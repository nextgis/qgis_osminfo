# ******************************************************************************
#
# OSMInfo
# ---------------------------------------------------------
# This plugin takes coordinates of a mouse click and gets information about all
# objects from this point from OSM using Overpass API.
#
# Author:   Maxim Dubinin, sim@gis-lab.info
# Author:   Alexander Lisovenko, alexander.lisovenko@nextgis.ru
# *****************************************************************************
# Copyright (c) 2012-2015. NextGIS, info@nextgis.com
#
# This source is free software; you can redistribute it and/or modify it under
# the terms of the GNU General Public License as published by the Free
# Software Foundation, either version 2 of the License, or (at your option)
# any later version.
#
# This code is distributed in the hope that it will be useful, but WITHOUT ANY
# WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS
# FOR A PARTICULAR PURPOSE. See the GNU General Public License for more
# details.
#
# A copy of the GNU General Public License is available on the World Wide Web
# at <http://www.gnu.org/licenses/>. You can also obtain it by writing
# to the Free Software Foundation, 51 Franklin Street, Suite 500 Boston,
# MA 02110-1335 USA.
#
# ******************************************************************************

from typing import Optional, cast

from qgis.core import (
    QgsCoordinateReferenceSystem,
    QgsCoordinateTransform,
    QgsPointXY,
    QgsProject,
)
from qgis.gui import QgisInterface, QgsMapMouseEvent, QgsMapTool
from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtGui import QCursor, QPixmap
from qgis.PyQt.QtWidgets import QApplication, QMainWindow

from . import resources  # noqa: F401
from .osminforesults import OsmInfoResultsDock
from .rb_result_renderer import RubberBandResultRenderer


class OSMInfotool(QgsMapTool):
    def __init__(self, iface: QgisInterface) -> None:
        QgsMapTool.__init__(self, iface.mapCanvas())
        self.result_renderer = RubberBandResultRenderer()

        # self.emitPoint = QgsMapToolEmitPoint(self.canvas)
        self.iface = iface

        self.cursor = QCursor(
            QPixmap(":/plugins/osminfo/icons/cursor.png"), 1, 1
        )
        # self.visibilityChanged.connect(self.result_renderer.clear)

        self.dockWidgetResults = OsmInfoResultsDock(
            "OSMInfo", self.result_renderer
        )

        main_window = cast(QMainWindow, iface.mainWindow())
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

    def __del__(self):
        main_window = cast(QMainWindow, self.iface.mainWindow())
        main_window.removeDockWidget(self.dockWidgetResults)
        self.clearCanvas()

    def clearCanvas(self):
        self.result_renderer.clear()
        self.result_renderer.clear_feature()

    def docWidgetResultsVisChange(self, vis):
        if vis is False:
            self.clearCanvas()

    def activate(self):
        self.canvas().setCursor(self.cursor)

    def deactivate(self):
        if self.dockWidgetResults.isFloating():
            self.dockWidgetResults.setVisible(False)

    def canvasReleaseEvent(self, e: Optional[QgsMapMouseEvent]):
        crsSrc = self.iface.mapCanvas().mapSettings().destinationCrs()
        crsWGS = QgsCoordinateReferenceSystem.fromEpsgId(4326)

        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        x = e.pos().x()
        y = e.pos().y()
        point = self.canvas().getCoordinateTransform().toMapCoordinates(x, y)

        xform = QgsCoordinateTransform(crsSrc, crsWGS, QgsProject.instance())
        point = xform.transform(QgsPointXY(point.x(), point.y()))
        QApplication.restoreOverrideCursor()

        xx = str(point.x())
        yy = str(point.y())

        self.result_renderer.clear()
        self.result_renderer.clear_feature()
        self.result_renderer.show_point(point, False)
        self.canvas().update()

        self.dockWidgetResults.getInfo(xx, yy)
        self.dockWidgetResults.setUserVisible(True)
