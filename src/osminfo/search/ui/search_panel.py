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

from typing import Optional

from qgis.gui import QgsDockWidget
from qgis.PyQt.QtCore import Qt, QTimer, pyqtSignal, pyqtSlot
from qgis.PyQt.QtWidgets import (
    QAction,
    QHBoxLayout,
    QMenu,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from osminfo.core.logging import logger
from osminfo.osminfo_interface import OsmInfoInterface
from osminfo.search.ui.nextgis_banner import NextGisBannerWidget
from osminfo.search.ui.results_view import OsmInfoResultsView
from osminfo.search.ui.search_combobox import OsmInfoSearchComboBox
from osminfo.ui.icon import material_icon, qgis_icon
from osminfo.ui.loading_tool_button import LoadingToolButton


class OsmInfoSearchPanel(QgsDockWidget):
    search = pyqtSignal(str)
    cancel = pyqtSignal()
    visibility_changed = pyqtSignal(bool)
    clear_results = pyqtSignal()
    all_features_visibility_changed = pyqtSignal(bool)
    small_features_as_points_changed = pyqtSignal(bool)

    def __init__(
        self,
        title: str,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(title, parent=parent)

        self.setWindowTitle(title)
        self.setObjectName("OsmInfoSearchPanel")
        self.setAllowedAreas(
            Qt.DockWidgetArea.LeftDockWidgetArea
            | Qt.DockWidgetArea.RightDockWidgetArea
        )

        self._content = QWidget(self)
        self.setWidget(self._content)

        self._main_layout = QVBoxLayout(self._content)
        self._main_layout.setSpacing(4)
        self._main_layout.setContentsMargins(0, 0, 0, 4)

        self.search_layout = QHBoxLayout()
        self.search_layout.setSpacing(3)
        self._main_layout.addLayout(self.search_layout)

        self.search_combobox = OsmInfoSearchComboBox(self)
        self.search_combobox.search_requested.connect(self.search.emit)
        self.search_combobox.clear_results.connect(self.clear_results.emit)
        self.search_layout.addWidget(self.search_combobox)

        self.search_button = LoadingToolButton(
            ":images/themes/default/mIconLoading.gif",
            material_icon("map_search"),
            material_icon("cancel"),
            self,
        )
        self.search_button.setObjectName("search_button")
        self.search_button.setToolTip(self.tr("Search OSM features"))
        self.search_button.clicked.connect(self._emit_search_requested)
        self.search_button.cancelRequested.connect(self.cancel.emit)

        square_size = self.search_combobox.sizeHint().height()
        self.search_button.setFixedSize(square_size, square_size)
        self.search_layout.addWidget(self.search_button)

        self.map_tool_button = QToolButton(self)
        self.map_tool_button.setObjectName("map_tool_button")
        self.map_tool_button.setFixedSize(square_size, square_size)
        self.map_tool_button.setCheckable(True)
        self.map_tool_button.setIcon(material_icon("arrow_selector_tool"))
        self.map_tool_button.setToolTip(
            self.tr("Identify OpenStreetMap Features")
        )
        self.map_tool_button.clicked.connect(self._on_map_tool_button_clicked)
        self.map_tool_button.hide()
        self._map_tool_action: Optional[QAction] = None

        self.search_layout.addWidget(self.map_tool_button)

        self.menu_button = QToolButton(self)
        self.menu_button.setObjectName("menu_button")
        self.menu_button.setIcon(material_icon("menu"))
        self.menu_button.setToolTip(self.tr("Open OSMInfo menu"))
        self.menu_button.setFixedSize(square_size, square_size)
        self.menu_button.setStyleSheet(
            """
            QToolButton::menu-indicator {
                image: none;
            }
            """
        )

        plugin = OsmInfoInterface.instance()

        search_menu = QMenu(self.menu_button)

        self.show_all_features_action = QAction(
            qgis_icon("mActionHighlightFeature.svg"),
            self.tr("Show all found features"),
            self.menu_button,
        )
        self.show_all_features_action.setCheckable(True)
        self.show_all_features_action.triggered.connect(
            self.all_features_visibility_changed
        )

        self.small_features_action = QAction(
            qgis_icon("rendererPointClusterSymbol.svg"),
            self.tr("Show small features as points"),
            self.menu_button,
        )
        self.small_features_action.setCheckable(True)
        self.small_features_action.triggered.connect(
            self.small_features_as_points_changed
        )

        settings_action = QAction(
            qgis_icon("iconSettingsConsole.svg"),
            self.tr("Settings"),
            self.menu_button,
        )
        settings_action.triggered.connect(plugin.open_settings)
        about_action = QAction(
            qgis_icon("mActionPropertiesWidget.svg"),
            self.tr("About plugin…"),
            self,
        )
        about_action.triggered.connect(plugin.open_about_dialog)

        search_menu.addAction(self.show_all_features_action)
        search_menu.addAction(self.small_features_action)
        search_menu.addSeparator()
        search_menu.addAction(settings_action)
        search_menu.addAction(about_action)

        self.menu_button.setMenu(search_menu)
        self.menu_button.setPopupMode(
            QToolButton.ToolButtonPopupMode.InstantPopup
        )
        self.search_layout.addWidget(self.menu_button)

        self.results_view = OsmInfoResultsView(self)
        self._main_layout.addWidget(self.results_view, 1)

        self.banner_widget = NextGisBannerWidget(self)
        self._main_layout.addWidget(self.banner_widget)
        self._updated_visibility = False
        self._is_visible = False

        self.visibilityChanged.connect(self._log_visibility_change)

    @property
    def search_text(self) -> str:
        return self.search_combobox.search_text

    def set_search_text(self, search_text: str) -> None:
        self.search_combobox.search_text = search_text

    def save_current_search(self) -> None:
        self.search_combobox.save_current_search()

    def set_show_all_found_features(self, enabled: bool) -> None:
        self.show_all_features_action.setChecked(enabled)

    def set_show_small_features_as_points(self, enabled: bool) -> None:
        self.small_features_action.setChecked(enabled)

    def set_map_tool_action(self, action: Optional[QAction]) -> None:
        if self._map_tool_action is action:
            if action is None:
                self.map_tool_button.hide()
                return

            self._sync_map_tool_button(action)
            self.map_tool_button.show()
            return

        if self._map_tool_action is not None:
            self._map_tool_action.toggled.disconnect(
                self._set_map_tool_checked
            )

        self._map_tool_action = action
        if action is None:
            self.map_tool_button.hide()
            return

        action.toggled.connect(self._set_map_tool_checked)
        self._sync_map_tool_button(action)
        self.map_tool_button.show()

    def set_loading_state(self, is_loading: bool) -> None:
        self.search_combobox.setEnabled(not is_loading)
        if is_loading:
            self.search_button.start()
            return

        self.search_button.stop()

    @pyqtSlot(bool)
    def _set_map_tool_checked(self, checked: bool) -> None:
        self.map_tool_button.blockSignals(True)
        self.map_tool_button.setChecked(checked)
        self.map_tool_button.blockSignals(False)

    @pyqtSlot(bool)
    def _on_map_tool_button_clicked(self, _checked: bool) -> None:
        if self._map_tool_action is None:
            return

        self._map_tool_action.trigger()
        self._sync_map_tool_button(self._map_tool_action)

    def _sync_map_tool_button(self, action: QAction) -> None:
        self.map_tool_button.setEnabled(action.isEnabled())
        self._set_map_tool_checked(action.isChecked())

    @pyqtSlot()
    def _emit_search_requested(self) -> None:
        self.search.emit(self.search_text)

    def _log_visibility_change(self, is_enabled: bool) -> None:
        self._updated_visibility = is_enabled
        QTimer.singleShot(100, self._emit_visibility_changed)

    @pyqtSlot()
    def _emit_visibility_changed(self) -> None:
        if self._is_visible == self._updated_visibility:
            return

        logger.debug(
            f"Search panel visibility changed: {self._updated_visibility}"
        )
        self._is_visible = self._updated_visibility
        self.visibility_changed.emit(self._updated_visibility)
