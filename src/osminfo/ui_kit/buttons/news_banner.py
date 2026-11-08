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

"""News banner button derived from the QuickMapServices UI kit."""

from html import escape
from html.parser import HTMLParser
from typing import List, Optional, Tuple

from qgis.PyQt.QtCore import QSize, Qt, QUrl
from qgis.PyQt.QtGui import (
    QColor,
    QDesktopServices,
    QLinearGradient,
    QPainter,
    QPixmap,
)
from qgis.PyQt.QtWidgets import QHBoxLayout, QLabel, QSizePolicy, QWidget

from osminfo.ui_kit.buttons.animated import ButtonVisualState
from osminfo.ui_kit.buttons.shining import ShiningButton

NEWS_BANNER_BORDER_RADIUS = 3
NEWS_BANNER_PADDING_HORIZONTAL = 6
NEWS_BANNER_PADDING_VERTICAL = 6
NEWS_BANNER_MINIMUM_HEIGHT = 30
NEWS_BANNER_MINIMUM_WIDTH = 160
NEWS_BANNER_ICON_SIZE = 16
NEWS_BANNER_ICON_TEXT_SPACING = 5
NEWS_BANNER_SHIMMER_ALPHA = 2
NEWS_BANNER_SHIMMER_BAND_MIN_WIDTH = 32
NEWS_BANNER_NORMAL_BACKGROUND_ALPHA = 12
NEWS_BANNER_HOVER_BACKGROUND_ALPHA = 0
NEWS_BANNER_PRESSED_BACKGROUND_ALPHA = 46
NEWS_BANNER_NORMAL_BORDER_ALPHA = 58


