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

from decimal import Decimal
from typing import List, Optional, Tuple

from qgis.core import QgsApplication, QgsPointXY

from osminfo.core.exceptions import OsmInfoQueryBuilderError
from osminfo.overpass.query_builder.query_header import QueryHeaderBuilder
from osminfo.settings.osm_info_settings import OsmInfoSettings


class CoordinatesQueryStrategy:
    def __init__(self, settings: Optional[OsmInfoSettings] = None) -> None:
        self._settings = settings or OsmInfoSettings()
        self._query_header_builder = QueryHeaderBuilder(self._settings)

    def build(self, point: QgsPointXY) -> List[str]:
        longitude, latitude = self._validate_point(point)
        queries: List[str] = []
        query_header = self._build_query_header()

        if self._settings.fetch_nearby:
            queries.append(
                self._build_nearby_query(
                    query_header,
                    longitude,
                    latitude,
                )
            )

        if self._settings.fetch_enclosing:
            queries.append(
                self._build_enclosing_query(
                    query_header,
                    longitude,
                    latitude,
                )
            )

        if len(queries) == 0:
            message = QgsApplication.translate(
                "Exceptions",
                "No object category selected in settings.",
            )
            raise OsmInfoQueryBuilderError(
                log_message="No coordinate query kinds are enabled",
                user_message=message,
            )

        return queries

    def _build_query_header(self) -> str:
        return self._query_header_builder.build()

    def _validate_point(self, point: QgsPointXY) -> Tuple[str, str]:
        try:
            longitude_value = float(point.x())
            latitude_value = float(point.y())
        except (AttributeError, TypeError, ValueError) as error:
            raise self._build_invalid_coordinates_error(
                point,
                detail=str(error),
            ) from error

        if abs(longitude_value) > 180 or abs(latitude_value) > 90:
            raise self._build_invalid_coordinates_error(point)

        longitude = self._format_coordinate(longitude_value)
        latitude = self._format_coordinate(latitude_value)
        return longitude, latitude

    def _build_invalid_coordinates_error(
        self,
        point: QgsPointXY,
        detail: Optional[str] = None,
    ) -> OsmInfoQueryBuilderError:
        message = QgsApplication.translate(
            "Exceptions",
            "{longitude}, {latitude} are wrong coords!",
        ).format(
            longitude=self._format_coordinate(point.x()),
            latitude=self._format_coordinate(point.y()),
        )
        return OsmInfoQueryBuilderError(
            log_message="Coordinates are out of range",
            user_message=message,
            detail=detail,
        )

    @staticmethod
    def _format_coordinate(value: float) -> str:
        return format(Decimal(str(value)), "f").rstrip("0").rstrip(".")

    def _build_nearby_query(
        self,
        query_header: str,
        longitude: str,
        latitude: str,
    ) -> str:
        distance = self._settings.distance
        return "\n".join(
            [
                query_header,
                "(",
                f"    node(around:{distance},{latitude},{longitude});",
                f"    way(around:{distance},{latitude},{longitude});",
                f"    relation(around:{distance},{latitude},{longitude});",
                ");",
                "out tags geom;",
            ]
        )

    def _build_enclosing_query(
        self,
        query_header: str,
        longitude: str,
        latitude: str,
    ) -> str:
        return "\n".join(
            [
                query_header,
                f"is_in({latitude},{longitude})->.a;",
                "way(pivot.a)->.b;",
                ".b out tags geom;",
                ".b <;",
                "out geom;",
                "relation(pivot.a);",
                "out geom;",
            ]
        )
