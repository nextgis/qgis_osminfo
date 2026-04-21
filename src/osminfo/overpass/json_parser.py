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

from copy import deepcopy
from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple

from qgis.core import QgsGeometry, QgsPointXY

from osminfo.core.compat import GeometryType
from osminfo.openstreetmap.models import (
    OsmBounds,
    OsmElementType,
    OsmGeometry,
    OsmGeometryCollection,
)

RawElement = Dict[str, Any]
Feature = Dict[str, Any]
_PolygonFeatureMap = Dict[str, Any]

DEFAULT_UNINTERESTING_TAGS = frozenset(
    {
        "source",
        "source_ref",
        "source:ref",
        "history",
        "attribution",
        "created_by",
        "tiger:county",
        "tiger:tlid",
        "tiger:upload_uuid",
    }
)


class PolygonRuleMode(str, Enum):
    ALL = "all"
    WHITELIST = "whitelist"
    BLACKLIST = "blacklist"


@dataclass(frozen=True)
class PolygonFeatureRule:
    key: str
    mode: PolygonRuleMode
    values: Tuple[str, ...] = tuple()


DEFAULT_POLYGON_RULES: Tuple[PolygonFeatureRule, ...] = (
    PolygonFeatureRule("building", PolygonRuleMode.ALL),
    PolygonFeatureRule(
        "highway",
        PolygonRuleMode.WHITELIST,
        ("services", "rest_area", "escape", "elevator"),
    ),
    PolygonFeatureRule(
        "natural",
        PolygonRuleMode.BLACKLIST,
        ("coastline", "cliff", "ridge", "arete", "tree_row"),
    ),
    PolygonFeatureRule("landuse", PolygonRuleMode.ALL),
    PolygonFeatureRule(
        "waterway",
        PolygonRuleMode.WHITELIST,
        ("riverbank", "dock", "boatyard", "dam"),
    ),
    PolygonFeatureRule("amenity", PolygonRuleMode.ALL),
    PolygonFeatureRule("leisure", PolygonRuleMode.ALL),
    PolygonFeatureRule(
        "barrier",
        PolygonRuleMode.WHITELIST,
        (
            "city_wall",
            "ditch",
            "hedge",
            "retaining_wall",
            "wall",
            "spikes",
        ),
    ),
    PolygonFeatureRule(
        "railway",
        PolygonRuleMode.WHITELIST,
        ("station", "turntable", "roundhouse", "platform"),
    ),
    PolygonFeatureRule("area", PolygonRuleMode.ALL),
    PolygonFeatureRule("boundary", PolygonRuleMode.ALL),
    PolygonFeatureRule(
        "man_made",
        PolygonRuleMode.BLACKLIST,
        ("cutline", "embankment", "pipeline"),
    ),
    PolygonFeatureRule(
        "power",
        PolygonRuleMode.WHITELIST,
        ("plant", "substation", "generator", "transformer"),
    ),
    PolygonFeatureRule("place", PolygonRuleMode.ALL),
    PolygonFeatureRule("shop", PolygonRuleMode.ALL),
    PolygonFeatureRule(
        "aeroway",
        PolygonRuleMode.BLACKLIST,
        ("taxiway",),
    ),
    PolygonFeatureRule("tourism", PolygonRuleMode.ALL),
    PolygonFeatureRule("historic", PolygonRuleMode.ALL),
    PolygonFeatureRule("public_transport", PolygonRuleMode.ALL),
    PolygonFeatureRule("office", PolygonRuleMode.ALL),
    PolygonFeatureRule("building:part", PolygonRuleMode.ALL),
    PolygonFeatureRule("military", PolygonRuleMode.ALL),
    PolygonFeatureRule("ruins", PolygonRuleMode.ALL),
    PolygonFeatureRule("area:highway", PolygonRuleMode.ALL),
    PolygonFeatureRule("craft", PolygonRuleMode.ALL),
    PolygonFeatureRule("golf", PolygonRuleMode.ALL),
    PolygonFeatureRule("indoor", PolygonRuleMode.ALL),
)


@dataclass(frozen=True)
class _RelationRef:
    role: Optional[str]
    rel: int
    reltags: Dict[str, Any]


def _build_polygon_features(
    rules: Iterable[PolygonFeatureRule],
) -> _PolygonFeatureMap:
    polygon_features: _PolygonFeatureMap = {}
    for rule in rules:
        if rule.mode == PolygonRuleMode.ALL:
            polygon_features[rule.key] = True
            continue

        value_map = {value: True for value in rule.values}
        if rule.mode == PolygonRuleMode.WHITELIST:
            polygon_features[rule.key] = {"included_values": value_map}
            continue

        polygon_features[rule.key] = {"excluded_values": value_map}

    return polygon_features


