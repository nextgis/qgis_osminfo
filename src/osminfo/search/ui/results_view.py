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

from html import escape
from typing import Optional

from qgis.PyQt.QtCore import Qt, QTimer, pyqtSignal
from qgis.PyQt.QtWidgets import (
    QAbstractItemView,
    QHeaderView,
    QLabel,
    QTreeView,
    QWidget,
)

from osminfo.osminfo_interface import OsmInfoInterface
from osminfo.ui.icon import draw_icon, material_icon, plugin_icon


class OsmInfoResultsView(QTreeView):
    SETTINGS_LINK = "#settings"
    FIX_WIZARD_LINK = "#fix_wizard"
    OVERLAY_ICON_SIZE = 38
    OVERLAY_CONTENT_SPACING = 4
    LOADING_DOTS_INTERVAL_MS = 400
    OVERLAY_TEXT_PADDING = 8
    OVERLAY_TEXT_BUFFER = 4
    OVERLAY_MESSAGE_MARGIN_BOTTOM = 4

    LOADING_STAGE_FETCHING = "fetching"
    LOADING_STAGE_READING = "reading"

    fix_wizard_query = pyqtSignal()

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)

        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.setSelectionMode(
            QAbstractItemView.SelectionMode.ExtendedSelection
        )
        self.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectRows
        )
        self.setUniformRowHeights(True)

        header = self.header()
        header.setStretchLastSection(True)
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)

        self._loading_message = self.tr("Fetching data")
        self._loading_dots_count = 0
        self._loading_stage = self.LOADING_STAGE_FETCHING
        self._overlay_text_preferred_width: Optional[int] = None
        self._loading_timer = QTimer(self)
        self._loading_timer.setInterval(self.LOADING_DOTS_INTERVAL_MS)
        self._loading_timer.timeout.connect(self._advance_loading_message)

        self._init_styles()
        self._overlay = QWidget(self)
        self._overlay.setObjectName("resultsOverlay")
        self._overlay.setStyleSheet(self._overlay_style)

        self._overlay_icon_label = QLabel(self._overlay)
        self._overlay_icon_label.setObjectName("overlayIcon")
        self._overlay_icon_label.setFixedSize(
            self.OVERLAY_ICON_SIZE,
            self.OVERLAY_ICON_SIZE,
        )
        self._overlay_icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self._overlay_text_label = QLabel(self._overlay)
        self._overlay_text_label.setObjectName("overlayText")
        self._overlay_text_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._overlay_text_label.setTextFormat(Qt.TextFormat.RichText)
        self._overlay_text_label.setWordWrap(True)
        self._overlay_text_label.setOpenExternalLinks(False)
        self._overlay_text_label.linkActivated.connect(self._open_link)

        self._overlay.hide()

        QTimer.singleShot(0, self._resize_header)

        self.set_default_message()

    def show_root_level(self) -> None:
        model = self.model()
        if model is None:
            return

        self.collapseAll()
        for row_index in range(model.rowCount()):
            self.setExpanded(model.index(row_index, 0), True)

    def set_default_message(self) -> None:
        self._set_overlay_message(
            self._logo_icon,
            self.tr("Enter a search query to find OSM features"),
        )

    def set_fetching_message(self, message: Optional[str] = None) -> None:
        self._set_loading_stage(
            self.LOADING_STAGE_FETCHING,
            message or self.tr("Fetching data"),
        )

    def set_reading_message(self, message: Optional[str] = None) -> None:
        self._set_loading_stage(
            self.LOADING_STAGE_READING,
            message or self.tr("Reading response"),
        )

    def _set_loading_stage(self, stage: str, message: str) -> None:
        self._loading_stage = stage
        self._loading_message = message
        self._loading_dots_count = 0
        self._set_loading_text_mode()
        draw_icon(
            self._overlay_icon_label,
            self._loading_icon,
            size=self.OVERLAY_ICON_SIZE,
        )
        self._overlay_text_label.setText(self._format_loading_message())
        self._loading_timer.start()
        self._show_overlay()

    def set_not_found_message(
        self,
        additional_info: Optional[str] = None,
    ) -> None:
        self._set_overlay_message(
            self._not_found_icon,
            self.tr("No features found"),
            additional_info=additional_info,
        )

    def set_regional_not_found_message(self) -> None:
        self._set_overlay_message(
            self._not_found_icon,
            self.tr("No features found"),
            additional_info=self.tr(
                "<a href='{settings_link}'>Check</a> whether the "
                "selected Overpass server contains data for the "
                "requested region."
            ).format(settings_link=self.SETTINGS_LINK),
            additional_info_is_rich_text=True,
        )

    def set_error_message(
        self,
        message: str,
        additional_info: Optional[str] = None,
    ) -> None:
        self._set_overlay_message(
            self._error_icon,
            message,
            additional_info=additional_info,
        )

    def set_overpass_error_message(self, message: str) -> None:
        self._set_overlay_message(
            self._error_icon,
            message,
            additional_info=self.tr(
                "Try changing the Overpass server in "
                "<a href='{settings_link}'>plugin settings</a>."
            ).format(settings_link=self.SETTINGS_LINK),
            additional_info_is_rich_text=True,
        )

    def set_repairable_error_message(
        self,
        message: str,
        repaired_search: str,
        additional_info: Optional[str] = None,
    ) -> None:
        escaped_search = self._format_plain_text(repaired_search)
        repair_markup = self.tr(
            "Did you mean \"<a href='{fix_link}'>{repaired_search}</a>\"?"
        ).format(
            fix_link=self.FIX_WIZARD_LINK,
            repaired_search=escaped_search,
        )
        if additional_info is not None and len(additional_info.strip()) > 0:
            repair_markup = f"{self._format_plain_text(additional_info)}<br/>{repair_markup}"

        self._set_overlay_message(
            self._wrong_template,
            message,
            additional_info=repair_markup,
            additional_info_is_rich_text=True,
        )

    def clear_message(self) -> None:
        self._stop_loading_animation()
        self._reset_overlay_text_mode()
        self._overlay.hide()

    def _set_overlay_message(
        self,
        icon,
        message: str,
        additional_info: Optional[str] = None,
        additional_info_is_rich_text: bool = False,
    ) -> None:
        self._stop_loading_animation()
        self._reset_overlay_text_mode()
        draw_icon(
            self._overlay_icon_label,
            icon,
            size=self.OVERLAY_ICON_SIZE,
        )
        self._overlay_text_label.setText(
            self._format_overlay_message(
                message,
                additional_info=additional_info,
                additional_info_is_rich_text=additional_info_is_rich_text,
            )
        )
        self._show_overlay()

    def _format_overlay_message(
        self,
        message: str,
        additional_info: Optional[str] = None,
        additional_info_is_rich_text: bool = False,
    ) -> str:
        formatted_message = self._format_plain_text(message)
        if additional_info is None or len(additional_info.strip()) == 0:
            return formatted_message

        if additional_info_is_rich_text:
            formatted_additional_info = additional_info.strip()
        else:
            formatted_additional_info = self._format_plain_text(
                additional_info
            )

        return (
            f"<p style='margin: 0 0 {self.OVERLAY_MESSAGE_MARGIN_BOTTOM}px 0;'>"
            f"<b>{formatted_message}</b>"
            f"</p>"
            f"<p style='margin: 0;'>{formatted_additional_info}</p>"
        )

    def _format_plain_text(self, value: str) -> str:
        return escape(value).replace("\n", "<br/>")

    def resizeEvent(self, event) -> None:  # type: ignore[override]
        super().resizeEvent(event)
        self._overlay.resize(self.size())
        self._overlay.move(0, 0)
        self._layout_overlay_contents()

    def _init_styles(self) -> None:
        palette = self.palette()
        disabled_group = palette.ColorGroup.Disabled

        base_style = """
            QWidget#resultsOverlay {{
                background-color: {background_color};
            }}
            QLabel#overlayText {{
                color: {text_color};
                font-size: 14px;
                padding: 0 8px 4px 8px;
            }}
        """
        empty_list_text_color = palette.color(
            disabled_group, palette.ColorRole.Text
        ).name()

        self._overlay_style = base_style.format(
            background_color="transparent",
            text_color=empty_list_text_color,
        )
        self._logo_icon = plugin_icon(
            "osminfo_logo_white.svg",
            color=empty_list_text_color,
            size=self.OVERLAY_ICON_SIZE,
        )
        self._loading_icon = material_icon(
            "hourglass_empty",
            color=empty_list_text_color,
            size=self.OVERLAY_ICON_SIZE,
        )
        self._error_icon = material_icon(
            "globe_2_cancel",
            color=empty_list_text_color,
            size=self.OVERLAY_ICON_SIZE,
        )
        self._not_found_icon = material_icon(
            "globe_2_question",
            color=empty_list_text_color,
            size=self.OVERLAY_ICON_SIZE,
        )
        self._wrong_template = material_icon(
            "not_listed_location",
            color=empty_list_text_color,
            size=self.OVERLAY_ICON_SIZE,
        )

    def _show_overlay(self) -> None:
        self._layout_overlay_contents()
        self._overlay.show()

    def _set_loading_text_mode(self) -> None:
        self._overlay_text_preferred_width = self._loading_text_width()
        self._overlay_text_label.setAlignment(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
        )
        self._overlay_text_label.setWordWrap(False)
        self._layout_overlay_contents()

    def _reset_overlay_text_mode(self) -> None:
        self._overlay_text_preferred_width = None
        self._overlay_text_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._overlay_text_label.setWordWrap(True)
        self._layout_overlay_contents()

    def _advance_loading_message(self) -> None:
        self._loading_dots_count = (self._loading_dots_count % 3) + 1
        self._overlay_text_label.setText(self._format_loading_message())

    def _format_loading_message(self) -> str:
        return (
            f"{self._loading_message}{'.' * max(1, self._loading_dots_count)}"
        )

    def _loading_text_width(self) -> int:
        full_text = f"{self._loading_message}..."
        return (
            self._overlay_text_label.fontMetrics().horizontalAdvance(full_text)
            + (self.OVERLAY_TEXT_PADDING * 2)
            + self.OVERLAY_TEXT_BUFFER
        )

    def _stop_loading_animation(self) -> None:
        if self._loading_timer.isActive():
            self._loading_timer.stop()
        self._loading_dots_count = 0

    def _layout_overlay_contents(self) -> None:
        if not self._overlay or not self._overlay_text_label:
            return

        margin = 32
        label_width = max(0, self._overlay.width() - margin)
        if self._overlay_text_preferred_width is not None:
            label_width = min(label_width, self._overlay_text_preferred_width)

        self._overlay_text_label.setFixedWidth(label_width)

        label_height = self._overlay_text_label.heightForWidth(label_width)
        if label_height <= 0:
            label_height = self._overlay_text_label.sizeHint().height()

        first_line_height = (
            self._overlay_text_label.fontMetrics().lineSpacing()
        )
        centered_block_height = (
            self.OVERLAY_ICON_SIZE
            + self.OVERLAY_CONTENT_SPACING
            + first_line_height
        )
        icon_top = max(
            0, (self._overlay.height() - centered_block_height) // 2
        )
        icon_left = max(
            0,
            (self._overlay.width() - self.OVERLAY_ICON_SIZE) // 2,
        )
        self._overlay_icon_label.move(icon_left, icon_top)

        label_left = max(0, (self._overlay.width() - label_width) // 2)
        label_top = (
            icon_top + self.OVERLAY_ICON_SIZE + self.OVERLAY_CONTENT_SPACING
        )
        self._overlay_text_label.setGeometry(
            label_left,
            label_top,
            label_width,
            label_height,
        )

    def _open_link(self, url: str) -> None:
        if url == self.SETTINGS_LINK:
            plugin = OsmInfoInterface.instance()
            plugin.open_settings()
        elif url == self.FIX_WIZARD_LINK:
            self.fix_wizard_query.emit()

    def _resize_header(self) -> None:
        self.header().resizeSection(0, 200)
