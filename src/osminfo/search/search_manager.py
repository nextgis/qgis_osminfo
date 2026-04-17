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

from typing import TYPE_CHECKING, Optional, cast

from qgis.core import QgsPointXY
from qgis.PyQt.QtCore import QObject, Qt, pyqtSlot
from qgis.PyQt.QtWidgets import QAction, QMainWindow
from qgis.utils import iface

from osminfo.core.constants import PLUGIN_NAME, POINT_PRECISION
from osminfo.search.identification.tool import OsmInfoMapTool
from osminfo.search.identification.tool_handler import OsmInfoToolHandler
from osminfo.search.ui.search_panel import OsmInfoSearchPanel
from osminfo.ui.icon import plugin_icon

if TYPE_CHECKING:
    from qgis.gui import QgisInterface

    from osminfo.osminfo_interface import OsmInfoInterface

    assert isinstance(iface, QgisInterface)


class OsmInfoSearchManager(QObject):
    _plugin: "OsmInfoInterface"
    _tool_action: Optional[QAction]
    _identify_tool: Optional[OsmInfoMapTool]
    _panel_action: Optional[QAction]
    _search_panel: Optional[OsmInfoSearchPanel]
    _tool_handler: Optional[OsmInfoToolHandler]

    def __init__(self, parent: "OsmInfoInterface") -> None:
        super().__init__(parent)

        self._plugin = parent
        self._tool_action = None
        self._identify_tool = None
        self._panel_action = None
        self._search_panel = None
        self._tool_handler = None

    def load(self) -> None:
        self._load_search_panel()
        self._load_tool()

    def unload(self) -> None:
        self._unload_tool()
        self._unload_search_panel()

    def _load_search_panel(self) -> None:
        if self._search_panel is not None:
            return

        main_window = cast(QMainWindow, iface.mainWindow())
        self._search_panel = OsmInfoSearchPanel(PLUGIN_NAME, main_window)
        self._search_panel.search.connect(self._search_by_string)
        self._search_panel.cancel.connect(self._cancel)

        self._panel_action = QAction(
            self.tr("Show/Hide {} Panel").format(PLUGIN_NAME), self
        )
        self._panel_action.setIcon(plugin_icon())
        self._search_panel.setToggleVisibilityAction(self._panel_action)

        # This action is used in the panel list in QGIS, so we set the icon for it as well
        self._search_panel.toggleViewAction().setIcon(plugin_icon())

        iface.addPluginToWebMenu(PLUGIN_NAME, self._panel_action)
        iface.addWebToolBarIcon(self._panel_action)

        if not main_window.restoreDockWidget(self._search_panel):
            main_window.addDockWidget(
                Qt.DockWidgetArea.RightDockWidgetArea,
                self._search_panel,
            )

    def _unload_search_panel(self) -> None:
        if self._search_panel is not None:
            main_window = cast(QMainWindow, iface.mainWindow())
            main_window.removeDockWidget(self._search_panel)
            self._search_panel.close()
            self._search_panel.deleteLater()
            self._search_panel = None

        if self._panel_action is not None:
            iface.removePluginWebMenu(PLUGIN_NAME, self._panel_action)
            iface.removeToolBarIcon(self._panel_action)
            self._panel_action.deleteLater()
            self._panel_action = None

    def _load_tool(self) -> None:
        if self._tool_handler is not None:
            return

        self._tool_action = QAction(
            self.tr("Identify OpenStreetMap Features"), self
        )
        self._tool_action.setIcon(plugin_icon("mActionIdentify.svg"))
        iface.addPluginToWebMenu(PLUGIN_NAME, self._tool_action)
        iface.addWebToolBarIcon(self._tool_action)

        self._identify_tool = OsmInfoMapTool(iface.mapCanvas())
        self._identify_tool.identify_point.connect(self._on_identify_point)

        self._tool_handler = OsmInfoToolHandler(
            self._identify_tool, self._tool_action
        )
        iface.registerMapToolHandler(self._tool_handler)

    def _unload_tool(self) -> None:
        if self._tool_handler is not None:
            iface.unregisterMapToolHandler(self._tool_handler)
            self._tool_handler = None

        if self._identify_tool is not None:
            if iface.mapCanvas().mapTool() == self._identify_tool:
                iface.mapCanvas().unsetMapTool(self._identify_tool)

            self._identify_tool.deleteLater()
            self._identify_tool = None

        if self._tool_action is not None:
            iface.removePluginWebMenu(PLUGIN_NAME, self._tool_action)
            iface.removeToolBarIcon(self._tool_action)
            self._tool_action.deleteLater()
            self._tool_action = None

    @pyqtSlot(QgsPointXY)
    def _on_identify_point(self, point: QgsPointXY) -> None:
        assert self._search_panel is not None
        self._search_panel.set_search_text(point.toString(POINT_PRECISION))
        self._search_panel.setUserVisible(True)

    @pyqtSlot(str)
    def _search_by_string(self, search_text: str) -> None:
        if not search_text.strip():
            return

        assert self._search_panel is not None
        self._search_panel.save_current_search()

    @pyqtSlot()
    def _cancel(self) -> None:
        if self._identify_tool is not None:
            self._identify_tool.is_loading = False

        if self._search_panel is not None:
            self._search_panel.set_loading_state(False)