class OverpassJsonParser:
    def __init__(
        self,
        raw_elements: Iterable[RawElement],
        *,
        flat_properties: bool = True,
        uninteresting_tags: Optional[Any] = None,
        polygon_features: Optional[Any] = None,
        deduplicator: Optional[
            Callable[[RawElement, RawElement], RawElement]
        ] = None,
    ) -> None:
        self._raw_elements = tuple(raw_elements)
        self._flat_properties = flat_properties
        self._uninteresting_tags = (
            DEFAULT_UNINTERESTING_TAGS
            if uninteresting_tags is None
            else uninteresting_tags
        )
        self._polygon_features = (
            _build_polygon_features(DEFAULT_POLYGON_RULES)
            if polygon_features is None
            else polygon_features
        )
        self._deduplicator = deduplicator or self._default_deduplicator
        self._nodes: List[RawElement] = []
        self._ways: List[RawElement] = []
        self._relations: List[RawElement] = []
        self._node_index: Dict[Any, RawElement] = {}
        self._way_index: Dict[Any, RawElement] = {}
        self._relation_index: Dict[Any, RawElement] = {}
        self._relation_membership_map = {
            OsmElementType.NODE: {},
            OsmElementType.WAY: {},
            OsmElementType.RELATION: {},
        }
        self._feature_index: Dict[str, Feature] = {}
        self._cached_features: Optional[List[Feature]] = None
        self._prepare_elements()

    @classmethod
    def from_response(
        cls,
        response: Dict[str, Any],
        **kwargs: Any,
    ) -> "OverpassJsonParser":
        raw_elements = response.get("elements", [])
        if not isinstance(raw_elements, list):
            raw_elements = []

        return cls(raw_elements, **kwargs)

    @classmethod
    def from_element(
        cls,
        raw_element: RawElement,
        **kwargs: Any,
    ) -> "OverpassJsonParser":
        return cls((raw_element,), **kwargs)

    @staticmethod
    def parse_bounds(raw_bounds: Any) -> Optional[OsmBounds]:
        if not isinstance(raw_bounds, dict):
            return None

        minlon = OverpassJsonParser._float_or_none(raw_bounds.get("minlon"))
        minlat = OverpassJsonParser._float_or_none(raw_bounds.get("minlat"))
        maxlon = OverpassJsonParser._float_or_none(raw_bounds.get("maxlon"))
        maxlat = OverpassJsonParser._float_or_none(raw_bounds.get("maxlat"))
        if None in (minlon, minlat, maxlon, maxlat):
            return None

        assert minlon is not None
        assert minlat is not None
        assert maxlon is not None
        assert maxlat is not None

        return OsmBounds(
            minlon=minlon,
            minlat=minlat,
            maxlon=maxlon,
            maxlat=maxlat,
        )

    def to_feature_collection(
        self,
        feature_callback: Optional[Callable[[Feature], None]] = None,
    ) -> Any:
        if feature_callback is not None:
            self._feature_index = {}
            self._build_features(feature_callback)
            return True

        self._ensure_features_built()
        assert self._cached_features is not None

        feature_collection = {
            "type": "FeatureCollection",
            "features": deepcopy(self._cached_features),
        }
        if self._flat_properties:
            self._flatten_feature_properties(feature_collection)

        return self._rewind_feature_collection(feature_collection)

    def geometry_for_element(
        self,
        raw_element: RawElement,
    ) -> Optional[OsmGeometry]:
        element_type = self._parse_element_type(raw_element.get("type"))
        feature = self.feature_for_element(raw_element)
        if feature is not None:
            feature_geometry = self._geometry_from_feature(feature)
            if element_type != OsmElementType.RELATION:
                return feature_geometry

            return self._merge_relation_member_points(
                feature_geometry,
                raw_element,
            )

        if element_type != OsmElementType.RELATION:
            return None

        return self._generic_relation_geometry(raw_element)

    def feature_for_element(
        self,
        raw_element: RawElement,
    ) -> Optional[Feature]:
        self._ensure_features_built()
        element_type = str(raw_element.get("type", "")).lower()
        element_id = self._raw_identifier(raw_element)
        if element_id is None:
            return None

        feature = self._feature_index.get(f"{element_type}/{element_id}")
        if feature is not None:
            return deepcopy(feature)

        if self._parse_element_type(element_type) != OsmElementType.RELATION:
            return None

        relation = self._relation_index.get(element_id)
        if relation is None:
            relation = deepcopy(raw_element)

        relation_tags = relation.get("tags", {})
        if not isinstance(relation_tags, dict):
            return None

        relation_kind = str(relation_tags.get("type", "")).lower()
        if relation_kind in ("route", "waterway"):
            feature = self._construct_route_feature(relation)
            if feature is not None:
                return feature

        if relation_kind in ("multipolygon", "boundary"):
            feature = self._construct_multipolygon_feature(
                relation,
                relation,
                force_relation_identifier=True,
            )
            if feature is not None:
                return self._rewind_feature(feature)

        return None

    def is_incomplete_element(self, raw_element: RawElement) -> bool:
        element_type = self._parse_element_type(raw_element.get("type"))
        feature = self.feature_for_element(raw_element)
        if feature is not None:
            properties = feature.get("properties")
            if (
                isinstance(properties, dict)
                and properties.get("tainted") is True
            ):
                return True

        if element_type == OsmElementType.RELATION:
            if self._relation_has_incomplete_members(raw_element):
                return True

        geometry = self.geometry_for_element(raw_element)
        return geometry is None and element_type != OsmElementType.NODE

    def _prepare_elements(self) -> None:
        for raw_element in self._raw_elements:
            if not isinstance(raw_element, dict):
                continue

            element_type = self._parse_element_type(raw_element.get("type"))
            if element_type == OsmElementType.NODE:
                self._nodes.append(raw_element)
                continue

            if element_type == OsmElementType.WAY:
                way = deepcopy(raw_element)
                way["nodes"] = deepcopy(raw_element.get("nodes"))
                self._ways.append(way)
                self._prepare_way(way)
                continue

            if element_type != OsmElementType.RELATION:
                continue

            relation = deepcopy(raw_element)
            relation["members"] = deepcopy(raw_element.get("members"))
            self._relations.append(relation)
            self._prepare_relation(relation)

    def _prepare_way(self, way: RawElement) -> None:
        if isinstance(way.get("center"), dict):
            self._add_center_geometry(way)

        if isinstance(way.get("geometry"), list):
            self._add_full_geometry_way(way)
            return

        if isinstance(way.get("bounds"), dict):
            self._add_bounds_geometry(way)

    def _prepare_relation(self, relation: RawElement) -> None:
        members = relation.get("members")
        has_full_geometry = False
        if isinstance(members, list):
            for member in members:
                if not isinstance(member, dict):
                    continue

                member_type = self._parse_element_type(member.get("type"))
                if member_type == OsmElementType.NODE:
                    if member.get("lat") is not None:
                        has_full_geometry = True
                        break
                    continue

                geometry = member.get("geometry")
                if (
                    member_type == OsmElementType.WAY
                    and isinstance(geometry, list)
                    and len(geometry) > 0
                ):
                    has_full_geometry = True
                    break

        if isinstance(relation.get("center"), dict):
            self._add_center_geometry(relation)

        if has_full_geometry:
            self._add_full_geometry_relation(relation)
            return

        if isinstance(relation.get("bounds"), dict):
            self._add_bounds_geometry(relation)

    def _add_center_geometry(self, raw_object: RawElement) -> None:
        center = raw_object.get("center")
        if not isinstance(center, dict):
            return

        pseudo_node = deepcopy(raw_object)
        pseudo_node["lat"] = center.get("lat")
        pseudo_node["lon"] = center.get("lon")
        pseudo_node["__is_center_placeholder"] = True
        self._nodes.append(pseudo_node)

    def _add_bounds_geometry(self, raw_object: RawElement) -> None:
        bounds = raw_object.get("bounds")
        if not isinstance(bounds, dict):
            return

        pseudo_way = deepcopy(raw_object)
        pseudo_way["nodes"] = []

        def add_pseudo_node(latitude: Any, longitude: Any, index: int) -> None:
            pseudo_node = {
                "type": "node",
                "id": (
                    f"_{pseudo_way.get('type')}/"
                    f"{pseudo_way.get('id')}bounds{index}"
                ),
                "lat": latitude,
                "lon": longitude,
            }
            pseudo_way["nodes"].append(pseudo_node["id"])
            self._nodes.append(pseudo_node)

        add_pseudo_node(bounds.get("minlat"), bounds.get("minlon"), 1)
        add_pseudo_node(bounds.get("maxlat"), bounds.get("minlon"), 2)
        add_pseudo_node(bounds.get("maxlat"), bounds.get("maxlon"), 3)
        add_pseudo_node(bounds.get("minlat"), bounds.get("maxlon"), 4)
        pseudo_way["nodes"].append(pseudo_way["nodes"][0])
        pseudo_way["__is_bounds_placeholder"] = True
        self._ways.append(pseudo_way)

    def _add_full_geometry_way(self, way: RawElement) -> None:
        geometry = way.get("geometry")
        if not isinstance(geometry, list):
            return

        if not isinstance(way.get("nodes"), list):
            node_identifiers = []
            for vertex in geometry:
                if vertex is None:
                    node_identifiers.append("_anonymous@unknown_location")
                    continue

                node_identifiers.append(
                    f"_anonymous@{vertex.get('lat')}/{vertex.get('lon')}"
                )
            way["nodes"] = node_identifiers

        for index, vertex in enumerate(geometry):
            if not isinstance(vertex, dict):
                continue

            self._nodes.append(
                {
                    "type": "node",
                    "id": way["nodes"][index],
                    "lat": vertex.get("lat"),
                    "lon": vertex.get("lon"),
                }
            )

    def _add_full_geometry_relation(self, relation: RawElement) -> None:
        members = relation.get("members")
        if not isinstance(members, list):
            return

        for member in members:
            if not isinstance(member, dict):
                continue

            member_type = self._parse_element_type(member.get("type"))
            member_identifier = self._member_identifier(member)
            if member_type == OsmElementType.NODE:
                if member.get("lat") is None or member.get("lon") is None:
                    continue

                self._nodes.append(
                    {
                        "type": "node",
                        "id": member_identifier,
                        "lat": member.get("lat"),
                        "lon": member.get("lon"),
                    }
                )
                continue

            geometry = member.get("geometry")
            if member_type != OsmElementType.WAY:
                continue

            if not isinstance(geometry, list):
                continue

            full_geometry_identifier = f"_fullGeom{member_identifier}"
            member["ref"] = full_geometry_identifier
            self._add_full_geometry_way_object(
                geometry,
                full_geometry_identifier,
            )

    def _add_full_geometry_way_object(
        self,
        geometry: List[Any],
        way_identifier: Any,
    ) -> None:
        for way in self._ways:
            if self._parse_element_type(way.get("type")) != OsmElementType.WAY:
                continue

            if way.get("id") == way_identifier:
                return

        geometry_way = {"type": "way", "id": way_identifier, "nodes": []}
        for vertex in geometry:
            if not isinstance(vertex, dict):
                geometry_way["nodes"].append(None)
                continue

            geometry_node = {
                "type": "node",
                "id": f"_anonymous@{vertex.get('lat')}/{vertex.get('lon')}",
                "lat": vertex.get("lat"),
                "lon": vertex.get("lon"),
            }
            geometry_way["nodes"].append(geometry_node["id"])
            self._nodes.append(geometry_node)

        self._ways.append(geometry_way)

    def _build_features(
        self,
        feature_callback: Optional[Callable[[Feature], None]],
    ) -> List[Feature]:
        self._build_node_index()
        point_identifiers = self._build_point_identifiers()
        self._build_way_index()
        pois = self._build_points_of_interest(point_identifiers)
        self._build_relation_index()
        self._build_relation_membership_map()

        point_features = self._build_point_features(pois, feature_callback)
        line_features: List[Feature] = []
        polygon_features: List[Feature] = []
        self._build_relation_features(
            feature_callback,
            point_features,
            line_features,
            polygon_features,
        )
        self._build_way_features(
            feature_callback,
            line_features,
            polygon_features,
        )

        if feature_callback is not None:
            return []

        features: List[Feature] = []
        features.extend(polygon_features)
        features.extend(line_features)
        features.extend(point_features)
        return features

    def _ensure_features_built(self) -> None:
        if self._cached_features is not None:
            return

        self._cached_features = self._build_features(None)

    def _build_node_index(self) -> None:
        self._node_index = {}
        for node in self._nodes:
            node_identifier = node.get("id")
            if node_identifier in self._node_index:
                node = self._deduplicator(
                    node, self._node_index[node_identifier]
                )

            self._node_index[node_identifier] = node

    def _build_point_identifiers(self) -> Dict[Any, bool]:
        point_identifiers: Dict[Any, bool] = {}
        for node in self._node_index.values():
            tags = node.get("tags")
            if isinstance(tags, dict) and self._has_interesting_tags(tags):
                point_identifiers[node.get("id")] = True

        for relation in self._relations:
            members = relation.get("members")
            if not isinstance(members, list):
                continue

            for member in members:
                if not isinstance(member, dict):
                    continue

                if (
                    self._parse_element_type(member.get("type"))
                    == OsmElementType.NODE
                ):
                    point_identifiers[self._member_identifier(member)] = True

        return point_identifiers

    def _build_way_index(self) -> None:
        self._way_index = {}
        self._way_node_identifiers = {}
        for way in self._ways:
            way_identifier = way.get("id")
            if way_identifier in self._way_index:
                way = self._deduplicator(way, self._way_index[way_identifier])

            self._way_index[way_identifier] = way
            nodes = way.get("nodes")
            if not isinstance(nodes, list):
                continue

            resolved_nodes = []
            for node_reference in nodes:
                if isinstance(node_reference, dict):
                    resolved_nodes.append(node_reference)
                    continue

                self._way_node_identifiers[node_reference] = True
                resolved_nodes.append(self._node_index.get(node_reference))

            way["nodes"] = resolved_nodes

    def _build_points_of_interest(
        self,
        point_identifiers: Dict[Any, bool],
    ) -> List[RawElement]:
        pois: List[RawElement] = []
        for node_identifier, node in self._node_index.items():
            if (
                node_identifier in self._way_node_identifiers
                and not point_identifiers.get(node_identifier)
            ):
                continue

            pois.append(node)

        return pois

    def _build_relation_index(self) -> None:
        self._relation_index = {}
        for relation in self._relations:
            relation_identifier = relation.get("id")
            if relation_identifier in self._relation_index:
                relation = self._deduplicator(
                    relation,
                    self._relation_index[relation_identifier],
                )

            self._relation_index[relation_identifier] = relation

    def _build_relation_membership_map(self) -> None:
        self._relation_membership_map = {
            OsmElementType.NODE: {},
            OsmElementType.WAY: {},
            OsmElementType.RELATION: {},
        }
        for relation in self._relation_index.values():
            relation_identifier = self._int_or_none(relation.get("id"))
            if relation_identifier is None:
                continue

            members = relation.get("members")
            if not isinstance(members, list):
                continue

            for member in members:
                if not isinstance(member, dict):
                    continue

                member_type = self._parse_element_type(member.get("type"))
                if member_type is None:
                    continue

                member_reference = self._member_identifier(member)
                if not isinstance(member_reference, int):
                    member_reference = self._strip_full_geometry_prefix(
                        member_reference,
                    )

                self._relation_membership_map[member_type].setdefault(
                    member_reference,
                    [],
                ).append(
                    _RelationRef(
                        role=self._string_or_none(member.get("role")),
                        rel=relation_identifier,
                        reltags=deepcopy(relation.get("tags", {})),
                    )
                )

    def _build_point_features(
        self,
        pois: List[RawElement],
        feature_callback: Optional[Callable[[Feature], None]],
    ) -> List[Feature]:
        point_features = []
        for point in pois:
            longitude = self._float_or_none(point.get("lon"))
            latitude = self._float_or_none(point.get("lat"))
            if longitude is None or latitude is None:
                continue

            feature = {
                "type": "Feature",
                "id": f"{point.get('type')}/{point.get('id')}",
                "properties": {
                    "type": point.get("type"),
                    "id": point.get("id"),
                    "tags": deepcopy(point.get("tags") or {}),
                    "relations": self._serialize_relation_refs(
                        self._relation_membership_map[OsmElementType.NODE].get(
                            point.get("id"),
                            [],
                        )
                    ),
                    "meta": self._build_meta_information(point),
                },
                "geometry": {
                    "type": "Point",
                    "coordinates": [longitude, latitude],
                },
            }
            if point.get("__is_center_placeholder"):
                feature["properties"]["geometry"] = "center"

            self._feature_index[feature["id"]] = deepcopy(feature)
            if feature_callback is None:
                point_features.append(feature)
            else:
                feature_callback(feature)

        return point_features

    def _build_relation_features(
        self,
        feature_callback: Optional[Callable[[Feature], None]],
        point_features: List[Feature],
        line_features: List[Feature],
        polygon_features: List[Feature],
    ) -> None:
        del point_features
        del line_features
        for relation in self._relation_index.values():
            tags = relation.get("tags")
            if not isinstance(tags, dict):
                continue

            relation_type = str(tags.get("type", "")).lower()
            if relation_type in ("route", "waterway"):
                members = relation.get("members")
                if not isinstance(members, list):
                    continue

                for member in members:
                    if not isinstance(member, dict):
                        continue

                    way = self._way_index.get(member.get("ref"))
                    if way is None:
                        way = self._way_index.get(
                            self._member_identifier(member)
                        )
                    way_tags = {} if way is None else way.get("tags") or {}
                    if not self._has_interesting_tags(way_tags):
                        if way is not None:
                            way["is_skippablerelationmember"] = True

                feature = self._construct_route_feature(relation)
                if feature is None:
                    continue

                feature = self._rewind_feature(feature)
                self._feature_index[feature["id"]] = deepcopy(feature)
                if feature_callback is None:
                    polygon_features.append(feature)
                else:
                    feature_callback(feature)
                continue

            if relation_type not in ("multipolygon", "boundary"):
                continue

            members = relation.get("members")
            if not isinstance(members, list):
                continue

            outer_count = 0
            for member in members:
                if not isinstance(member, dict):
                    continue

                role = str(member.get("role", "")).lower()
                if role == "outer":
                    outer_count += 1

                way = self._way_index.get(member.get("ref"))
                if way is None:
                    way = self._way_index.get(self._member_identifier(member))
                if way is None:
                    continue

                way_tags = way.get("tags") or {}
                if role == "outer" and not self._has_interesting_tags(
                    way_tags,
                    tags,
                ):
                    way["is_skippablerelationmember"] = True

                if role == "inner" and not self._has_interesting_tags(
                    way_tags
                ):
                    way["is_skippablerelationmember"] = True

            if outer_count == 0:
                continue

            is_simple_multipolygon = (
                outer_count == 1
                and not self._has_interesting_tags(tags, {"type": True})
            )
            feature = None
            if is_simple_multipolygon:
                outer_member = None
                for member in members:
                    if str(member.get("role", "")).lower() == "outer":
                        outer_member = member
                        break

                if outer_member is None:
                    continue

                outer_way = self._way_index.get(outer_member.get("ref"))
                if outer_way is None:
                    outer_way = self._way_index.get(
                        self._member_identifier(outer_member)
                    )
                if outer_way is None:
                    continue

                outer_way["is_skippablerelationmember"] = True
                feature = self._construct_multipolygon_feature(
                    outer_way, relation
                )
            else:
                feature = self._construct_multipolygon_feature(
                    relation, relation
                )

            if feature is None:
                continue

            feature = self._rewind_feature(feature)
            self._feature_index[feature["id"]] = deepcopy(feature)
            if feature_callback is None:
                polygon_features.append(feature)
            else:
                feature_callback(feature)

    def _build_way_features(
        self,
        feature_callback: Optional[Callable[[Feature], None]],
        line_features: List[Feature],
        polygon_features: List[Feature],
    ) -> None:
        for way in self._way_index.values():
            way_identifier = way.get("id")
            nodes = way.get("nodes")
            if not isinstance(nodes, list):
                continue

            if way.get("is_skippablerelationmember"):
                continue

            if not isinstance(way_identifier, int):
                way_identifier = self._strip_full_geometry_prefix(
                    way_identifier
                )
                way["id"] = way_identifier

            coordinates = []
            way["tainted"] = False
            for node in nodes:
                if not isinstance(node, dict):
                    way["tainted"] = True
                    continue

                longitude = self._float_or_none(node.get("lon"))
                latitude = self._float_or_none(node.get("lat"))
                if longitude is None or latitude is None:
                    way["tainted"] = True
                    continue

                coordinates.append((longitude, latitude))

            if len(coordinates) <= 1:
                continue

            geometry_type = "LineString"
            geometry_coordinates: Any = [list(point) for point in coordinates]
            if self._is_polygon_way(way):
                geometry_type = "Polygon"
                geometry_coordinates = [geometry_coordinates]

            feature = {
                "type": "Feature",
                "id": f"{way.get('type')}/{way_identifier}",
                "properties": {
                    "type": way.get("type"),
                    "id": way_identifier,
                    "tags": deepcopy(way.get("tags") or {}),
                    "relations": self._serialize_relation_refs(
                        self._relation_membership_map[OsmElementType.WAY].get(
                            way_identifier,
                            [],
                        )
                    ),
                    "meta": self._build_meta_information(way),
                },
                "geometry": {
                    "type": geometry_type,
                    "coordinates": geometry_coordinates,
                },
            }
            if way.get("tainted"):
                feature["properties"]["tainted"] = True

            if way.get("__is_bounds_placeholder"):
                feature["properties"]["geometry"] = "bounds"

            feature = self._rewind_feature(feature)
            self._feature_index[feature["id"]] = deepcopy(feature)
            if feature_callback is None:
                if geometry_type == "LineString":
                    line_features.append(feature)
                else:
                    polygon_features.append(feature)
            else:
                feature_callback(feature)

    def _construct_route_feature(
        self, relation: RawElement
    ) -> Optional[Feature]:
        members = relation.get("members")
        if not isinstance(members, list):
            return None

        is_tainted = False
        prepared_members = []
        for member in members:
            if not isinstance(member, dict):
                continue

            if (
                self._parse_element_type(member.get("type"))
                != OsmElementType.WAY
            ):
                continue

            way = self._way_index.get(member.get("ref"))
            if way is None:
                way = self._way_index.get(self._member_identifier(member))
            if way is None or not isinstance(way.get("nodes"), list):
                is_tainted = True
                continue

            nodes = []
            for node in way["nodes"]:
                if isinstance(node, dict):
                    nodes.append(node)
                    continue

                is_tainted = True

            prepared_members.append(
                {
                    "id": member.get("ref"),
                    "role": member.get("role"),
                    "way": way,
                    "nodes": nodes,
                }
            )

        line_strings = self._join(prepared_members)
        coordinates = []
        for line_string in line_strings:
            points = []
            for node in line_string:
                longitude = self._float_or_none(node.get("lon"))
                latitude = self._float_or_none(node.get("lat"))
                if longitude is None or latitude is None:
                    continue

                points.append([longitude, latitude])

            if len(points) > 0:
                coordinates.append(points)

        if len(coordinates) == 0:
            return None

        geometry_type = "LineString"
        geometry_coordinates: Any = coordinates[0]
        if len(coordinates) > 1:
            geometry_type = "MultiLineString"
            geometry_coordinates = coordinates

        feature = {
            "type": "Feature",
            "id": f"{relation.get('type')}/{relation.get('id')}",
            "properties": {
                "type": relation.get("type"),
                "id": relation.get("id"),
                "tags": deepcopy(relation.get("tags") or {}),
                "relations": self._serialize_relation_refs(
                    self._relation_membership_map[OsmElementType.RELATION].get(
                        relation.get("id"),
                        [],
                    )
                ),
                "meta": self._build_meta_information(relation),
            },
            "geometry": {
                "type": geometry_type,
                "coordinates": geometry_coordinates,
            },
        }
        if is_tainted:
            feature["properties"]["tainted"] = True

        return feature

    def _construct_multipolygon_feature(
        self,
        tag_object: RawElement,
        relation: RawElement,
        *,
        force_relation_identifier: bool = False,
    ) -> Optional[Feature]:
        members = relation.get("members")
        if not isinstance(members, list):
            return None

        is_tainted = False
        prepared_members = []
        for member in members:
            if not isinstance(member, dict):
                continue

            if (
                self._parse_element_type(member.get("type"))
                != OsmElementType.WAY
            ):
                continue

            way = self._way_index.get(member.get("ref"))
            if way is None:
                way = self._way_index.get(self._member_identifier(member))
            if way is None or not isinstance(way.get("nodes"), list):
                is_tainted = True
                continue

            nodes = []
            for node in way["nodes"]:
                if isinstance(node, dict):
                    nodes.append(node)
                    continue

                is_tainted = True

            prepared_members.append(
                {
                    "id": member.get("ref"),
                    "role": member.get("role") or "outer",
                    "way": way,
                    "nodes": nodes,
                }
            )

        outer_members = []
        inner_members = []
        for member in prepared_members:
            if str(member.get("role", "")).lower() == "inner":
                inner_members.append(member)
                continue

            outer_members.append(member)

        outer_rings = self._join(outer_members)
        inner_rings = self._join(inner_members)
        multipolygon = [[ring] for ring in outer_rings]
        for inner_ring in inner_rings:
            outer_index = self._find_outer_ring(outer_rings, inner_ring)
            if outer_index is None:
                continue

            multipolygon[outer_index].append(inner_ring)

        polygon_coordinates: List[Any] = []
        for ring_group in multipolygon:
            rings = []
            for ring in ring_group:
                if len(ring) < 4:
                    continue

                coordinates = []
                for node in ring:
                    longitude = self._float_or_none(node.get("lon"))
                    latitude = self._float_or_none(node.get("lat"))
                    if longitude is None or latitude is None:
                        continue

                    coordinates.append([longitude, latitude])

                if len(coordinates) >= 4:
                    rings.append(coordinates)

            if len(rings) > 0:
                polygon_coordinates.append(rings)

        if len(polygon_coordinates) == 0:
            return None

        geometry_type = "MultiPolygon"
        geometry_coordinates: Any = polygon_coordinates
        if len(polygon_coordinates) == 1:
            geometry_type = "Polygon"
            geometry_coordinates = polygon_coordinates[0]

        feature_identifier = tag_object.get("id")
        if not force_relation_identifier and not isinstance(
            feature_identifier, int
        ):
            feature_identifier = self._strip_full_geometry_prefix(
                feature_identifier
            )

        feature_type = tag_object.get("type")
        if force_relation_identifier:
            feature_identifier = relation.get("id")
            feature_type = relation.get("type")

        membership_type = self._parse_element_type(feature_type)
        relation_refs: List[_RelationRef] = []
        if membership_type is not None:
            relation_refs = self._relation_membership_map[membership_type].get(
                feature_identifier,
                [],
            )

        feature = {
            "type": "Feature",
            "id": f"{feature_type}/{feature_identifier}",
            "properties": {
                "type": feature_type,
                "id": feature_identifier,
                "tags": deepcopy(tag_object.get("tags") or {}),
                "relations": self._serialize_relation_refs(relation_refs),
                "meta": self._build_meta_information(tag_object),
            },
            "geometry": {
                "type": geometry_type,
                "coordinates": geometry_coordinates,
            },
        }
        if is_tainted:
            feature["properties"]["tainted"] = True

        return feature

    def _generic_relation_geometry(
        self,
        raw_relation: RawElement,
    ) -> Optional[OsmGeometry]:
        members = raw_relation.get("members")
        if not isinstance(members, list):
            return None

        point_geometries: List[QgsPointXY] = []
        line_geometries: List[List[QgsPointXY]] = []
        polygon_geometries: List[List[List[QgsPointXY]]] = []
        for member in members:
            if not isinstance(member, dict):
                continue

            member_type = self._parse_element_type(member.get("type"))
            member_reference = self._member_identifier(member)
            if member_type == OsmElementType.NODE:
                node = member
                if node.get("lat") is None or node.get("lon") is None:
                    node = self._node_index.get(member_reference, member)

                longitude = self._float_or_none(node.get("lon"))
                latitude = self._float_or_none(node.get("lat"))
                if longitude is None or latitude is None:
                    continue

                point_geometries.append(QgsPointXY(longitude, latitude))
                continue

            if member_type != OsmElementType.WAY:
                continue

            feature = self._feature_index.get(f"way/{member_reference}")
            if feature is None:
                way = self._way_index.get(member_reference)
                if way is None:
                    continue

                feature = self._build_temporary_way_feature(way)

            if feature is None:
                continue

            geometry = feature.get("geometry", {})
            geometry_type = geometry.get("type")
            coordinates = geometry.get("coordinates")
            if geometry_type == "LineString":
                line = self._line_from_coordinates(coordinates)
                if len(line) > 0:
                    line_geometries.append(line)
                continue

            if geometry_type == "Polygon":
                polygon = self._polygon_from_coordinates(coordinates)
                if len(polygon) > 0:
                    polygon_geometries.append(polygon)

        points = self._points_geometry(point_geometries)
        lines = self._lines_geometry(line_geometries)
        polygons = self._polygons_geometry(polygon_geometries)
        available_geometries = [
            geometry
            for geometry in (points, lines, polygons)
            if geometry is not None
        ]
        if len(available_geometries) == 0:
            return None

        if len(available_geometries) == 1:
            return available_geometries[0]

        return OsmGeometryCollection(
            points=points,
            lines=lines,
            polygons=polygons,
        )

    def _relation_has_incomplete_members(
        self,
        raw_relation: RawElement,
    ) -> bool:
        members = raw_relation.get("members")
        if not isinstance(members, list):
            return False

        for member in members:
            if not isinstance(member, dict):
                return True

            member_type = self._parse_element_type(member.get("type"))
            member_reference = self._member_identifier(member)

            if member_type == OsmElementType.NODE:
                node = member
                if member.get("lat") is None or member.get("lon") is None:
                    node = self._node_index.get(member_reference, member)

                if (
                    self._float_or_none(node.get("lat")) is None
                    or self._float_or_none(node.get("lon")) is None
                ):
                    return True

                continue

            if member_type == OsmElementType.WAY:
                if self._member_has_full_way_geometry(member):
                    if self._member_geometry_is_incomplete(
                        member.get("geometry")
                    ):
                        return True

                    continue

                way = self._way_index.get(member.get("ref"))
                if way is None:
                    way = self._way_index.get(member_reference)

                if way is None or not isinstance(way.get("nodes"), list):
                    return True

                way_nodes = way.get("nodes", [])
                if len(way_nodes) == 0:
                    return True

                valid_node_count = 0
                for node in way_nodes:
                    if not isinstance(node, dict):
                        return True

                    if (
                        self._float_or_none(node.get("lat")) is None
                        or self._float_or_none(node.get("lon")) is None
                    ):
                        return True

                    valid_node_count += 1

                if valid_node_count <= 1:
                    return True

                continue

            if member_type == OsmElementType.RELATION:
                continue

        return False

    def _member_has_full_way_geometry(self, member: RawElement) -> bool:
        return isinstance(member.get("geometry"), list)

    def _member_geometry_is_incomplete(self, geometry: Any) -> bool:
        if not isinstance(geometry, list):
            return True

        if len(geometry) == 0:
            return True

        valid_vertex_count = 0
        for vertex in geometry:
            if not isinstance(vertex, dict):
                return True

            if (
                self._float_or_none(vertex.get("lat")) is None
                or self._float_or_none(vertex.get("lon")) is None
            ):
                return True

            valid_vertex_count += 1

        return valid_vertex_count <= 1

    def _merge_relation_member_points(
        self,
        base_geometry: Optional[OsmGeometry],
        raw_relation: RawElement,
    ) -> Optional[OsmGeometry]:
        member_points = self._relation_member_points_geometry(raw_relation)
        if member_points is None:
            return base_geometry

        if base_geometry is None:
            return member_points

        if isinstance(base_geometry, OsmGeometryCollection):
            return OsmGeometryCollection(
                points=self._merge_optional_point_members(
                    base_geometry.points,
                    member_points,
                ),
                lines=(
                    None
                    if base_geometry.lines is None
                    else QgsGeometry(base_geometry.lines)
                ),
                polygons=(
                    None
                    if base_geometry.polygons is None
                    else QgsGeometry(base_geometry.polygons)
                ),
            )

        geometry_type = base_geometry.type()
        if geometry_type == GeometryType.Point:
            return self._merge_point_geometries(base_geometry, member_points)

        if geometry_type == GeometryType.Line:
            return OsmGeometryCollection(
                points=member_points,
                lines=QgsGeometry(base_geometry),
            )

        if geometry_type == GeometryType.Polygon:
            return OsmGeometryCollection(
                points=member_points,
                polygons=QgsGeometry(base_geometry),
            )

        return base_geometry

    def _merge_optional_point_members(
        self,
        left: Optional[QgsGeometry],
        right: Optional[QgsGeometry],
    ) -> Optional[QgsGeometry]:
        if left is None:
            return right

        if right is None:
            return QgsGeometry(left)

        return self._merge_point_geometries(left, right)

    def _relation_member_points_geometry(
        self,
        raw_relation: RawElement,
    ) -> Optional[QgsGeometry]:
        members = raw_relation.get("members")
        if not isinstance(members, list):
            return None

        point_geometries: List[QgsPointXY] = []
        for member in members:
            if not isinstance(member, dict):
                continue

            if (
                self._parse_element_type(member.get("type"))
                != OsmElementType.NODE
            ):
                continue

            node = member
            member_reference = self._member_identifier(member)
            if node.get("lat") is None or node.get("lon") is None:
                node = self._node_index.get(member_reference, member)

            longitude = self._float_or_none(node.get("lon"))
            latitude = self._float_or_none(node.get("lat"))
            if longitude is None or latitude is None:
                continue

            point_geometries.append(QgsPointXY(longitude, latitude))

        return self._points_geometry(point_geometries)

    def _merge_point_geometries(
        self,
        left: QgsGeometry,
        right: QgsGeometry,
    ) -> QgsGeometry:
        points: List[QgsPointXY] = []
        points.extend(self._geometry_points(left))
        points.extend(self._geometry_points(right))
        return self._points_geometry(points) or QgsGeometry(left)

    def _geometry_points(self, geometry: QgsGeometry) -> List[QgsPointXY]:
        if geometry.isMultipart():
            return list(geometry.asMultiPoint())

        return [geometry.asPoint()]

    def _build_temporary_way_feature(
        self,
        way: RawElement,
    ) -> Optional[Feature]:
        cloned_way = deepcopy(way)
        if not isinstance(cloned_way.get("nodes"), list):
            return None

        coordinates = []
        for node in cloned_way["nodes"]:
            if not isinstance(node, dict):
                continue

            longitude = self._float_or_none(node.get("lon"))
            latitude = self._float_or_none(node.get("lat"))
            if longitude is None or latitude is None:
                continue

            coordinates.append([longitude, latitude])

        if len(coordinates) <= 1:
            return None

        geometry_type = (
            "Polygon" if self._is_polygon_way(cloned_way) else "LineString"
        )
        geometry_coordinates: Any = coordinates
        if geometry_type == "Polygon":
            geometry_coordinates = [coordinates]

        return {
            "type": "Feature",
            "id": f"way/{cloned_way.get('id')}",
            "properties": {
                "type": "way",
                "id": cloned_way.get("id"),
                "tags": deepcopy(cloned_way.get("tags") or {}),
                "relations": [],
                "meta": self._build_meta_information(cloned_way),
            },
            "geometry": {
                "type": geometry_type,
                "coordinates": geometry_coordinates,
            },
        }

    def _geometry_from_feature(
        self,
        feature: Feature,
    ) -> Optional[OsmGeometry]:
        geometry = feature.get("geometry")
        if not isinstance(geometry, dict):
            return None

        geometry_type = geometry.get("type")
        coordinates = geometry.get("coordinates")
        if geometry_type == "Point":
            point = self._point_from_coordinates(coordinates)
            if point is None:
                return None

            return QgsGeometry.fromPointXY(point)

        if geometry_type == "MultiPoint":
            points = self._line_from_coordinates(coordinates)
            if len(points) == 0:
                return None

            return QgsGeometry.fromMultiPointXY(points)

        if geometry_type == "LineString":
            points = self._line_from_coordinates(coordinates)
            if len(points) == 0:
                return None

            return QgsGeometry.fromPolylineXY(points)

        if geometry_type == "MultiLineString":
            lines = []
            for line_coordinates in coordinates or []:
                line = self._line_from_coordinates(line_coordinates)
                if len(line) > 0:
                    lines.append(line)

            if len(lines) == 0:
                return None

            return QgsGeometry.fromMultiPolylineXY(lines)

        if geometry_type == "Polygon":
            polygon = self._polygon_from_coordinates(coordinates)
            if len(polygon) == 0:
                return None

            return QgsGeometry.fromPolygonXY(polygon)

        if geometry_type == "MultiPolygon":
            polygons = []
            for polygon_coordinates in coordinates or []:
                polygon = self._polygon_from_coordinates(polygon_coordinates)
                if len(polygon) > 0:
                    polygons.append(polygon)

            if len(polygons) == 0:
                return None

            return QgsGeometry.fromMultiPolygonXY(polygons)

        return None

    def _point_from_coordinates(
        self, coordinates: Any
    ) -> Optional[QgsPointXY]:
        if not isinstance(coordinates, list) or len(coordinates) < 2:
            return None

        longitude = self._float_or_none(coordinates[0])
        latitude = self._float_or_none(coordinates[1])
        if longitude is None or latitude is None:
            return None

        return QgsPointXY(longitude, latitude)

    def _line_from_coordinates(self, coordinates: Any) -> List[QgsPointXY]:
        points = []
        if not isinstance(coordinates, list):
            return points

        for point_coordinates in coordinates:
            point = self._point_from_coordinates(point_coordinates)
            if point is not None:
                points.append(point)

        return points

    def _polygon_from_coordinates(
        self,
        coordinates: Any,
    ) -> List[List[QgsPointXY]]:
        polygon = []
        if not isinstance(coordinates, list):
            return polygon

        for ring_coordinates in coordinates:
            ring = self._line_from_coordinates(ring_coordinates)
            if len(ring) > 0:
                polygon.append(ring)

        return polygon

    def _points_geometry(
        self,
        points: List[QgsPointXY],
    ) -> Optional[QgsGeometry]:
        if len(points) == 0:
            return None

        if len(points) == 1:
            return QgsGeometry.fromPointXY(points[0])

        return QgsGeometry.fromMultiPointXY(points)

    def _lines_geometry(
        self,
        lines: List[List[QgsPointXY]],
    ) -> Optional[QgsGeometry]:
        if len(lines) == 0:
            return None

        if len(lines) == 1:
            return QgsGeometry.fromPolylineXY(lines[0])

        return QgsGeometry.fromMultiPolylineXY(lines)

    def _polygons_geometry(
        self,
        polygons: List[List[List[QgsPointXY]]],
    ) -> Optional[QgsGeometry]:
        if len(polygons) == 0:
            return None

        if len(polygons) == 1:
            return QgsGeometry.fromPolygonXY(polygons[0])

        return QgsGeometry.fromMultiPolygonXY(polygons)

    def _is_polygon_way(self, way: RawElement) -> bool:
        nodes = way.get("nodes")
        if not isinstance(nodes, list) or len(nodes) == 0:
            return False

        first_node = nodes[0]
        last_node = nodes[-1]
        if not isinstance(first_node, dict) or not isinstance(last_node, dict):
            return False

        if first_node.get("id") != last_node.get("id"):
            return False

        if way.get("__is_bounds_placeholder"):
            return True

        tags = way.get("tags")
        if not isinstance(tags, dict):
            return False

        return self._is_polygon_feature(tags)

    def _is_polygon_feature(self, tags: Dict[str, Any]) -> bool:
        polygon_features = self._polygon_features
        if callable(polygon_features):
            return bool(polygon_features(tags))

        if tags.get("area") == "no":
            return False

        for key, value in tags.items():
            polygon_rule = polygon_features.get(key)
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

    def _has_interesting_tags(
        self,
        tags: Dict[str, Any],
        ignore_tags: Optional[Dict[str, Any]] = None,
    ) -> bool:
        ignored_tags = {} if ignore_tags is None else ignore_tags
        if callable(self._uninteresting_tags):
            return not bool(self._uninteresting_tags(tags, ignored_tags))

        for key, value in tags.items():
            if isinstance(self._uninteresting_tags, (set, frozenset)):
                if key in self._uninteresting_tags:
                    continue
            elif self._uninteresting_tags.get(key) is True:
                continue

            if ignored_tags.get(key) is True:
                continue

            if ignored_tags.get(key) == value:
                continue

            return True

        return False

    def _default_deduplicator(
        self,
        object_a: RawElement,
        object_b: RawElement,
    ) -> RawElement:
        version_a = self._int_or_none(object_a.get("version"))
        version_b = self._int_or_none(object_b.get("version"))
        if (
            version_a is not None
            and version_b is not None
            and version_a != version_b
        ):
            return deepcopy(object_a if version_a > version_b else object_b)

        return self._deep_merge_dicts(object_a, object_b)

    def _deep_merge_dicts(
        self,
        left: RawElement,
        right: RawElement,
    ) -> RawElement:
        result = deepcopy(left)
        for key, value in right.items():
            if value is None:
                continue

            existing_value = result.get(key)
            if isinstance(existing_value, dict) and isinstance(value, dict):
                result[key] = self._deep_merge_dicts(existing_value, value)
                continue

            result[key] = deepcopy(value)

        return result

    def _build_meta_information(
        self, raw_object: RawElement
    ) -> Dict[str, Any]:
        meta = {
            "timestamp": raw_object.get("timestamp"),
            "version": raw_object.get("version"),
            "changeset": raw_object.get("changeset"),
            "user": raw_object.get("user"),
            "uid": raw_object.get("uid"),
        }
        return {key: value for key, value in meta.items() if value is not None}

    def _serialize_relation_refs(
        self,
        relation_refs: List[_RelationRef],
    ) -> List[Dict[str, Any]]:
        return [
            {
                "role": relation_ref.role,
                "rel": relation_ref.rel,
                "reltags": deepcopy(relation_ref.reltags),
            }
            for relation_ref in relation_refs
        ]

    def _flatten_feature_properties(
        self,
        feature_collection: Dict[str, Any],
    ) -> None:
        for feature in feature_collection.get("features", []):
            properties = feature.get("properties", {})
            merged_properties = {}
            merged_properties.update(properties.get("meta", {}))
            merged_properties.update(properties.get("tags", {}))
            merged_properties["id"] = (
                f"{properties.get('type')}/{properties.get('id')}"
            )
            feature["properties"] = merged_properties

    def _rewind_feature_collection(
        self,
        feature_collection: Dict[str, Any],
    ) -> Dict[str, Any]:
        collection = deepcopy(feature_collection)
        collection["features"] = [
            self._rewind_feature(feature)
            for feature in collection.get("features", [])
        ]
        return collection

    def _rewind_feature(self, feature: Feature) -> Feature:
        rewound_feature = deepcopy(feature)
        geometry = rewound_feature.get("geometry")
        if not isinstance(geometry, dict):
            return rewound_feature

        geometry_type = geometry.get("type")
        if geometry_type == "Polygon":
            self._rewind_polygon_coordinates(geometry.get("coordinates"))
        elif geometry_type == "MultiPolygon":
            for polygon in geometry.get("coordinates", []):
                self._rewind_polygon_coordinates(polygon)

        return rewound_feature

    def _rewind_polygon_coordinates(self, polygon: Any) -> None:
        if not isinstance(polygon, list) or len(polygon) == 0:
            return

        for index, ring in enumerate(polygon):
            if not isinstance(ring, list):
                continue

            self._rewind_ring(ring, clockwise=index != 0)

    def _rewind_ring(self, ring: List[List[float]], clockwise: bool) -> None:
        if len(ring) == 0:
            return

        area = self._ring_area(ring)
        is_clockwise = area >= 0.0
        if is_clockwise != clockwise:
            ring.reverse()

    def _ring_area(self, ring: List[List[float]]) -> float:
        total = 0.0
        for index, point in enumerate(ring):
            previous = ring[index - 1]
            total += (point[0] - previous[0]) * (previous[1] + point[1])
        return total

    def _join(self, ways: List[RawElement]) -> List[List[RawElement]]:
        remaining_ways = list(ways)
        joined: List[List[RawElement]] = []
        while len(remaining_ways) > 0:
            current = list(remaining_ways.pop().get("nodes", []))
            joined.append(current)
            while len(remaining_ways) > 0 and not self._fit_together(
                current[0] if len(current) > 0 else None,
                current[-1] if len(current) > 0 else None,
            ):
                first_node = current[0] if len(current) > 0 else None
                last_node = current[-1] if len(current) > 0 else None
                matched_nodes = None
                insert_at_start = False
                matched_index = -1
                for index, way in enumerate(remaining_ways):
                    way_nodes = list(way.get("nodes", []))
                    if self._fit_together(
                        last_node, self._first_node(way_nodes)
                    ):
                        matched_nodes = way_nodes[1:]
                        matched_index = index
                        break

                    if self._fit_together(
                        last_node, self._last_node(way_nodes)
                    ):
                        matched_nodes = list(reversed(way_nodes[:-1]))
                        matched_index = index
                        break

                    if self._fit_together(
                        first_node, self._last_node(way_nodes)
                    ):
                        matched_nodes = way_nodes[:-1]
                        insert_at_start = True
                        matched_index = index
                        break

                    if self._fit_together(
                        first_node, self._first_node(way_nodes)
                    ):
                        matched_nodes = list(reversed(way_nodes[1:]))
                        insert_at_start = True
                        matched_index = index
                        break

                if matched_nodes is None or matched_index < 0:
                    break

                remaining_ways.pop(matched_index)
                if insert_at_start:
                    current[0:0] = matched_nodes
                    continue

                current.extend(matched_nodes)

        return joined

    def _find_outer_ring(
        self,
        outer_rings: List[List[RawElement]],
        inner_ring: List[RawElement],
    ) -> Optional[int]:
        inner_coordinates = self._lat_lon_coordinates(inner_ring)
        for index, outer_ring in enumerate(outer_rings):
            outer_coordinates = self._lat_lon_coordinates(outer_ring)
            if self._polygon_intersects_polygon(
                outer_coordinates, inner_coordinates
            ):
                return index

        return None

    def _polygon_intersects_polygon(
        self,
        outer_ring: List[Tuple[float, float]],
        inner_ring: List[Tuple[float, float]],
    ) -> bool:
        for point in inner_ring:
            if self._point_in_polygon(point, outer_ring):
                return True

        return False

    def _point_in_polygon(
        self,
        point: Tuple[float, float],
        polygon: List[Tuple[float, float]],
    ) -> bool:
        x_value = point[0]
        y_value = point[1]
        is_inside = False
        polygon_length = len(polygon)
        for index in range(polygon_length):
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

    def _lat_lon_coordinates(
        self,
        ring: List[RawElement],
    ) -> List[Tuple[float, float]]:
        coordinates = []
        for node in ring:
            latitude = self._float_or_none(node.get("lat"))
            longitude = self._float_or_none(node.get("lon"))
            if latitude is None or longitude is None:
                continue

            coordinates.append((latitude, longitude))

        return coordinates

    def _first_node(self, nodes: List[Any]) -> Optional[RawElement]:
        return None if len(nodes) == 0 else nodes[0]

    def _last_node(self, nodes: List[Any]) -> Optional[RawElement]:
        return None if len(nodes) == 0 else nodes[-1]

    def _member_identifier(self, member: RawElement) -> Any:
        return member.get("ref", member.get("id"))

    def _fit_together(
        self,
        node_a: Optional[RawElement],
        node_b: Optional[RawElement],
    ) -> bool:
        if not isinstance(node_a, dict) or not isinstance(node_b, dict):
            return False

        return node_a.get("id") == node_b.get("id")

    def _raw_identifier(self, raw_element: RawElement) -> Optional[int]:
        raw_identifier = raw_element.get("id", raw_element.get("ref"))
        return self._int_or_none(raw_identifier)

    def _strip_full_geometry_prefix(self, identifier: Any) -> Any:
        if not isinstance(identifier, str):
            return identifier

        if not identifier.startswith("_fullGeom"):
            return identifier

        return self._int_or_none(identifier.replace("_fullGeom", "", 1))

    def _string_or_none(self, value: Any) -> Optional[str]:
        if value is None:
            return None

        return str(value)

    def _int_or_none(self, value: Any) -> Optional[int]:
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _float_or_none(value: Any) -> Optional[float]:
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    def _parse_element_type(self, value: Any) -> Optional[OsmElementType]:
        if value is None:
            return None

        try:
            return OsmElementType(str(value).lower())
        except ValueError:
            return None
