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

from typing import Any, Dict, Iterable, List, Optional, Tuple

from osminfo.logging import logger
from osminfo.openstreetmap.max_scale_calculator import (
    OsmElementMaxScaleCalculator,
)
from osminfo.openstreetmap.models import (
    OsmElement,
    OsmElementType,
    OsmRelationRef,
    OsmResultGroup,
    OsmResultGroupType,
    OsmResultTree,
    OsmTag,
)
from osminfo.openstreetmap.tag2link import TagLinkResolver
from osminfo.openstreetmap.title_builder import OsmElementTitleBuilder
from osminfo.overpass.json_parser import OverpassJsonParser


class OsmFeaturesParser:
    def __init__(self, locale_name: str = "en") -> None:
        self._locale_name = locale_name or "en"
        self._tag_link_resolver = TagLinkResolver()
        self._title_builder = OsmElementTitleBuilder(self._locale_name)
        self._max_scale_calculator = OsmElementMaxScaleCalculator()

    def parse_element(
        self,
        raw_element: Dict[str, Any],
        *,
        is_relation_member: bool = False,
    ) -> Optional[OsmElement]:
        parser = OverpassJsonParser.from_element(raw_element)
        return self._parse_element_with_parser(
            raw_element,
            parser,
            is_relation_member=is_relation_member,
        )

    def parse_group(
        self,
        group_type: OsmResultGroupType,
        title: str,
        raw_elements: Iterable[Dict[str, Any]],
        *,
        sort_by_bounds_area: bool = False,
    ) -> OsmResultGroup:
        sorted_elements = list(raw_elements)
        if sort_by_bounds_area:
            sorted_elements.sort(key=self._bounds_area_sort_key)

        parser = OverpassJsonParser(sorted_elements)

        elements: List[OsmElement] = []
        for raw_element in sorted_elements:
            try:
                parsed_element = self._parse_element_with_parser(
                    raw_element,
                    parser,
                )
            except Exception:
                logger.exception("Failed to parse Overpass element")
                continue

            if parsed_element is None:
                continue

            elements.append(parsed_element)

        return OsmResultGroup(
            group_type=group_type,
            title=title,
            elements=tuple(elements),
        )

    def parse_result_tree(
        self,
        nearby_elements: Iterable[Dict[str, Any]],
        enclosing_elements: Iterable[Dict[str, Any]],
        search_elements: Iterable[Dict[str, Any]],
        titles: Dict[OsmResultGroupType, str],
    ) -> OsmResultTree:
        groups: List[OsmResultGroup] = []

        search_group = self.parse_group(
            OsmResultGroupType.SEARCH,
            titles[OsmResultGroupType.SEARCH],
            search_elements,
        )
        if len(search_group.elements) > 0:
            groups.append(search_group)

        nearby_group = self.parse_group(
            OsmResultGroupType.NEARBY,
            titles[OsmResultGroupType.NEARBY],
            nearby_elements,
        )
        if len(nearby_group.elements) > 0:
            groups.append(nearby_group)

        enclosing_group = self.parse_group(
            OsmResultGroupType.ENCLOSING,
            titles[OsmResultGroupType.ENCLOSING],
            enclosing_elements,
            sort_by_bounds_area=True,
        )
        if len(enclosing_group.elements) > 0:
            groups.append(enclosing_group)

        return OsmResultTree(groups=tuple(groups))

    def _parse_element_with_parser(
        self,
        raw_element: Dict[str, Any],
        parser: OverpassJsonParser,
        *,
        is_relation_member: bool = False,
    ) -> Optional[OsmElement]:
        element_type = self._parse_element_type(raw_element.get("type"))
        if element_type is None:
            return None

        osm_id = self._parse_osm_id(raw_element)
        if osm_id is None:
            return None

        tags = self._parse_tags(raw_element.get("tags", {}))
        feature = parser.feature_for_element(raw_element)
        geometry = parser.geometry_for_element(raw_element)
        bounds = OverpassJsonParser.parse_bounds(raw_element.get("bounds"))
        relation_refs = self._parse_relation_refs(feature)
        relation_role = self._resolve_relation_role(
            raw_element,
            relation_refs,
        )
        is_incomplete = parser.is_incomplete_element(raw_element)
        preset_geometry_type = self._preset_geometry_type(
            raw_element,
            feature,
            element_type,
        )

        element = OsmElement(
            osm_id=osm_id,
            element_type=element_type,
            title=self._title_builder.build(
                tags,
                osm_id,
                geometry_type=preset_geometry_type,
            ),
            geometry=geometry,
            tag_items=self._build_tag_items(tags),
            tags=tags,
            bounds=bounds,
            relation_refs=relation_refs,
            relation_role=relation_role,
            is_relation_member=(
                is_relation_member
                or relation_role is not None
                or len(relation_refs) > 0
            ),
            is_incomplete=is_incomplete,
        )

        element.max_scale = self._max_scale_calculator.calculate(
            geometry_type=element.geometry_type(),
            bounds=bounds,
            bbox=element.bounding_box(),
        )
        return element

    def _preset_geometry_type(
        self,
        raw_element: Dict[str, Any],
        feature: Optional[Dict[str, Any]],
        element_type: OsmElementType,
    ) -> Optional[str]:
        if element_type == OsmElementType.NODE:
            return "point"

        geometry = feature.get("geometry") if feature is not None else None
        geometry_name = None
        if isinstance(geometry, dict):
            geometry_name = geometry.get("type")

        if element_type == OsmElementType.WAY:
            if geometry_name in ("Polygon", "MultiPolygon"):
                return "area"

            return "line"

        if element_type != OsmElementType.RELATION:
            return None

        tags = raw_element.get("tags")
        relation_type = None
        if isinstance(tags, dict):
            relation_type = tags.get("type")

        if relation_type in ("multipolygon", "boundary"):
            return "area"

        if geometry_name in ("Polygon", "MultiPolygon"):
            return "area"

        return "relation"

    def _parse_element_type(self, value: Any) -> Optional[OsmElementType]:
        if value is None:
            return None

        try:
            return OsmElementType(str(value).lower())
        except ValueError:
            return None

    def _parse_osm_id(self, raw_element: Dict[str, Any]) -> Optional[int]:
        raw_identifier = raw_element.get("id", raw_element.get("ref"))
        if raw_identifier is None:
            return None

        try:
            return int(raw_identifier)
        except (TypeError, ValueError):
            return None

    def _parse_tags(self, raw_tags: Any) -> Dict[str, str]:
        if not isinstance(raw_tags, dict):
            return {}

        tags: Dict[str, str] = {}
        for key, value in raw_tags.items():
            normalized_key = self._normalize_optional_text(key)
            normalized_value = self._normalize_optional_text(value)
            if normalized_key is None or normalized_value is None:
                continue

            tags[normalized_key] = normalized_value

        return tags

    def _build_tag_items(
        self,
        tags: Dict[str, str],
    ) -> Tuple[OsmTag, ...]:
        tag_items = []
        for key, value in sorted(tags.items()):
            links = self._tag_link_resolver.resolve(
                key,
                value,
                self._locale_name,
            )
            tag_items.append(OsmTag(key=key, value=value, links=links))

        return tuple(tag_items)

    def _parse_relation_refs(
        self,
        feature: Optional[Dict[str, Any]],
    ) -> Tuple[OsmRelationRef, ...]:
        if not isinstance(feature, dict):
            return tuple()

        properties = feature.get("properties")
        if not isinstance(properties, dict):
            return tuple()

        raw_relation_refs = properties.get("relations")
        if not isinstance(raw_relation_refs, list):
            return tuple()

        relation_refs: List[OsmRelationRef] = []
        for raw_relation_ref in raw_relation_refs:
            if not isinstance(raw_relation_ref, dict):
                continue

            relation_id = self._parse_raw_relation_id(raw_relation_ref)
            if relation_id is None:
                continue

            relation_refs.append(
                OsmRelationRef(
                    relation_id=relation_id,
                    role=self._normalize_relation_role(
                        raw_relation_ref.get("role")
                    ),
                    relation_tags=self._parse_tags(
                        raw_relation_ref.get("reltags")
                    ),
                )
            )

        return tuple(relation_refs)

    def _parse_raw_relation_id(
        self,
        raw_relation_ref: Dict[str, Any],
    ) -> Optional[int]:
        raw_identifier = raw_relation_ref.get("rel")
        if raw_identifier is None:
            return None

        try:
            return int(raw_identifier)
        except (TypeError, ValueError):
            return None

    def _bounds_area_sort_key(
        self,
        raw_element: Dict[str, Any],
    ) -> Tuple[int, float]:
        bounds = OverpassJsonParser.parse_bounds(raw_element.get("bounds"))
        if bounds is None:
            return (1, 0.0)

        return (0, bounds.area)

    def _normalize_optional_text(self, value: Any) -> Optional[str]:
        if value is None:
            return None

        return str(value)

    def _normalize_relation_role(self, value: Any) -> Optional[str]:
        normalized_value = self._normalize_optional_text(value)
        if normalized_value is None:
            return None

        if len(normalized_value) == 0:
            return None

        return normalized_value

    def _resolve_relation_role(
        self,
        raw_element: Dict[str, Any],
        relation_refs: Tuple[OsmRelationRef, ...],
    ) -> Optional[str]:
        raw_role = self._normalize_relation_role(raw_element.get("role"))
        if raw_role is not None:
            return raw_role

        relation_roles = {
            relation_ref.role
            for relation_ref in relation_refs
            if relation_ref.role is not None
        }
        if len(relation_roles) != 1:
            return None

        return next(iter(relation_roles))
