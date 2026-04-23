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

from collections import OrderedDict
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

from qgis.core import (
    QgsCoordinateReferenceSystem,
    QgsDistanceArea,
    QgsGeometry,
    QgsPointXY,
    QgsProject,
)

from osminfo.core.logging import logger
from osminfo.openstreetmap.max_scale_calculator import (
    OsmElementMaxScaleCalculator,
)
from osminfo.openstreetmap.models import (
    OsmBounds,
    OsmElement,
    OsmElementType,
    OsmGeometry,
    OsmGeometryCollection,
    OsmGeometryType,
    OsmRelationRef,
    OsmResultGroup,
    OsmResultGroupType,
    OsmResultTree,
    OsmTag,
    osm_geometry_type_from_qgs,
)
from osminfo.openstreetmap.tag2link import TagLinkResolver
from osminfo.openstreetmap.title_builder import OsmElementTitleBuilder
from osminfo.overpass.json_parser import (
    DEFAULT_POLYGON_RULES,
    OverpassJsonParser,
    PolygonRuleMode,
)

SQ_METERS_IN_SQ_KILOMETER = 1000000.0


@dataclass(frozen=True)
class _GeometryCacheRule:
    bucket_key: str
    max_entries: int
    required_tags: Tuple[
        Tuple[str, Optional[Tuple[str, ...]]],
        ...,
    ]


GEOMETRY_CACHE_RULES = (
    _GeometryCacheRule(
        bucket_key="admin_level:2",
        max_entries=3,
        required_tags=(("admin_level", ("2",)),),
    ),
    _GeometryCacheRule(
        bucket_key="admin_level:3",
        max_entries=5,
        required_tags=(("admin_level", ("3",)),),
    ),
    _GeometryCacheRule(
        bucket_key="admin_level:4",
        max_entries=5,
        required_tags=(("admin_level", ("4",)),),
    ),
    _GeometryCacheRule(
        bucket_key="admin_level:5",
        max_entries=10,
        required_tags=(("admin_level", ("5",)),),
    ),
)


@dataclass(frozen=True)
class _CachedGeometryLoad:
    geometry: OsmGeometry
    display_geometry_type: Optional[OsmGeometryType]
    bounds: Optional[OsmBounds]
    max_scale: Optional[float]
    relation_refs: Tuple[OsmRelationRef, ...]
    relation_role: Optional[str]
    is_relation_member: bool
    is_incomplete: bool


_GEOMETRY_LOAD_CACHE_BUCKETS: Dict[
    str,
    "OrderedDict[Tuple[str, int], _CachedGeometryLoad]",
] = {
    cache_rule.bucket_key: OrderedDict() for cache_rule in GEOMETRY_CACHE_RULES
}


def _build_polygon_feature_map() -> Dict[str, Any]:
    polygon_features: Dict[str, Any] = {}
    for rule in DEFAULT_POLYGON_RULES:
        if rule.mode == PolygonRuleMode.ALL:
            polygon_features[rule.key] = True
            continue

        value_map = {value: True for value in rule.values}
        if rule.mode == PolygonRuleMode.WHITELIST:
            polygon_features[rule.key] = {"included_values": value_map}
            continue

        polygon_features[rule.key] = {"excluded_values": value_map}

    return polygon_features


DEFAULT_POLYGON_FEATURES = _build_polygon_feature_map()


