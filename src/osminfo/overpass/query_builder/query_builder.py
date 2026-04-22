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

import re
from typing import List, Optional

from qgis.core import QgsApplication, QgsPointXY

from osminfo.core.exceptions import OsmInfoQueryBuilderError
from osminfo.overpass.query_builder.coordinates_query_strategy import (
    CoordinatesQueryStrategy,
)
from osminfo.overpass.query_builder.overpass_ql_query_strategy import (
    OverpassQlQueryStrategy,
)
from osminfo.overpass.query_builder.wizard_query_strategy import (
    WizardQueryStrategy,
)
from osminfo.settings.osm_info_settings import OsmInfoSettings

COORDINATES_PATTERN = re.compile(
    r"^\s*"
    r"(?P<longitude>[+-]?(?:\d+(?:\.\d+)?|\.\d+))"
    r"\s*,\s*"
    r"(?P<latitude>[+-]?(?:\d+(?:\.\d+)?|\.\d+))"
    r"\s*$"
)


class QueryBuilder:
    """Build Overpass QL queries from user input strings or coordinates."""

    def __init__(self, settings: Optional[OsmInfoSettings] = None) -> None:
        self._settings = settings or OsmInfoSettings()
        self._coordinates_strategy = CoordinatesQueryStrategy(self._settings)
        self._string_strategies = [
            OverpassQlQueryStrategy(self._settings),
            WizardQueryStrategy(settings=self._settings),
        ]
        self._last_strategy_name = ""

    @property
    def last_strategy_name(self) -> str:
        return self._last_strategy_name

    def build_for_coords(self, point: QgsPointXY) -> List[str]:
        self._last_strategy_name = "coords"
        return self._coordinates_strategy.build(point)

    @classmethod
    def parse_coordinates(cls, search_string: str) -> Optional[QgsPointXY]:
        normalized_search_string = search_string.strip()
        if len(normalized_search_string) == 0:
            return None

        match = COORDINATES_PATTERN.fullmatch(search_string)
        if match is None:
            return None

        longitude = match.group("longitude")
        latitude = match.group("latitude")
        return QgsPointXY(float(longitude), float(latitude))

    def build_for_string(self, search_string: str) -> List[str]:
        normalized_search_string = search_string.strip()
        if len(normalized_search_string) == 0:
            # fmt: off
            message = QgsApplication.translate(
                "Exceptions",
                "Search string is empty"
            )
            # fmt: on
            raise OsmInfoQueryBuilderError(
                log_message="Search string is empty",
                user_message=message,
            )

        point = self.parse_coordinates(normalized_search_string)
        if point is not None:
            return self.build_for_coords(point)

        for strategy in self._string_strategies:
            queries = strategy.build(normalized_search_string)
            if len(queries) == 0:
                continue

            self._last_strategy_name = strategy.NAME
            return queries

        # fmt: off
        message = QgsApplication.translate(
            "Exceptions",
            "Unsupported search string. Provide coordinates or Overpass QL"
        )
        # fmt: on
        raise OsmInfoQueryBuilderError(
            log_message=(
                f"No query strategy accepted search string: "
                f"{normalized_search_string}"
            ),
            user_message=message,
            detail=normalized_search_string,
        )

    def repair_search(self, search_string: str) -> Optional[str]:
        normalized_search_string = search_string.strip()
        if len(normalized_search_string) == 0:
            return None

        if self.parse_coordinates(normalized_search_string) is not None:
            return None

        for strategy in self._string_strategies:
            repaired_search = strategy.repair_search(normalized_search_string)
            if repaired_search is None:
                continue

            return repaired_search

        return None