class NewsBannerHtmlParser(HTMLParser):
    """Extract an icon and formatted display text from banner HTML."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.image_path = ""
        self.fragments: List[Tuple[str, bool]] = []
        self._bold_depth = 0

    @property
    def display_html(self) -> str:
        """Return sanitized rich text for the banner label."""

        parts = []
        for text, is_bold in self.fragments:
            escaped_text = escape(text)
            if is_bold:
                escaped_text = f"<b>{escaped_text}</b>"

            parts.append(escaped_text)

        return " ".join(parts)

    @property
    def plain_text(self) -> str:
        """Return the banner text without rich-text markup."""

        return " ".join(text for text, _ in self.fragments)

    def handle_starttag(
        self,
        tag: str,
        attrs: List[Tuple[str, Optional[str]]],
    ) -> None:
        tag_name = tag.casefold()
        if tag_name == "img":
            self._store_image_path(attrs)
            return

        if tag_name in ("b", "strong"):
            self._bold_depth += 1

    def handle_startendtag(
        self,
        tag: str,
        attrs: List[Tuple[str, Optional[str]]],
    ) -> None:
        del attrs
        if tag.casefold() == "br":
            self._append_text(" ")

    def handle_endtag(self, tag: str) -> None:
        if tag.casefold() in ("b", "strong") and self._bold_depth > 0:
            self._bold_depth -= 1

    def handle_data(self, data: str) -> None:
        self._append_text(data)

    def _store_image_path(
        self,
        attrs: List[Tuple[str, Optional[str]]],
    ) -> None:
        if self.image_path:
            return

        for name, value in attrs:
            if name.casefold() == "src" and value:
                self.image_path = value
                return

    def _append_text(self, data: str) -> None:
        text = " ".join(data.replace("\xa0", " ").split())
        if text:
            self.fragments.append((text, self._bold_depth > 0))


class NewsBannerButton(ShiningButton):
    """Flat news banner button with rich text and subtle shimmer."""

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        self._banner_url = ""
        self._banner_display_html = ""
        self._banner_plain_text = ""
        self._banner_image_path = ""
        self._compact_banner_text = ""
        self._full_banner_width = NEWS_BANNER_MINIMUM_WIDTH

        super().__init__("", parent)

        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setMinimumWidth(0)
        self.setMinimumHeight(NEWS_BANNER_MINIMUM_HEIGHT)
        self.setMaximumHeight(16777215)
        self.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Minimum,
        )

        self._icon_label = QLabel(self)
        self._icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._icon_label.setAttribute(
            Qt.WidgetAttribute.WA_TransparentForMouseEvents,
            True,
        )
        self._icon_label.setFixedSize(
            NEWS_BANNER_ICON_SIZE,
            NEWS_BANNER_ICON_SIZE,
        )
        self._icon_label.setSizePolicy(
            QSizePolicy.Policy.Fixed,
            QSizePolicy.Policy.Fixed,
        )
        self._icon_label.setVisible(False)

        self._text_label = QLabel(self)
        self._text_label.setAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
        )
        self._text_label.setAttribute(
            Qt.WidgetAttribute.WA_TransparentForMouseEvents,
            True,
        )
        self._text_label.setTextFormat(Qt.TextFormat.RichText)
        self._text_label.setWordWrap(False)
        self._text_label.setSizePolicy(
            QSizePolicy.Policy.Preferred,
            QSizePolicy.Policy.Fixed,
        )

        self._content_layout = QHBoxLayout(self)
        self._content_layout.setContentsMargins(
            NEWS_BANNER_PADDING_HORIZONTAL,
            NEWS_BANNER_PADDING_VERTICAL,
            NEWS_BANNER_PADDING_HORIZONTAL,
            NEWS_BANNER_PADDING_VERTICAL,
        )
        self._content_layout.setSpacing(0)
        self._content_layout.addStretch()
        self._content_layout.addWidget(
            self._icon_label,
            0,
            Qt.AlignmentFlag.AlignVCenter,
        )
        self._content_layout.addWidget(
            self._text_label,
            0,
            Qt.AlignmentFlag.AlignVCenter,
        )
        self._content_layout.addStretch()

        self.clicked.connect(self._open_banner_link)

    def set_banner_html(
        self,
        html: str,
        url: str,
        compact_text: Optional[str] = None,
    ) -> None:
        """Set the banner content and its destination URL."""

        parser = NewsBannerHtmlParser()
        parser.feed(html)
        parser.close()

        self._banner_url = url
        self._banner_display_html = parser.display_html
        self._banner_plain_text = parser.plain_text
        self._banner_image_path = parser.image_path
        self._update_banner_icon()
        self._text_label.setText(self._banner_display_html)
        self._full_banner_width = self._button_width_hint()

        self._compact_banner_text = ""
        if compact_text is not None:
            compact_parser = NewsBannerHtmlParser()
            compact_parser.feed(compact_text)
            compact_parser.close()
            self._compact_banner_text = compact_parser.display_html
            self._text_label.setText(self._compact_banner_text)

        self.setMinimumSize(self.minimumSizeHint())
        self.setToolTip(self._banner_plain_text)
        self.setEnabled(bool(self._banner_url))
        self.updateGeometry()
        self.update()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)

        text = self._banner_display_html
        if (
            self._compact_banner_text
            and event.size().width() < self._full_banner_width
        ):
            text = self._compact_banner_text

        if self._text_label.text() != text:
            self._text_label.setText(text)

    def hasHeightForWidth(self) -> bool:
        """Return whether the banner height depends on its width."""

        return False

    def heightForWidth(self, width: int) -> int:
        """Return the fixed banner height."""

        del width
        return self._button_height_hint()

    def sizeHint(self) -> QSize:
        """Return the preferred banner size."""

        return QSize(
            max(self.width(), self._button_width_hint()),
            self._button_height_hint(),
        )

    def minimumSizeHint(self) -> QSize:
        """Return the minimum banner size."""

        return QSize(
            self._button_width_hint(),
            self._button_height_hint(),
        )

    def paintEvent(self, event) -> None:
        """Paint the button and the banner-specific shimmer."""

        super(ShiningButton, self).paintEvent(event)
        self._paint_subtle_shimmer()

    def _normal_state(self) -> ButtonVisualState:
        return ButtonVisualState(
            background=self._overlay_color(
                NEWS_BANNER_NORMAL_BACKGROUND_ALPHA
            ),
            border=self._overlay_color(NEWS_BANNER_NORMAL_BORDER_ALPHA),
            text=self._text_color(),
        )

    def _hover_state(self) -> ButtonVisualState:
        return ButtonVisualState(
            background=self._overlay_color(NEWS_BANNER_HOVER_BACKGROUND_ALPHA),
            border=self._overlay_color(NEWS_BANNER_NORMAL_BORDER_ALPHA),
            text=self._text_color(),
        )

    def _pressed_state(self) -> ButtonVisualState:
        return ButtonVisualState(
            background=self._overlay_color(
                NEWS_BANNER_PRESSED_BACKGROUND_ALPHA
            ),
            border=self._overlay_color(NEWS_BANNER_NORMAL_BORDER_ALPHA),
            text=self._text_color(),
        )

    def _disabled_state(self) -> ButtonVisualState:
        return ButtonVisualState(
            background=self._overlay_color(10),
            border=self._overlay_color(28),
            text=self._text_color(),
        )

    def _border_radius(self) -> int:
        return NEWS_BANNER_BORDER_RADIUS

    def _open_banner_link(self) -> None:
        if self._banner_url:
            QDesktopServices.openUrl(QUrl(self._banner_url))

    def _overlay_color(self, alpha: int) -> QColor:
        color = QColor(self.palette().text().color())
        color.setAlpha(alpha)
        return color

    def _text_color(self) -> QColor:
        return QColor(self.palette().windowText().color())

    def _update_banner_icon(self) -> None:
        pixmap = QPixmap(self._banner_image_path)
        has_icon = not pixmap.isNull()
        self._icon_label.setVisible(has_icon)
        self._text_label.setContentsMargins(
            NEWS_BANNER_ICON_TEXT_SPACING if has_icon else 0,
            0,
            0,
            0,
        )
        if not has_icon:
            self._icon_label.clear()
            return

        self._icon_label.setPixmap(
            pixmap.scaled(
                NEWS_BANNER_ICON_SIZE,
                NEWS_BANNER_ICON_SIZE,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )

    def _button_width_hint(self) -> int:
        return max(
            NEWS_BANNER_MINIMUM_WIDTH,
            self._content_width_hint()
            + NEWS_BANNER_PADDING_HORIZONTAL * 2
            + 2,
        )

    def _button_height_hint(self) -> int:
        return max(
            NEWS_BANNER_MINIMUM_HEIGHT,
            max(self._content_height_hint(), NEWS_BANNER_ICON_SIZE)
            + NEWS_BANNER_PADDING_VERTICAL * 2
            + 2,
        )

    def _content_width_hint(self) -> int:
        content_width = self._text_label.sizeHint().width()
        if self._icon_label.isVisible():
            content_width += NEWS_BANNER_ICON_SIZE
            content_width += NEWS_BANNER_ICON_TEXT_SPACING

        return content_width

    def _content_height_hint(self) -> int:
        return self._text_label.sizeHint().height()

    def _paint_subtle_shimmer(self) -> None:
        if not self.isEnabled() or self._shimmer_progress <= 0.0:
            return

        rect = self.rect().adjusted(1, 1, -1, -1)
        if rect.isEmpty():
            return

        band_width = max(NEWS_BANNER_SHIMMER_BAND_MIN_WIDTH, rect.width() // 4)
        center_x = rect.left() + rect.width() * self._shimmer_progress
        highlight = QColor(self._current_state.text)
        highlight.setAlpha(NEWS_BANNER_SHIMMER_ALPHA)
        transparent = QColor(highlight)
        transparent.setAlpha(0)

        gradient = QLinearGradient(
            center_x - band_width,
            rect.top(),
            center_x + band_width,
            rect.bottom(),
        )
        gradient.setColorAt(0.0, transparent)
        gradient.setColorAt(0.5, highlight)
        gradient.setColorAt(1.0, transparent)

        painter = QPainter(self)
        painter.fillRect(rect, gradient)
        painter.end()
