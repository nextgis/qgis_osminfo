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

from math import hypot, sqrt

import pytest
from qgis.core import QgsRectangle

from osminfo.openstreetmap.max_scale_calculator import (
    OsmElementMaxScaleCalculator,
)
from osminfo.openstreetmap.models import OsmBounds, OsmGeometryType


def test_calculate_uses_bbox_diagonal_for_polygon_scale() -> None:
    calculator = OsmElementMaxScaleCalculator()
    bounds = OsmBounds(0.0, 0.0, 0.03, 0.04)
    bbox = QgsRectangle(0.0, 0.0, 0.03, 0.04)

    max_scale = calculator.calculate(
        OsmGeometryType.POLYGON,
        bounds,
        bbox,
    )

    assert max_scale == pytest.approx(
        hypot(0.03, 0.04)
        * calculator._METERS_PER_DEGREE_LAT
        / (
            calculator._MIN_VISIBLE_DIAGONAL_PIXELS[OsmGeometryType.POLYGON]
            * calculator._MAP_UNITS_PER_PIXEL
        )
    )
    assert calculator._MIN_VISIBLE_DIAGONAL_PIXELS[
        OsmGeometryType.POLYGON
    ] == pytest.approx(20.0 * sqrt(2.0))


def test_calculate_preserves_collection_threshold_from_overview_logic() -> (
    None
):
    calculator = OsmElementMaxScaleCalculator()
    bounds = OsmBounds(30.0, 60.0, 30.2, 60.2)
    bbox = QgsRectangle(30.0, 60.0, 30.2, 60.2)

    max_scale = calculator.calculate(
        OsmGeometryType.COLLECTION,
        bounds,
        bbox,
    )

    assert max_scale is not None
    assert calculator._MIN_VISIBLE_DIAGONAL_PIXELS[
        OsmGeometryType.COLLECTION
    ] == pytest.approx(18.0 * sqrt(2.0))
