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

from qgis.core import (
    QgsCoordinateReferenceSystem,
    QgsCoordinateTransform,
    QgsPointXY,
    QgsProject,
)
from qgis.gui import QgisInterface, QgsMapMouseEvent, QgsMapTool
from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtGui import QCursor
from qgis.PyQt.QtWidgets import QMainWindow
from qgis.utils import iface

from osminfo.core.constants import PLUGIN_NAME
from osminfo.ui.cursor import OsmInfoCursor, create_cursor

from . import resources  # noqa: F401
from .osminforesults import OsmInfoResultsDock
from .rb_result_renderer import RubberBandResultRenderer

if TYPE_CHECKING:
    assert isinstance(iface, QgisInterface)


class OSMInfotool(QgsMapTool):
    def __init__(self, iface: QgisInterface) -> None:
        super().__init__(iface.mapCanvas())
        self.__default_cursor = create_cursor(OsmInfoCursor.IDENTIFY)
        self.__is_loading = False
        self.setCursor(self.__default_cursor)

        self.result_renderer = RubberBandResultRenderer()

        main_window = cast(QMainWindow, iface.mainWindow())
        self.dockWidgetResults = OsmInfoResultsDock(
            PLUGIN_NAME, self.result_renderer, main_window
        )

        if main_window.restoreDockWidget(self.dockWidgetResults):
            main_window.panelMenu().addAction(
                self.dockWidgetResults.toggleViewAction()
            )
        else:
            main_window.addDockWidget(
                Qt.DockWidgetArea.RightDockWidgetArea, self.dockWidgetResults
            )

        self.dockWidgetResults.visibilityChanged.connect(
            self.docWidgetResultsVisChange
        )
        self.dockWidgetResults.loadingStateChanged.connect(
            self.__set_loading_state
        )

    def __del__(self):
        self.cleanup()

    def cleanup(self) -> None:
        main_window = cast(QMainWindow, iface.mainWindow())

        dock_widget = self.dockWidgetResults
        panel_menu = main_window.panelMenu()  # pyright: ignore[reportAttributeAccessIssue]

        panel_menu.removeAction(dock_widget.toggleViewAction())
        main_window.removeDockWidget(dock_widget)
        dock_widget.close()
        dock_widget.deleteLater()
        self.dockWidgetResults = None
        self.clearCanvas()

    def clearCanvas(self):
        self.result_renderer.clear()
        self.result_renderer.clear_feature()

    def docWidgetResultsVisChange(self, vis):
        if vis is False:
            self.clearCanvas()

    def deactivate(self):
        if self.dockWidgetResults.isFloating():
            self.dockWidgetResults.setVisible(False)

        super().deactivate()

    def activate(self):
        super().activate()
        self.__update_cursor()

    def __set_loading_state(self, is_loading: bool) -> None:
        self.__is_loading = is_loading
        self.__update_cursor()

    def __update_cursor(self) -> None:
        cursor = self.__default_cursor
        if self.__is_loading:
            cursor = QCursor(Qt.CursorShape.WaitCursor)

        self.setCursor(cursor)
        if self.canvas().mapTool() == self:
            self.canvas().setCursor(cursor)

    def canvasReleaseEvent(self, e: Optional[QgsMapMouseEvent]):
        if e is None:
            return

        crsSrc = iface.mapCanvas().mapSettings().destinationCrs()
        crsWGS = QgsCoordinateReferenceSystem.fromEpsgId(4326)
        point = QgsPointXY(e.mapPoint())

        xform = QgsCoordinateTransform(crsSrc, crsWGS, QgsProject.instance())
        point = QgsPointXY(xform.transform(point))

        xx = str(point.x())
        yy = str(point.y())

        self.result_renderer.clear()
        self.result_renderer.clear_feature()
        self.result_renderer.show_point(point, False)
        self.canvas().update()

        self.dockWidgetResults.set_search_text(f"{xx}, {yy}")
        self.dockWidgetResults.getInfo(point)
        self.dockWidgetResults.setUserVisible(True)
