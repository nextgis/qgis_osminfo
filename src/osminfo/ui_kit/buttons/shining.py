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

"""Shimmering buttons derived from the QuickMapServices UI kit."""

from typing import Optional

from qgis.PyQt.QtCore import QEasingCurve, QVariantAnimation
from qgis.PyQt.QtGui import QColor, QLinearGradient, QPainter
from qgis.PyQt.QtWidgets import QWidget

from osminfo.ui_kit.buttons.animated import ButtonVisualState
from osminfo.ui_kit.buttons.primary import PrimaryButton
from osminfo.ui_kit.graphics.decorator import (
    NextgisBrandColor,
    NextgisDecorator,
)


class ShiningButton(PrimaryButton):
    """Show a primary button with hover shimmer feedback."""

    def __init__(
        self,
        text: str = "",
        parent: Optional[QWidget] = None,
    ) -> None:
        self._shimmer_progress = 0.0
        super().__init__(text, parent)

        self._shimmer_animation = QVariantAnimation(self)
        self._shimmer_animation.setDuration(450)
        self._shimmer_animation.setEasingCurve(QEasingCurve.Type.InOutCubic)
        self._shimmer_animation.valueChanged.connect(
            self._set_shimmer_progress
        )

    def enterEvent(self, event) -> None:
        """Handle pointer entry."""

        self._animate_shimmer(1.0)
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        """Handle pointer exit."""

        self._animate_shimmer(0.0)
        super().leaveEvent(event)

    def paintEvent(self, event) -> None:
        """Paint the button and shimmer overlay."""

        super().paintEvent(event)

        if not self.isEnabled() or self._shimmer_progress <= 0.0:
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        rect = self.rect().adjusted(1, 1, -1, -1)
        band_width = max(48, rect.width() // 3)
        center_x = rect.left() + rect.width() * self._shimmer_progress

        gradient = QLinearGradient(
            center_x - band_width,
            rect.top(),
            center_x + band_width,
            rect.bottom(),
        )
        transparent = QColor("#ffffff")
        transparent.setAlpha(0)
        highlight = QColor("#ffffff")
        highlight.setAlpha(42)
        gradient.setColorAt(0.0, transparent)
        gradient.setColorAt(0.5, highlight)
        gradient.setColorAt(1.0, transparent)

        painter.fillRect(rect, gradient)

    def _background_css(self, state: ButtonVisualState) -> str:
        if not self.isEnabled() or self._is_pressed:
            return super()._background_css(state)

        start_color = NextgisDecorator.brand_color()
        end_color = NextgisDecorator.brand_color(NextgisBrandColor.ACCENT)

        return (
            "qlineargradient(x1:0, y1:1, x2:1, y2:0, "
            f"stop:0 {start_color.name()}, stop:1 {end_color.name()})"
        )

    def _animate_shimmer(self, target_value: float) -> None:
        self._shimmer_animation.stop()
        self._shimmer_animation.setStartValue(self._shimmer_progress)
        self._shimmer_animation.setEndValue(target_value)
        self._shimmer_animation.start()

    def _set_shimmer_progress(self, value: float) -> None:
        self._shimmer_progress = value
        self.update()
