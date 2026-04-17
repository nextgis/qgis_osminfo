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
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Tuple

from osminfo.core.exceptions import (
    OsmInfoNominatimGeocodeError,
    OsmInfoQueryBuilderError,
)
from osminfo.overpass.query_builder.query_context import QueryContext


@dataclass(frozen=True)
class QueryGeocodingData:
    id_queries: Tuple[str, ...] = tuple()
    area_queries: Tuple[str, ...] = tuple()
    bbox_queries: Tuple[str, ...] = tuple()
    coordinate_queries: Tuple[str, ...] = tuple()

    def has_requests(self) -> bool:
        return any(
            (
                len(self.id_queries) > 0,
                len(self.area_queries) > 0,
                len(self.bbox_queries) > 0,
                len(self.coordinate_queries) > 0,
            )
        )


class QueryPostprocessor:
    _DATE_PATTERN = re.compile(r"\{\{date(?::(.*?))?\}\}")
    _RELATIVE_DATE_PATTERN = re.compile(
        r"(-?\d+) ?"
        r"(seconds?|minutes?|hours?|days?|weeks?|months?|years?)?"
    )
    _SHORTCUT_DEFINITION_PATTERN = re.compile(r"\{\{([^{}=]+?)=(.+?)\}\}")
    _SHORTCUT_PLACEHOLDER_PATTERN = re.compile(r"\{\{([^{}:]+?)\}\}")
    _GEOCODE_ID_PATTERN = re.compile(r"\{\{geocodeId:(.+?)\}\}")
    _GEOCODE_AREA_PATTERN = re.compile(r"\{\{geocodeArea:(.+?)\}\}")
    _GEOCODE_BBOX_PATTERN = re.compile(r"\{\{geocodeBbox:(.+?)\}\}")
    _GEOCODE_COORDS_PATTERN = re.compile(r"\{\{geocodeCoords:(.+?)\}\}")
    _SECONDS_PER_UNIT = {
        "second": 1,
        "seconds": 1,
        "minute": 60,
        "minutes": 60,
        "hour": 3600,
        "hours": 3600,
        "day": 86400,
        "days": 86400,
        "week": 604800,
        "weeks": 604800,
        "month": 2628000,
        "months": 2628000,
        "year": 31536000,
        "years": 31536000,
    }

    @staticmethod
    def extract_geocoding_data(queries: List[str]) -> QueryGeocodingData:
        id_queries = []
        area_queries = []
        bbox_queries = []
        coordinate_queries = []
        for query in queries:
            id_queries.extend(
                match.strip()
                for match in QueryPostprocessor._GEOCODE_ID_PATTERN.findall(
                    query
                )
            )
            area_queries.extend(
                match.strip()
                for match in QueryPostprocessor._GEOCODE_AREA_PATTERN.findall(
                    query
                )
            )
            bbox_queries.extend(
                match.strip()
                for match in QueryPostprocessor._GEOCODE_BBOX_PATTERN.findall(
                    query
                )
            )
            coordinate_queries.extend(
                match.strip()
                for match in QueryPostprocessor._GEOCODE_COORDS_PATTERN.findall(
                    query
                )
            )

        return QueryGeocodingData(
            id_queries=tuple(dict.fromkeys(id_queries)),
            area_queries=tuple(dict.fromkeys(area_queries)),
            bbox_queries=tuple(dict.fromkeys(bbox_queries)),
            coordinate_queries=tuple(dict.fromkeys(coordinate_queries)),
        )

    def process(self, queries: List[str], context: QueryContext) -> List[str]:
        processed_queries: List[str] = []
        for query in queries:
            processed_query = self._replace_shortcuts(query)
            processed_query = processed_query.replace(
                "{{bbox}}",
                QueryContext.format_bbox(context.bbox),
            )
            processed_query = processed_query.replace(
                "{{center}}",
                QueryContext.format_center_point(context.center),
            )
            processed_query = self._replace_dates(processed_query)
            processed_query = self._replace_geocode_ids(
                processed_query,
                context,
            )
            processed_query = self._replace_geocode_areas(
                processed_query,
                context,
            )
            processed_query = self._replace_geocode_bboxes(
                processed_query,
                context,
            )
            processed_query = self._replace_geocode_coords(
                processed_query,
                context,
            )
            self._validate_uninitialized_shortcuts(processed_query)
            processed_query = self._cleanup_query(processed_query)
            processed_queries.append(processed_query)

        return processed_queries

    def _replace_shortcuts(self, query: str) -> str:
        shortcut_values: Dict[str, str] = {}
        for match in self._SHORTCUT_DEFINITION_PATTERN.finditer(query):
            shortcut_name = match.group(1).strip()
            shortcut_value = match.group(2).strip()
            shortcut_values[shortcut_name] = shortcut_value

        query = self._SHORTCUT_DEFINITION_PATTERN.sub("", query)

        for shortcut_name, shortcut_value in shortcut_values.items():
            query = query.replace(
                f"{{{{{shortcut_name}}}}}",
                shortcut_value,
            )

        return query

    def _validate_uninitialized_shortcuts(self, query: str) -> None:
        unresolved_shortcuts = [
            match.strip()
            for match in self._SHORTCUT_PLACEHOLDER_PATTERN.findall(query)
        ]
        if len(unresolved_shortcuts) == 0:
            return

        placeholder_name = unresolved_shortcuts[0]
        raise OsmInfoQueryBuilderError(
            log_message=(
                f"Shortcut placeholder is not initialized: {placeholder_name}"
            ),
            user_message=(
                f"Shortcut placeholder '{placeholder_name}' is not "
                "initialized."
            ),
        )

    @staticmethod
    def _cleanup_query(query: str) -> str:
        query = re.sub(r"\n{3,}", "\n\n", query)
        return query.strip()

    def _replace_dates(self, query: str) -> str:
        def _replace(match: re.Match) -> str:
            raw_value = match.group(1)
            if raw_value is None:
                return self._relative_date_to_iso("")

            return self._relative_date_to_iso(raw_value.strip())

        return self._DATE_PATTERN.sub(_replace, query)

    def _relative_date_to_iso(self, value: str) -> str:
        normalized_value = value.lower()
        if len(normalized_value) == 0:
            normalized_value = "0 seconds"

        match = self._RELATIVE_DATE_PATTERN.fullmatch(normalized_value)
        if match is None:
            raise OsmInfoQueryBuilderError(
                log_message=(f"Invalid date placeholder expression: {value}"),
                user_message="Date placeholder is invalid.",
            )

        count = int(match.group(1))
        unit = match.group(2) or "days"
        interval_seconds = self._SECONDS_PER_UNIT.get(unit)
        if interval_seconds is None:
            raise OsmInfoQueryBuilderError(
                log_message=(f"Unsupported date placeholder unit: {unit}"),
                user_message="Date placeholder unit is invalid.",
            )

        relative_delta = timedelta(seconds=count * interval_seconds)
        timestamp = datetime.now(timezone.utc) - relative_delta
        return timestamp.isoformat(timespec="milliseconds").replace(
            "+00:00",
            "Z",
        )

    def _replace_geocode_areas(
        self,
        query: str,
        context: QueryContext,
    ) -> str:
        def _replace(match: re.Match) -> str:
            search_text = match.group(1).strip()
            replacement = context.geocode_areas.get(search_text)
            if replacement is None:
                raise OsmInfoNominatimGeocodeError(
                    log_message=(
                        f"Missing geocoded area for query: {search_text}"
                    ),
                    user_message=(
                        f"Failed to geocode area for '{search_text}'."
                    ),
                )
            return replacement

        return self._GEOCODE_AREA_PATTERN.sub(_replace, query)

    def _replace_geocode_ids(
        self,
        query: str,
        context: QueryContext,
    ) -> str:
        def _replace(match: re.Match) -> str:
            search_text = match.group(1).strip()
            replacement = context.geocode_ids.get(search_text)
            if replacement is None:
                raise OsmInfoNominatimGeocodeError(
                    log_message=(
                        f"Missing geocoded id for query: {search_text}"
                    ),
                    user_message=(
                        f"Failed to geocode id for '{search_text}'."
                    ),
                )
            return replacement

        return self._GEOCODE_ID_PATTERN.sub(_replace, query)

    def _replace_geocode_bboxes(
        self,
        query: str,
        context: QueryContext,
    ) -> str:
        def _replace(match: re.Match) -> str:
            search_text = match.group(1).strip()
            replacement = context.geocode_bboxes.get(search_text)
            if replacement is None:
                raise OsmInfoNominatimGeocodeError(
                    log_message=(
                        "Missing geocoded bounding box for query: "
                        f"{search_text}"
                    ),
                    user_message=(
                        f"Failed to geocode bounding box for '{search_text}'."
                    ),
                )
            return replacement

        return self._GEOCODE_BBOX_PATTERN.sub(_replace, query)

    def _replace_geocode_coords(
        self,
        query: str,
        context: QueryContext,
    ) -> str:
        def _replace(match: re.Match) -> str:
            search_text = match.group(1).strip()
            replacement = context.geocode_coords.get(search_text)
            if replacement is None:
                raise OsmInfoNominatimGeocodeError(
                    log_message=(
                        "Missing geocoded coordinates for query: "
                        f"{search_text}"
                    ),
                    user_message=(
                        f"Failed to geocode coordinates for '{search_text}'."
                    ),
                )
            return replacement

        return self._GEOCODE_COORDS_PATTERN.sub(_replace, query)
