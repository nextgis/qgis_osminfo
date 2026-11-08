# NextGIS OSMInfo Plugin
# Copyright (C) 2026  NextGIS
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or any
# later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License along
# with this program; if not, see <https://www.gnu.org/licenses/>.

"""Animated buttons derived from the QuickMapServices UI kit."""

from dataclasses import dataclass
from typing import Optional

from qgis.PyQt.QtCore import (
    QEasingCurve,
    QEvent,
    QRect,
    QRectF,
    QSize,
    Qt,
    QVariantAnimation,
)
from qgis.PyQt.QtGui import QColor, QPainter, QPalette, QPen
from qgis.PyQt.QtWidgets import QPushButton, QSizePolicy, QWidget

from osminfo.ui_kit.graphics.decorator import (
    NextgisDecorator,
    NextgisRadius,
    NextgisSize,
    NextgisSpacing,
)


@dataclass
class ButtonVisualState:
    """Store button colors for one visual state."""

    background: QColor
    border: QColor
    text: QColor


class AnimatedButtonBase(QPushButton):
    """Render a button with animated visual states."""

    _TRANSITION_DURATION_MS = 300

    def __init__(
        self,
        text: str = "",
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(text, parent)
        self._initial_palette = QPalette(self.palette())

        self._is_hovered = False
        self._is_pressed = False
        self._is_applying_visual_state = False
        self._current_state = self._target_state()
        self._animation_start_state = self._current_state
        self._animation_end_state = self._current_state

        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setAutoDefault(False)
        self.setDefault(False)
        self.set_button_height(
            NextgisDecorator.size(NextgisSize.CONTROL_COMPACT)
        )
        self.setSizePolicy(
            QSizePolicy.Policy.Minimum,
            QSizePolicy.Policy.Fixed,
        )
        self._sync_minimum_width()

        self._transition = QVariantAnimation(self)
        self._transition.setDuration(self._TRANSITION_DURATION_MS)
        self._transition.setStartValue(0.0)
        self._transition.setEndValue(1.0)
        self._transition.setEasingCurve(QEasingCurve.Type.InOutCubic)
        self._transition.valueChanged.connect(
            self._on_transition_value_changed
        )

        self._apply_visual_state(self._current_state)

    def setText(self, text: str) -> None:
        """Set button text and update its minimum width."""

        super().setText(text)
        self._sync_minimum_width()

    def sizeHint(self) -> QSize:
        """Return the preferred button size."""

        return QSize(self.minimumWidth(), self.minimumHeight())

    def minimumSizeHint(self) -> QSize:
        """Return the minimum button size."""

        return QSize(self.minimumWidth(), self.minimumHeight())

    def enterEvent(self, event) -> None:
        """Handle pointer entry."""

        self._is_hovered = True
        self._refresh_visual_state()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        """Handle pointer exit."""

        self._is_hovered = False
        self._is_pressed = False
        self._refresh_visual_state()
        super().leaveEvent(event)

    def mousePressEvent(self, event) -> None:
        """Handle pointer press."""

        if event.button() == Qt.MouseButton.LeftButton:
            self._is_pressed = True
            self._refresh_visual_state()

        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        """Handle pointer release."""

        self._is_pressed = False
        self._is_hovered = self.rect().contains(event.pos())
        self._refresh_visual_state()
        super().mouseReleaseEvent(event)

    def changeEvent(self, event) -> None:
        """Refresh the visual state when the palette changes."""

        if self._is_applying_visual_state:
            super().changeEvent(event)
            return

        if event.type() in (
            QEvent.Type.EnabledChange,
            QEvent.Type.PaletteChange,
            QEvent.Type.ApplicationPaletteChange,
            QEvent.Type.StyleChange,
        ):
            self._refresh_visual_state(animated=False)

        super().changeEvent(event)

    def _on_transition_value_changed(self, value: float) -> None:
        blended_state = ButtonVisualState(
            background=self._blend_color(
                self._animation_start_state.background,
                self._animation_end_state.background,
                value,
            ),
            border=self._blend_color(
                self._animation_start_state.border,
                self._animation_end_state.border,
                value,
            ),
            text=self._blend_color(
                self._animation_start_state.text,
                self._animation_end_state.text,
                value,
            ),
        )
        self._current_state = blended_state
        self._apply_visual_state(blended_state)

    def _refresh_visual_state(self, animated: bool = True) -> None:
        target_state = self._target_state()
        if self._states_equal(self._current_state, target_state):
            return

        if not animated:
            self._transition.stop()
            self._current_state = target_state
            self._animation_start_state = target_state
            self._animation_end_state = target_state
            self._apply_visual_state(target_state)
            return

        self._animation_start_state = self._current_state
        self._animation_end_state = target_state
        self._transition.stop()
        self._transition.start()

    def _apply_visual_state(self, state: ButtonVisualState) -> None:
        self._is_applying_visual_state = True
        try:
            self._after_visual_state_applied(state)
            self.update()
        finally:
            self._is_applying_visual_state = False

    def paintEvent(self, event) -> None:
        """Paint the button frame."""

        del event

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        border_rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        if border_rect.isEmpty():
            return

        painter.setBrush(self._current_state.background)
        pen = QPen(self._current_state.border)
        pen.setWidth(1)
        painter.setPen(pen)
        painter.drawRoundedRect(
            border_rect,
            self._border_radius(),
            self._border_radius(),
        )

        self._paint_content(painter, self.rect().adjusted(1, 1, -1, -1))

    def _background_css(self, state: ButtonVisualState) -> str:
        return NextgisDecorator.as_rgba(state.background)

    def _after_visual_state_applied(self, state: ButtonVisualState) -> None:
        del state

    def _target_state(self) -> ButtonVisualState:
        if not self.isEnabled():
            return self._disabled_state()

        if self._is_pressed:
            return self._pressed_state()

        if self._is_hovered:
            return self._hover_state()

        return self._normal_state()

    def _normal_state(self) -> ButtonVisualState:
        raise NotImplementedError

    def _hover_state(self) -> ButtonVisualState:
        raise NotImplementedError

    def _pressed_state(self) -> ButtonVisualState:
        raise NotImplementedError

    def _disabled_state(self) -> ButtonVisualState:
        raise NotImplementedError

    def _horizontal_padding(self) -> int:
        return NextgisDecorator.spacing(NextgisSpacing.LG)

    def _border_radius(self) -> int:
        return NextgisDecorator.radius(NextgisRadius.BUTTON)

    def set_button_height(self, height: int) -> None:
        """Set a fixed button height."""

        self.setMinimumHeight(height)
        self.setMaximumHeight(height)
        self._sync_minimum_width()

    def _states_equal(
        self,
        first_state: ButtonVisualState,
        second_state: ButtonVisualState,
    ) -> bool:
        return (
            first_state.background == second_state.background
            and first_state.border == second_state.border
            and first_state.text == second_state.text
        )

    def _blend_color(
        self,
        first_color: QColor,
        second_color: QColor,
        factor: float,
    ) -> QColor:
        return QColor(
            round(
                first_color.red()
                + (second_color.red() - first_color.red()) * factor
            ),
            round(
                first_color.green()
                + (second_color.green() - first_color.green()) * factor
            ),
            round(
                first_color.blue()
                + (second_color.blue() - first_color.blue()) * factor
            ),
            round(
                first_color.alpha()
                + (second_color.alpha() - first_color.alpha()) * factor
            ),
        )

    def _content_width(self) -> int:
        text_width = self.fontMetrics().horizontalAdvance(self.text())
        icon_width = 0
        if not self.icon().isNull():
            icon_width = self.iconSize().width()
            if text_width > 0:
                icon_width += self._icon_text_spacing()

        return icon_width + text_width

    def _minimum_width(self) -> int:
        return self._content_width() + self._horizontal_padding() * 2 + 2

    def _sync_minimum_width(self) -> None:
        if self.text() == "" and not self.icon().isNull():
            return

        self.setMinimumWidth(self._minimum_width())

    def _icon_text_spacing(self) -> int:
        return NextgisDecorator.spacing(NextgisSpacing.SM)

    def _paint_content(self, painter: QPainter, rect: QRect) -> None:
        icon = self.icon()
        text = self.text()
        icon_size = self.iconSize()
        text_width = self.fontMetrics().horizontalAdvance(text)
        has_icon = not icon.isNull()
        has_text = text != ""

        total_width = text_width
        if has_icon:
            total_width += icon_size.width()
            if has_text:
                total_width += self._icon_text_spacing()

        start_x = rect.left() + max(0, (rect.width() - total_width) // 2)
        center_y = rect.top() + rect.height() // 2

        if has_icon:
            icon_rect = QRect(
                start_x,
                center_y - icon_size.height() // 2,
                icon_size.width(),
                icon_size.height(),
            )
            icon.paint(
                painter,
                icon_rect,
                Qt.AlignmentFlag.AlignCenter,
            )
            start_x = icon_rect.right() + 1
            if has_text:
                start_x += self._icon_text_spacing()

        if not has_text:
            return

        painter.setPen(self._current_state.text)
        painter.drawText(
            QRect(
                start_x,
                rect.top(),
                text_width,
                rect.height(),
            ),
            Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
            text,
        )
