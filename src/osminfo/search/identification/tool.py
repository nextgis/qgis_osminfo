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

from qgis.core import (
    QgsCoordinateReferenceSystem,
    QgsCoordinateTransform,
    QgsPointXY,
    QgsProject,
)
from qgis.gui import QgsMapCanvas, QgsMapMouseEvent, QgsMapTool
from qgis.PyQt.QtCore import QPoint, Qt, pyqtSignal, pyqtSlot
from qgis.PyQt.QtGui import QCursor

from osminfo.core.constants import POINT_PRECISION
from osminfo.logging import logger
from osminfo.search.identification.click_renderer import OsmInfoClickRenderer
from osminfo.ui.cursor import OsmInfoCursor, create_cursor


class OsmInfoMapTool(QgsMapTool):
    """A tool for identifying openstreetmap objects by clicking on the map canvas"""

    identify_point = pyqtSignal(QgsPointXY)
    clear_results = pyqtSignal()

    _cursor: QCursor
    _pressed_position: Optional[QPoint]
    _last_position: Optional[QPoint]
    _is_pan_action_started: bool
    _is_loading: bool

    def __init__(self, canvas: Optional[QgsMapCanvas]) -> None:
        super().__init__(canvas)

        self._default_cursor = create_cursor(OsmInfoCursor.IDENTIFY)
        self.setCursor(self._default_cursor)

        self.is_loading = False

        self._pressed_position = None
        self._last_position = None
        self._is_pan_action_started = False
        self._is_loading = False

        assert canvas is not None
        self._click_renderer = OsmInfoClickRenderer(canvas, self)

        self.identify_point.connect(self._log_position)

    def __del__(self) -> None:
        if self.canvas():
            self.canvas().unsetMapTool(self)

    def flags(self) -> QgsMapTool.Flag:
        return super().flags() | QgsMapTool.Flag.ShowContextMenu  # type: ignore

    @property
    def is_loading(self) -> bool:
        return self._is_loading

    @is_loading.setter
    def is_loading(self, value: bool) -> None:
        self._is_loading = value
        if value:
            self._cursor = QCursor(Qt.CursorShape.WaitCursor)
        else:
            self._cursor = self._default_cursor

        self.setCursor(self._cursor)
        if self.canvas().mapTool() == self:
            self.canvas().setCursor(self._cursor)

    def canvasPressEvent(self, e: Optional[QgsMapMouseEvent]) -> None:
        assert e is not None
        if e.button() != Qt.MouseButton.LeftButton:
            return

        self._pressed_position = e.pos()
        self._last_position = e.pos()

    def canvasMoveEvent(self, e: Optional[QgsMapMouseEvent]) -> None:
        assert e is not None
        if (
            not bool(e.buttons() & Qt.MouseButton.LeftButton)
            or self._pressed_position is None
        ):
            return

        self._last_position = e.pos()

        if (
            self._last_position - self._pressed_position
        ).manhattanLength() < 3:
            return

        self.__pan_action_start(self._pressed_position)
        self.__pan_action()

    def canvasReleaseEvent(self, e: Optional[QgsMapMouseEvent]) -> None:
        assert e is not None
        if e.button() != Qt.MouseButton.LeftButton:
            return

        if self._is_pan_action_started:
            self.__pan_action_end(e.pos())
        else:
            self.__process_point(e.pos())

        self._pressed_position = None
        self._last_position = None

        self.canvas().setCursor(self._cursor)

    def __pan_action_start(self, release_point: QPoint) -> None:
        if self._is_pan_action_started:
            return

        self._is_pan_action_started = True
        self.canvas().setCursor(QCursor(Qt.CursorShape.ClosedHandCursor))

    def __pan_action(self) -> None:
        if not self._is_pan_action_started:
            return

        self.__move_canvas_contents()

    def __pan_action_end(self, release_point: QPoint) -> None:
        self.__move_canvas_contents(reset=True)

        if self._pressed_position is None:
            return

        # Get the drag start and end positions in screen coordinates.
        start_screen = self._pressed_position
        end_screen = release_point

        # Convert screen coordinates to map coordinates.
        start_map = (
            self.canvas()
            .getCoordinateTransform()
            .toMapCoordinates(start_screen)
        )
        end_map = (
            self.canvas().getCoordinateTransform().toMapCoordinates(end_screen)
        )

        # Calculate the pan offset.
        dx = end_map.x() - start_map.x()
        dy = end_map.y() - start_map.y()

        # Update the canvas center using the computed offset.
        center = self.canvas().center()
        new_center = QgsPointXY(center.x() - dx, center.y() - dy)
        self.canvas().setCenter(new_center)

        self.canvas().refresh()

        self._is_pan_action_started = False

    def __move_canvas_contents(self, *, reset: bool = False) -> None:
        point = QPoint(0, 0)

        if not reset:
            assert self._pressed_position is not None
            assert self._last_position is not None
            point += self._last_position - self._pressed_position

        viewport = self.canvas().viewport()
        width = viewport.size().width()
        height = viewport.size().height()
        self.canvas().setSceneRect(-point.x(), -point.y(), width, height)

    def __process_point(self, point: QPoint) -> None:
        map_point = (
            self.canvas().getCoordinateTransform().toMapCoordinates(point)
        )
        self._click_renderer.start_point_animation(map_point)

        target_crs = QgsCoordinateReferenceSystem.fromEpsgId(4326)

        transform = QgsCoordinateTransform(
            self.canvas().mapSettings().destinationCrs(),
            target_crs,
            QgsProject.instance(),
        )
        result = transform.transform(map_point)

        self.identify_point.emit(
            QgsPointXY(
                round(result.x(), POINT_PRECISION),
                round(result.y(), POINT_PRECISION),
            )
        )

    @pyqtSlot(QgsPointXY)
    def _log_position(self, point: QgsPointXY) -> None:
        logger.debug(f"Clicked point: {point.toString(POINT_PRECISION)}")
