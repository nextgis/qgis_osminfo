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

from math import cos, hypot, radians, sqrt
from typing import Optional

from qgis.core import QgsRectangle

from osminfo.openstreetmap.models import OsmBounds, OsmGeometryType

POLYGON_CENTROID_MARKER_SIZE_PIXELS = 16.0
POLYGON_CENTROID_MARKER_OUTLINE_WIDTH_PIXELS = 2.0
POLYGON_CENTROID_OUTER_DIAMETER_PIXELS = (
    POLYGON_CENTROID_MARKER_SIZE_PIXELS
    + 2.0 * POLYGON_CENTROID_MARKER_OUTLINE_WIDTH_PIXELS
)

MIN_VISIBLE_DIAGONAL_PIXELS_BY_GEOMETRY = {
    OsmGeometryType.LINESTRING: 12.0 * sqrt(2.0),
    OsmGeometryType.POLYGON: (
        POLYGON_CENTROID_OUTER_DIAMETER_PIXELS * sqrt(2.0)
    ),
    OsmGeometryType.COLLECTION: 18.0 * sqrt(2.0),
}
DEFAULT_MIN_VISIBLE_DIAGONAL_PIXELS = 16.0 * sqrt(2.0)


class OsmElementMaxScaleCalculator:
    _METERS_PER_DEGREE_LAT = 111320.0
    _MAP_UNITS_PER_PIXEL = 0.00028
    _MIN_VISIBLE_DIAGONAL_PIXELS = MIN_VISIBLE_DIAGONAL_PIXELS_BY_GEOMETRY

    def calculate(
        self,
        geometry_type: Optional[OsmGeometryType],
        bounds: Optional[OsmBounds],
        bbox: Optional[QgsRectangle],
    ) -> Optional[float]:
        if geometry_type in (None, OsmGeometryType.POINT):
            return None

        rectangle = self._resolve_rectangle(bounds, bbox)
        if rectangle is None:
            return None

        width_degrees = abs(rectangle.xMaximum() - rectangle.xMinimum())
        height_degrees = abs(rectangle.yMaximum() - rectangle.yMinimum())
        if width_degrees == 0.0 and height_degrees == 0.0:
            return None

        center_latitude = (rectangle.yMinimum() + rectangle.yMaximum()) / 2.0
        longitude_factor = max(cos(radians(center_latitude)), 0.01)
        width_meters = (
            width_degrees * self._METERS_PER_DEGREE_LAT * longitude_factor
        )
        height_meters = height_degrees * self._METERS_PER_DEGREE_LAT
        diagonal_meters = hypot(width_meters, height_meters)

        min_visible_pixels = self._MIN_VISIBLE_DIAGONAL_PIXELS.get(
            geometry_type,
            DEFAULT_MIN_VISIBLE_DIAGONAL_PIXELS,
        )
        if diagonal_meters <= 0.0 or min_visible_pixels <= 0.0:
            return None

        return diagonal_meters / (
            min_visible_pixels * self._MAP_UNITS_PER_PIXEL
        )

    def _resolve_rectangle(
        self,
        bounds: Optional[OsmBounds],
        bbox: Optional[QgsRectangle],
    ) -> Optional[QgsRectangle]:
        if bounds is not None:
            return bounds.to_qgs_rectangle()

        if bbox is not None:
            return QgsRectangle(bbox)

        return None