class OsmFeaturesParser:
    def __init__(self, locale_name: str = "en") -> None:
        self._locale_name = locale_name or "en"
        self._tag_link_resolver = TagLinkResolver()
        self._title_builder = OsmElementTitleBuilder(self._locale_name)
        self._max_scale_calculator = OsmElementMaxScaleCalculator()
        self._distance_area = QgsDistanceArea()
        self._distance_area.setSourceCrs(
            QgsCoordinateReferenceSystem.fromEpsgId(4326),
            QgsProject.instance().transformContext(),
        )
        self._distance_area.setEllipsoid("WGS84")

    def parse_element(
        self,
        raw_element: Dict[str, Any],
        *,
        is_relation_member: bool = False,
        include_geometry: bool = True,
        geometry_area_limit_sq_km: Optional[float] = None,
    ) -> Optional[OsmElement]:
        parser = OverpassJsonParser.from_element(raw_element)
        return self._parse_element_with_parser(
            raw_element,
            parser,
            is_relation_member=is_relation_member,
            include_geometry=include_geometry,
            geometry_area_limit_sq_km=geometry_area_limit_sq_km,
        )

    def parse_elements_by_keys(
        self,
        raw_elements: Iterable[Dict[str, Any]],
        element_keys: Set[Tuple[str, int]],
        *,
        geometry_area_limit_sq_km: Optional[float] = None,
    ) -> Dict[Tuple[str, int], OsmElement]:
        raw_elements_list = list(raw_elements)
        requested_raw_elements = {
            element_key: raw_element
            for raw_element in raw_elements_list
            for element_key in [self._raw_element_key(raw_element)]
            if element_key is not None and element_key in element_keys
        }

        parsed_elements: Dict[Tuple[str, int], OsmElement] = {}
        remaining_keys: Set[Tuple[str, int]] = set()
        for element_key in element_keys:
            raw_element = requested_raw_elements.get(element_key)
            if raw_element is None:
                continue

            cached_element = self._cached_geometry_element(raw_element)
            if cached_element is not None:
                parsed_elements[element_key] = cached_element
                continue

            direct_element = self._parse_geometry_load_element_directly(
                raw_element,
                geometry_area_limit_sq_km=geometry_area_limit_sq_km,
            )
            if direct_element is not None:
                parsed_elements[element_key] = direct_element
                self._store_cached_geometry_element(
                    raw_element, direct_element
                )
                continue

            remaining_keys.add(element_key)

        if len(remaining_keys) == 0:
            return parsed_elements

        parser = OverpassJsonParser(raw_elements_list)
        for element_key in sorted(remaining_keys):
            raw_element = requested_raw_elements.get(element_key)
            if raw_element is None:
                continue

            try:
                parsed_element = self._parse_element_with_parser(
                    raw_element,
                    parser,
                    include_geometry=True,
                    geometry_area_limit_sq_km=geometry_area_limit_sq_km,
                )
            except Exception:
                logger.exception("Failed to parse Overpass element geometry")
                continue

            if parsed_element is None:
                continue

            parsed_elements[element_key] = parsed_element
            self._store_cached_geometry_element(raw_element, parsed_element)

        return parsed_elements

    @classmethod
    def clear_geometry_load_cache(cls) -> None:
        for cache_bucket in _GEOMETRY_LOAD_CACHE_BUCKETS.values():
            cache_bucket.clear()

    def parse_group(
        self,
        group_type: OsmResultGroupType,
        title: str,
        raw_elements: Iterable[Dict[str, Any]],
        *,
        sort_by_bounds_area: bool = False,
        include_geometry: bool = True,
        geometry_area_limit_sq_km: Optional[float] = None,
    ) -> OsmResultGroup:
        sorted_elements = list(raw_elements)
        if sort_by_bounds_area:
            sorted_elements.sort(key=self._bounds_area_sort_key)

        deferred_flags: List[bool] = []
        parser_elements: List[Dict[str, Any]] = []
        for raw_element in sorted_elements:
            should_defer = self._should_defer_element_without_parser(
                raw_element,
                include_geometry=include_geometry,
                geometry_area_limit_sq_km=geometry_area_limit_sq_km,
            )
            deferred_flags.append(should_defer)
            if should_defer:
                continue

            parser_elements.append(raw_element)

        parser = None
        if len(parser_elements) > 0:
            parser = OverpassJsonParser(parser_elements)

        elements: List[OsmElement] = []
        for index, raw_element in enumerate(sorted_elements):
            try:
                if deferred_flags[index]:
                    parsed_element = self._parse_deferred_element(raw_element)
                else:
                    assert parser is not None
                    parsed_element = self._parse_element_with_parser(
                        raw_element,
                        parser,
                        include_geometry=include_geometry,
                        geometry_area_limit_sq_km=geometry_area_limit_sq_km,
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

    def _should_defer_element_without_parser(
        self,
        raw_element: Dict[str, Any],
        *,
        include_geometry: bool,
        geometry_area_limit_sq_km: Optional[float],
    ) -> bool:
        if not include_geometry:
            return False

        element_type = self._parse_element_type(raw_element.get("type"))
        if element_type is None:
            return False

        bounds = OverpassJsonParser.parse_bounds(raw_element.get("bounds"))
        return self._should_defer_geometry_from_bounds(
            raw_element,
            element_type,
            bounds,
            geometry_area_limit_sq_km,
        )

    def _parse_deferred_element(
        self,
        raw_element: Dict[str, Any],
    ) -> Optional[OsmElement]:
        element_type = self._parse_element_type(raw_element.get("type"))
        if element_type is None:
            return None

        osm_id = self._parse_osm_id(raw_element)
        if osm_id is None:
            return None

        tags = self._parse_tags(raw_element.get("tags", {}))
        bounds = OverpassJsonParser.parse_bounds(raw_element.get("bounds"))
        relation_role = self._normalize_relation_role(raw_element.get("role"))
        preset_geometry_type = self._preset_geometry_type(
            raw_element,
            None,
            element_type,
        )
        display_geometry_type = self._display_geometry_type(
            None,
            preset_geometry_type,
        )

        element = OsmElement(
            osm_id=osm_id,
            element_type=element_type,
            title=self._title_builder.build(
                tags,
                osm_id,
                geometry_type=preset_geometry_type,
            ),
            geometry=None,
            display_geometry_type=display_geometry_type,
            tag_items=self._build_tag_items(tags),
            tags=tags,
            bounds=bounds,
            relation_refs=tuple(),
            relation_role=relation_role,
            is_relation_member=relation_role is not None,
            is_incomplete=False,
            is_geometry_deferred=True,
            raw_element=dict(raw_element),
        )
        element.max_scale = self._max_scale_calculator.calculate(
            geometry_type=element.geometry_type(),
            bounds=bounds,
            bbox=element.bounding_box(),
        )
        return element

    def parse_result_tree(
        self,
        nearby_elements: Iterable[Dict[str, Any]],
        enclosing_elements: Iterable[Dict[str, Any]],
        search_elements: Iterable[Dict[str, Any]],
        titles: Dict[OsmResultGroupType, str],
        *,
        include_geometry: bool = True,
        geometry_area_limit_sq_km: Optional[float] = None,
    ) -> OsmResultTree:
        groups: List[OsmResultGroup] = []

        search_group = self.parse_group(
            OsmResultGroupType.SEARCH,
            titles[OsmResultGroupType.SEARCH],
            search_elements,
            include_geometry=include_geometry,
            geometry_area_limit_sq_km=geometry_area_limit_sq_km,
        )
        if len(search_group.elements) > 0:
            groups.append(search_group)

        nearby_group = self.parse_group(
            OsmResultGroupType.NEARBY,
            titles[OsmResultGroupType.NEARBY],
            nearby_elements,
            include_geometry=include_geometry,
            geometry_area_limit_sq_km=geometry_area_limit_sq_km,
        )
        if len(nearby_group.elements) > 0:
            groups.append(nearby_group)

        enclosing_group = self.parse_group(
            OsmResultGroupType.ENCLOSING,
            titles[OsmResultGroupType.ENCLOSING],
            enclosing_elements,
            sort_by_bounds_area=True,
            include_geometry=include_geometry,
            geometry_area_limit_sq_km=geometry_area_limit_sq_km,
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
        include_geometry: bool = True,
        geometry_area_limit_sq_km: Optional[float] = None,
    ) -> Optional[OsmElement]:
        element_type = self._parse_element_type(raw_element.get("type"))
        if element_type is None:
            return None

        osm_id = self._parse_osm_id(raw_element)
        if osm_id is None:
            return None

        tags = self._parse_tags(raw_element.get("tags", {}))
        bounds = OverpassJsonParser.parse_bounds(raw_element.get("bounds"))
        if include_geometry and not is_relation_member:
            cached_element = self._cached_geometry_element(raw_element)
            if cached_element is not None:
                if not self._should_defer_geometry_from_bounds(
                    raw_element,
                    element_type,
                    bounds,
                    geometry_area_limit_sq_km,
                ):
                    return cached_element

        geometry = None
        is_geometry_deferred = False
        geometry_checked = False
        if include_geometry:
            if self._should_defer_geometry_from_bounds(
                raw_element,
                element_type,
                bounds,
                geometry_area_limit_sq_km,
            ):
                is_geometry_deferred = True
                geometry_checked = True
            else:
                cached_geometry = self._cached_geometry_entry(raw_element)
                if cached_geometry is not None:
                    geometry = self._clone_geometry(cached_geometry.geometry)
                    geometry_checked = True
                else:
                    geometry = parser.geometry_for_element(raw_element)
                    geometry_checked = True
                    if self._is_geometry_over_area_limit(
                        geometry,
                        geometry_area_limit_sq_km,
                    ):
                        geometry = None
                        is_geometry_deferred = True
        relation_refs = self._parse_relation_refs(
            parser.relation_refs_for_element(raw_element)
        )
        relation_role = self._resolve_relation_role(
            raw_element,
            relation_refs,
        )
        if is_geometry_deferred:
            is_incomplete = False
        else:
            is_incomplete = parser.is_incomplete_element_with_geometry(
                raw_element,
                geometry_checked=geometry_checked,
                geometry=geometry,
            )
        preset_geometry_type = self._preset_geometry_type(
            raw_element,
            geometry,
            element_type,
        )
        display_geometry_type = self._display_geometry_type(
            geometry,
            preset_geometry_type,
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
            display_geometry_type=display_geometry_type,
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
            is_geometry_deferred=is_geometry_deferred,
            raw_element=dict(raw_element),
        )

        element.max_scale = self._max_scale_calculator.calculate(
            geometry_type=element.geometry_type(),
            bounds=bounds,
            bbox=element.bounding_box(),
        )
        self._store_cached_geometry_element(raw_element, element)
        return element

    def _raw_element_key(
        self,
        raw_element: Dict[str, Any],
    ) -> Optional[Tuple[str, int]]:
        element_type = self._parse_element_type(raw_element.get("type"))
        if element_type is None:
            return None

        osm_id = self._parse_osm_id(raw_element)
        if osm_id is None:
            return None

        return (element_type.value, osm_id)

    def _cached_geometry_element(
        self,
        raw_element: Dict[str, Any],
    ) -> Optional[OsmElement]:
        cached_geometry = self._cached_geometry_entry(raw_element)
        if cached_geometry is None:
            return None

        return self._build_geometry_load_element(
            raw_element,
            geometry=self._clone_geometry(cached_geometry.geometry),
            bounds=cached_geometry.bounds,
            display_geometry_type=cached_geometry.display_geometry_type,
            max_scale=cached_geometry.max_scale,
            relation_refs=cached_geometry.relation_refs,
            relation_role=cached_geometry.relation_role,
            is_relation_member=cached_geometry.is_relation_member,
            is_incomplete=cached_geometry.is_incomplete,
        )

    def _store_cached_geometry_element(
        self,
        raw_element: Dict[str, Any],
        element: OsmElement,
    ) -> None:
        cache_bucket = self._cache_bucket_for_raw_element(raw_element)
        if cache_bucket is None:
            return

        if element.geometry is None or element.is_geometry_deferred:
            return

        element_key = self._raw_element_key(raw_element)
        if element_key is None or element.geometry is None:
            return

        cache_bucket[element_key] = _CachedGeometryLoad(
            geometry=self._clone_geometry(element.geometry),
            display_geometry_type=element.display_geometry_type,
            bounds=element.bounds,
            max_scale=element.max_scale,
            relation_refs=element.relation_refs,
            relation_role=element.relation_role,
            is_relation_member=element.is_relation_member,
            is_incomplete=element.is_incomplete,
        )
        cache_bucket.move_to_end(element_key)

        cache_rule = self._cache_rule_for_raw_element(raw_element)
        assert cache_rule is not None
        bucket_limit = cache_rule.max_entries
        while len(cache_bucket) > bucket_limit:
            cache_bucket.popitem(last=False)

    def _cached_geometry_entry(
        self,
        raw_element: Dict[str, Any],
    ) -> Optional[_CachedGeometryLoad]:
        cache_bucket = self._cache_bucket_for_raw_element(raw_element)
        if cache_bucket is None:
            return None

        element_key = self._raw_element_key(raw_element)
        if element_key is None:
            return None

        cached_geometry = cache_bucket.get(element_key)
        if cached_geometry is None:
            return None

        cache_bucket.move_to_end(element_key)
        return cached_geometry

    def _cache_bucket_for_raw_element(
        self,
        raw_element: Dict[str, Any],
    ) -> Optional["OrderedDict[Tuple[str, int], _CachedGeometryLoad]"]:
        cache_rule = self._cache_rule_for_raw_element(raw_element)
        if cache_rule is None:
            return None

        return _GEOMETRY_LOAD_CACHE_BUCKETS[cache_rule.bucket_key]

    def _cache_rule_for_raw_element(
        self,
        raw_element: Dict[str, Any],
    ) -> Optional[_GeometryCacheRule]:
        raw_tags = raw_element.get("tags")
        if not isinstance(raw_tags, dict):
            return None

        for cache_rule in GEOMETRY_CACHE_RULES:
            if self._matches_cache_rule(raw_tags, cache_rule):
                return cache_rule

        return None

    def _matches_cache_rule(
        self,
        raw_tags: Dict[str, Any],
        cache_rule: _GeometryCacheRule,
    ) -> bool:
        for tag_name, allowed_values in cache_rule.required_tags:
            raw_value = raw_tags.get(tag_name)
            if raw_value is None:
                return False

            if allowed_values is None:
                continue

            if str(raw_value) not in allowed_values:
                return False

        return True

    def _clone_geometry(
        self,
        geometry: OsmGeometry,
    ) -> OsmGeometry:
        if isinstance(geometry, QgsGeometry):
            return QgsGeometry(geometry)

        return OsmGeometryCollection(
            points=(
                QgsGeometry(geometry.points)
                if geometry.points is not None
                else None
            ),
            lines=(
                QgsGeometry(geometry.lines)
                if geometry.lines is not None
                else None
            ),
            polygons=(
                QgsGeometry(geometry.polygons)
                if geometry.polygons is not None
                else None
            ),
        )

    def _build_geometry_load_element(
        self,
        raw_element: Dict[str, Any],
        *,
        geometry: Optional[OsmGeometry],
        bounds: Optional[OsmBounds],
        display_geometry_type: Optional[OsmGeometryType],
        max_scale: Optional[float],
        relation_refs: Tuple[OsmRelationRef, ...] = tuple(),
        relation_role: Optional[str] = None,
        is_relation_member: bool = False,
        is_incomplete: bool = False,
        is_geometry_deferred: bool = False,
    ) -> Optional[OsmElement]:
        element_type = self._parse_element_type(raw_element.get("type"))
        if element_type is None:
            return None

        osm_id = self._parse_osm_id(raw_element)
        if osm_id is None:
            return None

        tags = self._parse_tags(raw_element.get("tags", {}))
        preset_geometry_type = self._preset_geometry_type(
            raw_element,
            geometry,
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
            display_geometry_type=display_geometry_type,
            max_scale=max_scale,
            tag_items=self._build_tag_items(tags),
            tags=tags,
            bounds=bounds,
            relation_refs=relation_refs,
            relation_role=relation_role,
            is_relation_member=is_relation_member,
            is_incomplete=is_incomplete,
            is_geometry_deferred=is_geometry_deferred,
            raw_element=dict(raw_element),
        )
        if element.max_scale is None:
            element.max_scale = self._max_scale_calculator.calculate(
                geometry_type=element.geometry_type(),
                bounds=bounds,
                bbox=element.bounding_box(),
            )

        return element

    def _parse_geometry_load_element_directly(
        self,
        raw_element: Dict[str, Any],
        *,
        geometry_area_limit_sq_km: Optional[float],
    ) -> Optional[OsmElement]:
        direct_geometry = self._direct_geometry_for_raw_element(raw_element)
        if direct_geometry is None:
            return None

        bounds = OverpassJsonParser.parse_bounds(raw_element.get("bounds"))
        element_type = self._parse_element_type(raw_element.get("type"))
        if element_type is None:
            return None

        preset_geometry_type = self._preset_geometry_type(
            raw_element,
            direct_geometry,
            element_type,
        )
        display_geometry_type = self._display_geometry_type(
            direct_geometry,
            preset_geometry_type,
        )

        if self._is_geometry_over_area_limit(
            direct_geometry,
            geometry_area_limit_sq_km,
        ):
            return self._build_geometry_load_element(
                raw_element,
                geometry=None,
                bounds=bounds,
                display_geometry_type=display_geometry_type,
                max_scale=self._max_scale_calculator.calculate(
                    geometry_type=display_geometry_type,
                    bounds=bounds,
                    bbox=bounds.to_qgs_rectangle()
                    if bounds is not None
                    else None,
                ),
                is_geometry_deferred=True,
            )

        return self._build_geometry_load_element(
            raw_element,
            geometry=direct_geometry,
            bounds=bounds,
            display_geometry_type=display_geometry_type,
            max_scale=None,
        )

    def _direct_geometry_for_raw_element(
        self,
        raw_element: Dict[str, Any],
    ) -> Optional[OsmGeometry]:
        element_type = self._parse_element_type(raw_element.get("type"))
        if element_type == OsmElementType.NODE:
            longitude = self._float_value(raw_element.get("lon"))
            latitude = self._float_value(raw_element.get("lat"))
            if longitude is None or latitude is None:
                return None

            return QgsGeometry.fromPointXY(QgsPointXY(longitude, latitude))

        if element_type == OsmElementType.WAY:
            return self._direct_way_geometry(raw_element)

        if element_type == OsmElementType.RELATION:
            return self._direct_relation_geometry(raw_element)

        return None

    def _direct_way_geometry(
        self,
        raw_way: Dict[str, Any],
    ) -> Optional[QgsGeometry]:
        path = self._coordinate_path_from_raw_geometry(raw_way.get("geometry"))
        if path is None or len(path) < 2:
            return None

        points = [QgsPointXY(point[1], point[0]) for point in path]
        if self._is_raw_polygon_way(raw_way) and len(points) >= 4:
            return QgsGeometry.fromPolygonXY([points])

        return QgsGeometry.fromPolylineXY(points)

    def _direct_relation_geometry(
        self,
        raw_relation: Dict[str, Any],
    ) -> Optional[OsmGeometry]:
        raw_tags = raw_relation.get("tags")
        if not isinstance(raw_tags, dict):
            return None

        relation_type = str(raw_tags.get("type", "")).lower()
        if relation_type not in ("multipolygon", "boundary"):
            return None

        raw_members = raw_relation.get("members")
        if not isinstance(raw_members, list):
            return None

        outer_paths: List[List[Tuple[float, float]]] = []
        inner_paths: List[List[Tuple[float, float]]] = []
        point_members: List[QgsPointXY] = []
        for raw_member in raw_members:
            if not isinstance(raw_member, dict):
                return None

            member_type = self._parse_element_type(raw_member.get("type"))
            if member_type == OsmElementType.NODE:
                longitude = self._float_value(raw_member.get("lon"))
                latitude = self._float_value(raw_member.get("lat"))
                if longitude is None or latitude is None:
                    continue

                point_members.append(QgsPointXY(longitude, latitude))
                continue

            if member_type != OsmElementType.WAY:
                continue

            path = self._coordinate_path_from_raw_geometry(
                raw_member.get("geometry")
            )
            if path is None or len(path) < 2:
                return None

            role = str(raw_member.get("role", "outer")).lower()
            if role == "inner":
                inner_paths.append(path)
            else:
                outer_paths.append(path)

        if len(outer_paths) == 0:
            return None

        outer_rings = self._join_coordinate_paths(outer_paths)
        inner_rings = self._join_coordinate_paths(inner_paths)
        multipolygon = [[ring] for ring in outer_rings]
        for inner_ring in inner_rings:
            outer_index = self._find_outer_coordinate_ring(
                outer_rings,
                inner_ring,
            )
            if outer_index is None:
                continue

            multipolygon[outer_index].append(inner_ring)

        polygons: List[List[List[QgsPointXY]]] = []
        for ring_group in multipolygon:
            polygon_rings: List[List[QgsPointXY]] = []
            for ring in ring_group:
                if len(ring) < 4:
                    continue

                polygon_rings.append(
                    [QgsPointXY(point[1], point[0]) for point in ring]
                )

            if len(polygon_rings) > 0:
                polygons.append(polygon_rings)

        if len(polygons) == 0:
            return None

        polygon_geometry = QgsGeometry.fromMultiPolygonXY(polygons)
        if len(polygons) == 1:
            polygon_geometry = QgsGeometry.fromPolygonXY(polygons[0])

        if len(point_members) == 0:
            return polygon_geometry

        return OsmGeometryCollection(
            points=QgsGeometry.fromMultiPointXY(point_members),
            polygons=polygon_geometry,
        )

    def _coordinate_path_from_raw_geometry(
        self,
        raw_geometry: Any,
    ) -> Optional[List[Tuple[float, float]]]:
        if not isinstance(raw_geometry, list):
            return None

        path: List[Tuple[float, float]] = []
        for raw_vertex in raw_geometry:
            if not isinstance(raw_vertex, dict):
                return None

            longitude = self._float_value(raw_vertex.get("lon"))
            latitude = self._float_value(raw_vertex.get("lat"))
            if longitude is None or latitude is None:
                return None

            path.append((latitude, longitude))

        return path

    def _join_coordinate_paths(
        self,
        paths: List[List[Tuple[float, float]]],
    ) -> List[List[Tuple[float, float]]]:
        remaining_paths = [list(path) for path in paths if len(path) > 0]
        endpoint_index: Dict[Tuple[float, float], List[int]] = {}
        unused_indexes = set(range(len(remaining_paths)))
        for index, path in enumerate(remaining_paths):
            self._index_coordinate_path(endpoint_index, path, index)

        joined: List[List[Tuple[float, float]]] = []
        while len(unused_indexes) > 0:
            current_index = max(unused_indexes)
            unused_indexes.remove(current_index)
            self._remove_coordinate_path(
                endpoint_index, remaining_paths[current_index], current_index
            )
            current = list(remaining_paths[current_index])
            joined.append(current)
            while len(unused_indexes) > 0 and current[0] != current[-1]:
                first_point = current[0]
                last_point = current[-1]
                matched_path: Optional[List[Tuple[float, float]]] = None
                matched_index = -1
                insert_at_start = False
                for candidate_index in self._candidate_coordinate_path_indexes(
                    endpoint_index,
                    first_point,
                    last_point,
                ):
                    if candidate_index not in unused_indexes:
                        continue

                    candidate_path = remaining_paths[candidate_index]
                    if last_point == candidate_path[0]:
                        matched_path = candidate_path[1:]
                        matched_index = candidate_index
                        break

                    if last_point == candidate_path[-1]:
                        matched_path = list(reversed(candidate_path[:-1]))
                        matched_index = candidate_index
                        break

                    if first_point == candidate_path[-1]:
                        matched_path = candidate_path[:-1]
                        matched_index = candidate_index
                        insert_at_start = True
                        break

                    if first_point == candidate_path[0]:
                        matched_path = list(reversed(candidate_path[1:]))
                        matched_index = candidate_index
                        insert_at_start = True
                        break

                if matched_path is None or matched_index < 0:
                    break

                unused_indexes.remove(matched_index)
                self._remove_coordinate_path(
                    endpoint_index,
                    remaining_paths[matched_index],
                    matched_index,
                )
                if insert_at_start:
                    current[0:0] = matched_path
                else:
                    current.extend(matched_path)

        return joined

    def _candidate_coordinate_path_indexes(
        self,
        endpoint_index: Dict[Tuple[float, float], List[int]],
        first_point: Tuple[float, float],
        last_point: Tuple[float, float],
    ) -> List[int]:
        candidate_indexes: List[int] = []
        seen_indexes = set()
        for point in (last_point, first_point):
            for index in endpoint_index.get(point, []):
                if index in seen_indexes:
                    continue

                seen_indexes.add(index)
                candidate_indexes.append(index)

        return candidate_indexes

    def _index_coordinate_path(
        self,
        endpoint_index: Dict[Tuple[float, float], List[int]],
        path: List[Tuple[float, float]],
        index: int,
    ) -> None:
        endpoint_index.setdefault(path[0], []).append(index)
        if path[-1] != path[0]:
            endpoint_index.setdefault(path[-1], []).append(index)

    def _remove_coordinate_path(
        self,
        endpoint_index: Dict[Tuple[float, float], List[int]],
        path: List[Tuple[float, float]],
        index: int,
    ) -> None:
        for point in (path[0], path[-1]):
            indexes = endpoint_index.get(point)
            if indexes is None:
                continue

            endpoint_index[point] = [
                candidate_index
                for candidate_index in indexes
                if candidate_index != index
            ]
            if len(endpoint_index[point]) == 0:
                endpoint_index.pop(point, None)

    def _find_outer_coordinate_ring(
        self,
        outer_rings: List[List[Tuple[float, float]]],
        inner_ring: List[Tuple[float, float]],
    ) -> Optional[int]:
        for index, outer_ring in enumerate(outer_rings):
            if self._polygon_intersects_coordinate_polygon(
                outer_ring,
                inner_ring,
            ):
                return index

        return None

    def _polygon_intersects_coordinate_polygon(
        self,
        outer_ring: List[Tuple[float, float]],
        inner_ring: List[Tuple[float, float]],
    ) -> bool:
        for point in inner_ring:
            if self._coordinate_point_in_polygon(point, outer_ring):
                return True

        return False

    def _coordinate_point_in_polygon(
        self,
        point: Tuple[float, float],
        polygon: List[Tuple[float, float]],
    ) -> bool:
        x_value = point[0]
        y_value = point[1]
        is_inside = False
        for index in range(len(polygon)):
            previous_index = index - 1
            xi = polygon[index][0]
            yi = polygon[index][1]
            xj = polygon[previous_index][0]
            yj = polygon[previous_index][1]
            intersects = (yi > y_value) != (yj > y_value) and x_value < (
                xj - xi
            ) * (y_value - yi) / (yj - yi) + xi
            if intersects:
                is_inside = not is_inside

        return is_inside

    def _float_value(self, value: Any) -> Optional[float]:
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    def _display_geometry_type(
        self,
        geometry: Optional[OsmGeometry],
        preset_geometry_type: Optional[str],
    ) -> Optional[OsmGeometryType]:
        if geometry is not None:
            if isinstance(geometry, QgsGeometry):
                return osm_geometry_type_from_qgs(geometry)

            geometry_type = geometry.geometry_type()
            if geometry_type is not None:
                return geometry_type

        if preset_geometry_type == "point":
            return OsmGeometryType.POINT

        if preset_geometry_type == "line":
            return OsmGeometryType.LINESTRING

        if preset_geometry_type == "area":
            return OsmGeometryType.POLYGON

        if preset_geometry_type == "relation":
            return OsmGeometryType.COLLECTION

        return None

    def _is_geometry_over_area_limit(
        self,
        geometry: Optional[OsmGeometry],
        geometry_area_limit_sq_km: Optional[float],
    ) -> bool:
        if geometry is None or geometry_area_limit_sq_km is None:
            return False

        qgs_geometry = self._primary_qgs_geometry(geometry)
        if qgs_geometry is None:
            return False

        if qgs_geometry.type() != OsmGeometryType.POLYGON.value:
            return False

        return (
            self._geometry_area_sq_km(qgs_geometry) > geometry_area_limit_sq_km
        )

    def _primary_qgs_geometry(
        self,
        geometry: OsmGeometry,
    ) -> Optional[QgsGeometry]:
        if isinstance(geometry, QgsGeometry):
            return geometry

        return geometry.primary_geometry()

    def _geometry_area_sq_km(self, geometry: QgsGeometry) -> float:
        return (
            self._distance_area.measureArea(geometry)
            / SQ_METERS_IN_SQ_KILOMETER
        )

    def _should_defer_geometry_from_bounds(
        self,
        raw_element: Dict[str, Any],
        element_type: OsmElementType,
        bounds: Optional[OsmBounds],
        geometry_area_limit_sq_km: Optional[float],
    ) -> bool:
        if geometry_area_limit_sq_km is None or bounds is None:
            return False

        if not self._is_bounds_based_area_candidate(raw_element, element_type):
            return False

        return self._bounds_area_sq_km(bounds) > geometry_area_limit_sq_km

    def _is_bounds_based_area_candidate(
        self,
        raw_element: Dict[str, Any],
        element_type: OsmElementType,
    ) -> bool:
        if element_type == OsmElementType.WAY:
            return self._is_raw_polygon_way(raw_element)

        if element_type != OsmElementType.RELATION:
            return False

        raw_tags = raw_element.get("tags")
        if not isinstance(raw_tags, dict):
            return False

        return str(raw_tags.get("type", "")).lower() in (
            "multipolygon",
            "boundary",
        )

    def _bounds_area_sq_km(self, bounds: OsmBounds) -> float:
        bounds_geometry = QgsGeometry.fromPolygonXY(
            [
                [
                    QgsPointXY(bounds.minlon, bounds.minlat),
                    QgsPointXY(bounds.maxlon, bounds.minlat),
                    QgsPointXY(bounds.maxlon, bounds.maxlat),
                    QgsPointXY(bounds.minlon, bounds.maxlat),
                    QgsPointXY(bounds.minlon, bounds.minlat),
                ]
            ]
        )
        return self._geometry_area_sq_km(bounds_geometry)

    def _preset_geometry_type(
        self,
        raw_element: Dict[str, Any],
        geometry: Optional[OsmGeometry],
        element_type: OsmElementType,
    ) -> Optional[str]:
        if element_type == OsmElementType.NODE:
            return "point"

        geometry_type = self._display_geometry_type(geometry, None)
        geometry_name = None if geometry_type is None else geometry_type.name

        if element_type == OsmElementType.WAY:
            if geometry_name in ("POLYGON", "COLLECTION"):
                return "area"

            if self._is_raw_polygon_way(raw_element):
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

        if geometry_name in ("POLYGON", "COLLECTION"):
            return "area"

        return "relation"

    def _is_raw_polygon_way(self, raw_element: Dict[str, Any]) -> bool:
        raw_geometry = raw_element.get("geometry")
        if isinstance(raw_geometry, list) and len(raw_geometry) > 1:
            first_vertex = raw_geometry[0]
            last_vertex = raw_geometry[-1]
            if isinstance(first_vertex, dict) and isinstance(
                last_vertex, dict
            ):
                if first_vertex.get("lat") == last_vertex.get(
                    "lat"
                ) and first_vertex.get("lon") == last_vertex.get("lon"):
                    return self._is_polygon_tags(raw_element)

        raw_nodes = raw_element.get("nodes")
        if isinstance(raw_nodes, list) and len(raw_nodes) > 1:
            if raw_nodes[0] == raw_nodes[-1]:
                return self._is_polygon_tags(raw_element)

        return bool(raw_element.get("bounds")) and self._is_polygon_tags(
            raw_element
        )

    def _is_polygon_tags(self, raw_element: Dict[str, Any]) -> bool:
        raw_tags = raw_element.get("tags")
        if not isinstance(raw_tags, dict):
            return False

        if raw_tags.get("area") == "no":
            return False

        for key, value in raw_tags.items():
            polygon_rule = DEFAULT_POLYGON_FEATURES.get(key)
            if polygon_rule is None or value == "no":
                continue

            if polygon_rule is True:
                return True

            included_values = polygon_rule.get("included_values")
            if isinstance(included_values, dict) and included_values.get(
                value
            ):
                return True

            excluded_values = polygon_rule.get("excluded_values")
            if isinstance(excluded_values, dict) and not excluded_values.get(
                value
            ):
                return True

        return False

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
        raw_relation_refs: Any,
    ) -> Tuple[OsmRelationRef, ...]:
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
