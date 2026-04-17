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

from typing import ClassVar, Optional

from qgis.core import QgsGeometry, QgsPointXY
from qgis.gui import QgsMapCanvas, QgsRubberBand
from qgis.PyQt.QtCore import QObject, QVariantAnimation
from qgis.PyQt.QtGui import QColor

from osminfo.compat import GeometryType
from osminfo.core.constants import OSM_COLOR


class OsmInfoClickRenderer(QObject):
    """Render a temporary highlighted point on the map canvas."""

    POINT_SIZE: ClassVar[int] = 15
    POINT_STROKE_WIDTH: ClassVar[int] = 3
    STROKE_COLOR_ALPHA: ClassVar[int] = 150
    ANIMATION_DURATION: ClassVar[int] = 1000

    def __init__(
        self, canvas: QgsMapCanvas, parent: Optional[QObject] = None
    ) -> None:
        super().__init__(parent)
        self._canvas = canvas

        self._point_color = QColor(OSM_COLOR)
        self._point_color.setAlpha(self.STROKE_COLOR_ALPHA)

        self._point_rubber_band = self._create_point_rubber_band()
        self._point_fade_animation = QVariantAnimation(self)
        self._point_fade_animation.setDuration(self.ANIMATION_DURATION)
        self._point_fade_animation.setStartValue(self._point_color.alpha())
        self._point_fade_animation.setEndValue(0)
        self._point_fade_animation.valueChanged.connect(
            self._on_point_fade_animation_value_changed
        )
        self._point_fade_animation.finished.connect(
            self._on_point_fade_animation_finished
        )

    def __del__(self) -> None:
        self.clear()

    def clear(self) -> None:
        self._point_fade_animation.stop()
        self._point_rubber_band.reset(GeometryType.Point)
        self._point_rubber_band.setColor(self._point_color)

    def start_point_animation(self, point: QgsPointXY) -> None:
        """Highlight the selected point geometry.

        Display the point geometry on the canvas and start the fade-out
        animation for the temporary marker.

        :param point: Point geometry to highlight.
        """
        geometry = QgsGeometry.fromPointXY(point)
        self._point_rubber_band.reset(GeometryType.Point)
        self._point_rubber_band.setToGeometry(
            geometry,
            self._canvas.mapSettings().destinationCrs(),
        )
        self._point_rubber_band.update()
        self._start_fade_animation()

    def _create_point_rubber_band(self) -> QgsRubberBand:
        rubber_band = QgsRubberBand(self._canvas, GeometryType.Point)
        rubber_band.setIcon(QgsRubberBand.IconType.ICON_CIRCLE)
        rubber_band.setColor(self._point_color)
        rubber_band.setIconSize(self.POINT_SIZE)
        rubber_band.setWidth(self.POINT_STROKE_WIDTH)
        return rubber_band

    def _start_fade_animation(self) -> None:
        """Start the fade-out animation for the point rubber band.

        Restart the shared animation and fade the point rubber band to
        transparent.
        """
        self._point_fade_animation.stop()
        self._point_fade_animation.setStartValue(self._point_color.alpha())
        self._point_fade_animation.setEndValue(0)
        self._point_rubber_band.setColor(self._point_color)
        self._point_fade_animation.start()

    def _on_point_fade_animation_value_changed(self, value: int) -> None:
        """Apply the current animation alpha to the point rubber band.

        :param value: Alpha value produced by the fade animation.
        """
        color = QColor(self._point_color)
        color.setAlpha(value)
        self._point_rubber_band.setColor(color)
        self._point_rubber_band.update()

    def _on_point_fade_animation_finished(self) -> None:
        self.clear()
