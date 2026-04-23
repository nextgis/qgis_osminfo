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

# pyright: reportMissingImports=false

import copy
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional

import pytest


def _custom_deduplicator(
    object_a: Dict[str, Any],
    object_b: Dict[str, Any],
) -> Dict[str, Any]:
    version_a = int(object_a.get("version") or 0)
    version_b = int(object_b.get("version") or 0)
    selected_object = object_a if version_a < version_b else object_b
    return copy.deepcopy(selected_object)


def _uninteresting_tags_callback(
    tags: Dict[str, Any],
    ignore_tags: Dict[str, Any],
) -> bool:
    del ignore_tags
    return tags.get("tag") != "1"


def _polygon_features_callback(tags: Dict[str, Any]) -> bool:
    return tags.get("tag") == "1"


@dataclass(frozen=True)
class ParserCollectionCase:
    name: str
    response: Dict[str, Any]
    expected: Dict[str, Any]
    flat_properties: bool = True
    uninteresting_tags: Optional[Any] = None
    polygon_features: Optional[Any] = None
    deduplicator: Optional[
        Callable[[Dict[str, Any], Dict[str, Any]], Dict[str, Any]]
    ] = None


@dataclass(frozen=True)
class ParserCallbackCase:
    name: str
    response: Dict[str, Any]
    expected_features: List[Dict[str, Any]]
    flat_properties: bool = True


def _make_parser_kwargs(case: ParserCollectionCase) -> Dict[str, Any]:
    kwargs: Dict[str, Any] = {"flat_properties": case.flat_properties}
    if case.uninteresting_tags is not None:
        kwargs["uninteresting_tags"] = case.uninteresting_tags

    if case.polygon_features is not None:
        kwargs["polygon_features"] = case.polygon_features

    if case.deduplicator is not None:
        kwargs["deduplicator"] = case.deduplicator

    return kwargs


def _assert_collection_case(case: ParserCollectionCase) -> None:
    from osminfo.overpass.json_parser import OverpassJsonParser

    original_data = copy.deepcopy(case.response)
    parser = OverpassJsonParser.from_response(
        case.response,
        **_make_parser_kwargs(case),
    )
    result = parser.to_feature_collection()
    assert result == case.expected
    assert case.response == original_data


def _assert_callback_case(case: ParserCallbackCase) -> None:
    from osminfo.overpass.json_parser import OverpassJsonParser

    original_data = copy.deepcopy(case.response)
    parser = OverpassJsonParser.from_response(
        case.response,
        flat_properties=case.flat_properties,
    )
    callback_features: List[Dict[str, Any]] = []
    result = parser.to_feature_collection(callback_features.append)
    assert result is True
    assert callback_features == case.expected_features
    assert case.response == original_data


REFERENCE_CASES = (
    ParserCollectionCase(
        name="node",
        response={
            "elements": [{"type": "node", "id": 1, "lat": 1.234, "lon": 4.321}]
        },
        flat_properties=False,
        expected={
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "id": "node/1",
                    "properties": {
                        "type": "node",
                        "id": 1,
                        "tags": {},
                        "relations": [],
                        "meta": {},
                    },
                    "geometry": {
                        "type": "Point",
                        "coordinates": [4.321, 1.234],
                    },
                }
            ],
        },
    ),
    ParserCollectionCase(
        name="way",
        response={
            "elements": [
                {"type": "way", "id": 1, "nodes": [2, 3, 4]},
                {"type": "node", "id": 2, "lat": 0, "lon": 1},
                {"type": "node", "id": 3, "lat": 0, "lon": 1.1},
                {"type": "node", "id": 4, "lat": 0.1, "lon": 1.2},
            ]
        },
        flat_properties=False,
        expected={
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "id": "way/1",
                    "properties": {
                        "type": "way",
                        "id": 1,
                        "tags": {},
                        "relations": [],
                        "meta": {},
                    },
                    "geometry": {
                        "type": "LineString",
                        "coordinates": [[1, 0], [1.1, 0], [1.2, 0.1]],
                    },
                }
            ],
        },
    ),
    ParserCollectionCase(
        name="polygon",
        response={
            "elements": [
                {
                    "type": "way",
                    "id": 1,
                    "nodes": [2, 3, 4, 5, 2],
                    "tags": {"area": "yes"},
                },
                {"type": "node", "id": 2, "lat": 0, "lon": 0},
                {"type": "node", "id": 3, "lat": 0, "lon": 1},
                {"type": "node", "id": 4, "lat": 1, "lon": 1},
                {"type": "node", "id": 5, "lat": 1, "lon": 0},
            ]
        },
        flat_properties=False,
        expected={
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "id": "way/1",
                    "properties": {
                        "type": "way",
                        "id": 1,
                        "tags": {"area": "yes"},
                        "relations": [],
                        "meta": {},
                    },
                    "geometry": {
                        "type": "Polygon",
                        "coordinates": [
                            [[0, 0], [1, 0], [1, 1], [0, 1], [0, 0]]
                        ],
                    },
                }
            ],
        },
    ),
    ParserCollectionCase(
        name="simple multipolygon",
        response={
            "elements": [
                {
                    "type": "relation",
                    "id": 1,
                    "tags": {"type": "multipolygon"},
                    "members": [
                        {"type": "way", "ref": 2, "role": "outer"},
                        {"type": "way", "ref": 3, "role": "inner"},
                    ],
                },
                {
                    "type": "way",
                    "id": 2,
                    "nodes": [4, 5, 6, 7, 4],
                    "tags": {"area": "yes"},
                },
                {"type": "way", "id": 3, "nodes": [8, 9, 10, 8]},
                {"type": "node", "id": 4, "lat": -1, "lon": -1},
                {"type": "node", "id": 5, "lat": -1, "lon": 1},
                {"type": "node", "id": 6, "lat": 1, "lon": 1},
                {"type": "node", "id": 7, "lat": 1, "lon": -1},
                {"type": "node", "id": 8, "lat": -0.5, "lon": 0},
                {"type": "node", "id": 9, "lat": 0.5, "lon": 0},
                {"type": "node", "id": 10, "lat": 0, "lon": 0.5},
            ]
        },
        flat_properties=False,
        expected={
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "id": "way/2",
                    "properties": {
                        "type": "way",
                        "id": 2,
                        "tags": {"area": "yes"},
                        "relations": [
                            {
                                "role": "outer",
                                "rel": 1,
                                "reltags": {"type": "multipolygon"},
                            }
                        ],
                        "meta": {},
                    },
                    "geometry": {
                        "type": "Polygon",
                        "coordinates": [
                            [
                                [-1, -1],
                                [1, -1],
                                [1, 1],
                                [-1, 1],
                                [-1, -1],
                            ],
                            [[0, -0.5], [0, 0.5], [0.5, 0], [0, -0.5]],
                        ],
                    },
                }
            ],
        },
    ),
    ParserCollectionCase(
        name="route relation",
        response={
            "elements": [
                {
                    "type": "relation",
                    "id": 1,
                    "tags": {"type": "route"},
                    "members": [
                        {"type": "way", "ref": 2, "role": "forward"},
                        {"type": "way", "ref": 3, "role": "backward"},
                        {"type": "way", "ref": 4, "role": "forward"},
                    ],
                },
                {"type": "way", "id": 2, "nodes": [4, 5]},
                {"type": "way", "id": 3, "nodes": [5, 6]},
                {"type": "way", "id": 4, "nodes": [7, 8]},
                {"type": "node", "id": 4, "lat": -1, "lon": -1},
                {"type": "node", "id": 5, "lat": 0, "lon": 0},
                {"type": "node", "id": 6, "lat": 1, "lon": 1},
                {"type": "node", "id": 7, "lat": 10, "lon": 10},
                {"type": "node", "id": 8, "lat": 20, "lon": 20},
            ]
        },
        flat_properties=False,
        expected={
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "id": "relation/1",
                    "properties": {
                        "type": "relation",
                        "id": 1,
                        "tags": {"type": "route"},
                        "relations": [],
                        "meta": {},
                    },
                    "geometry": {
                        "type": "MultiLineString",
                        "coordinates": [
                            [[10, 10], [20, 20]],
                            [[-1, -1], [0, 0], [1, 1]],
                        ],
                    },
                }
            ],
        },
    ),
    ParserCollectionCase(
        name="flattened properties",
        response={
            "elements": [
                {
                    "type": "node",
                    "id": 1,
                    "lat": 1.234,
                    "lon": 4.321,
                    "user": "johndoe",
                    "tags": {"foo": "bar"},
                }
            ]
        },
        expected={
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "id": "node/1",
                    "properties": {
                        "foo": "bar",
                        "id": "node/1",
                        "user": "johndoe",
                    },
                    "geometry": {
                        "type": "Point",
                        "coordinates": [4.321, 1.234],
                    },
                }
            ],
        },
    ),
    ParserCollectionCase(
        name="uninteresting tags map",
        response={
            "elements": [
                {"type": "way", "id": 1, "nodes": [2, 3]},
                {
                    "type": "node",
                    "id": 2,
                    "lat": 1,
                    "lon": 0,
                    "user": "johndoe",
                    "tags": {"foo": "bar"},
                },
                {
                    "type": "node",
                    "id": 3,
                    "lat": 2,
                    "lon": 0,
                    "user": "johndoe",
                    "tags": {"foo": "bar", "asd": "fasd"},
                },
            ]
        },
        flat_properties=False,
        uninteresting_tags={"foo": True},
        expected={
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "id": "way/1",
                    "properties": {
                        "type": "way",
                        "id": 1,
                        "tags": {},
                        "relations": [],
                        "meta": {},
                    },
                    "geometry": {
                        "type": "LineString",
                        "coordinates": [[0, 1], [0, 2]],
                    },
                },
                {
                    "type": "Feature",
                    "id": "node/3",
                    "properties": {
                        "type": "node",
                        "id": 3,
                        "tags": {"foo": "bar", "asd": "fasd"},
                        "relations": [],
                        "meta": {"user": "johndoe"},
                    },
                    "geometry": {
                        "type": "Point",
                        "coordinates": [0, 2],
                    },
                },
            ],
        },
    ),
    ParserCollectionCase(
        name="polygon detection map",
        response={
            "elements": [
                {
                    "type": "way",
                    "id": 1,
                    "nodes": [1, 2, 3, 1],
                    "tags": {"is_polygon_key": "*"},
                },
                {
                    "type": "way",
                    "id": 2,
                    "nodes": [1, 2, 3, 1],
                    "tags": {"is_polygon_key_value": "included_value"},
                },
                {
                    "type": "way",
                    "id": 3,
                    "nodes": [1, 2, 3, 1],
                    "tags": {"is_polygon_key_excluded_value": "*"},
                },
                {
                    "type": "way",
                    "id": 4,
                    "nodes": [1, 2, 3, 1],
                    "tags": {"is_polygon_key": "no"},
                },
                {
                    "type": "way",
                    "id": 5,
                    "nodes": [1, 2, 3, 1],
                    "tags": {"is_polygon_key_value": "not_included_value"},
                },
                {
                    "type": "way",
                    "id": 6,
                    "nodes": [1, 2, 3, 1],
                    "tags": {
                        "is_polygon_key_excluded_value": "excluded_value"
                    },
                },
                {"type": "node", "id": 1, "lat": 1, "lon": 0},
                {"type": "node", "id": 2, "lat": 2, "lon": 0},
                {"type": "node", "id": 3, "lat": 0, "lon": 3},
            ]
        },
        polygon_features={
            "is_polygon_key": True,
            "is_polygon_key_value": {
                "included_values": {"included_value": True}
            },
            "is_polygon_key_excluded_value": {
                "excluded_values": {"excluded_value": True}
            },
        },
        expected={
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "id": "way/1",
                    "properties": {
                        "id": "way/1",
                        "is_polygon_key": "*",
                    },
                    "geometry": {
                        "type": "Polygon",
                        "coordinates": [[[0, 1], [3, 0], [0, 2], [0, 1]]],
                    },
                },
                {
                    "type": "Feature",
                    "id": "way/2",
                    "properties": {
                        "id": "way/2",
                        "is_polygon_key_value": "included_value",
                    },
                    "geometry": {
                        "type": "Polygon",
                        "coordinates": [[[0, 1], [3, 0], [0, 2], [0, 1]]],
                    },
                },
                {
                    "type": "Feature",
                    "id": "way/3",
                    "properties": {
                        "id": "way/3",
                        "is_polygon_key_excluded_value": "*",
                    },
                    "geometry": {
                        "type": "Polygon",
                        "coordinates": [[[0, 1], [3, 0], [0, 2], [0, 1]]],
                    },
                },
                {
                    "type": "Feature",
                    "id": "way/4",
                    "properties": {
                        "id": "way/4",
                        "is_polygon_key": "no",
                    },
                    "geometry": {
                        "type": "LineString",
                        "coordinates": [[0, 1], [0, 2], [3, 0], [0, 1]],
                    },
                },
                {
                    "type": "Feature",
                    "id": "way/5",
                    "properties": {
                        "id": "way/5",
                        "is_polygon_key_value": "not_included_value",
                    },
                    "geometry": {
                        "type": "LineString",
                        "coordinates": [[0, 1], [0, 2], [3, 0], [0, 1]],
                    },
                },
                {
                    "type": "Feature",
                    "id": "way/6",
                    "properties": {
                        "id": "way/6",
                        "is_polygon_key_excluded_value": "excluded_value",
                    },
                    "geometry": {
                        "type": "LineString",
                        "coordinates": [[0, 1], [0, 2], [3, 0], [0, 1]],
                    },
                },
            ],
        },
    ),
    ParserCollectionCase(
        name="tainted way",
        response={
            "elements": [
                {"type": "way", "id": 1, "nodes": [2, 3, 4]},
                {"type": "node", "id": 2, "lat": 0, "lon": 0},
                {"type": "node", "id": 4, "lat": 1, "lon": 1},
            ]
        },
        flat_properties=False,
        expected={
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "id": "way/1",
                    "properties": {
                        "type": "way",
                        "id": 1,
                        "tags": {},
                        "relations": [],
                        "meta": {},
                        "tainted": True,
                    },
                    "geometry": {
                        "type": "LineString",
                        "coordinates": [[0, 0], [1, 1]],
                    },
                }
            ],
        },
    ),
    ParserCollectionCase(
        name="center geometry",
        response={
            "elements": [
                {
                    "type": "way",
                    "id": 1,
                    "center": {"lat": 1.234, "lon": 4.321},
                }
            ]
        },
        flat_properties=False,
        expected={
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "id": "way/1",
                    "properties": {
                        "type": "way",
                        "id": 1,
                        "tags": {},
                        "relations": [],
                        "meta": {},
                        "geometry": "center",
                    },
                    "geometry": {
                        "type": "Point",
                        "coordinates": [4.321, 1.234],
                    },
                }
            ],
        },
    ),
    ParserCollectionCase(
        name="bounds geometry",
        response={
            "elements": [
                {
                    "type": "way",
                    "id": 1,
                    "bounds": {
                        "minlon": 4.321,
                        "minlat": 1.234,
                        "maxlon": 5.321,
                        "maxlat": 2.234,
                    },
                }
            ]
        },
        flat_properties=False,
        expected={
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "id": "way/1",
                    "properties": {
                        "type": "way",
                        "id": 1,
                        "tags": {},
                        "relations": [],
                        "meta": {},
                        "geometry": "bounds",
                    },
                    "geometry": {
                        "type": "Polygon",
                        "coordinates": [
                            [
                                [4.321, 1.234],
                                [5.321, 1.234],
                                [5.321, 2.234],
                                [4.321, 2.234],
                                [4.321, 1.234],
                            ]
                        ],
                    },
                }
            ],
        },
    ),
    ParserCollectionCase(
        name="full geometry",
        response={
            "elements": [
                {
                    "type": "way",
                    "id": 1,
                    "nodes": [1, 2, 3, 1],
                    "tags": {"area": "yes"},
                    "bounds": {
                        "minlon": 0,
                        "minlat": 0,
                        "maxlon": 1,
                        "maxlat": 1,
                    },
                    "geometry": [
                        {"lat": 0, "lon": 0},
                        {"lat": 0, "lon": 1},
                        {"lat": 1, "lon": 1},
                        {"lat": 0, "lon": 0},
                    ],
                }
            ]
        },
        flat_properties=False,
        expected={
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "id": "way/1",
                    "properties": {
                        "type": "way",
                        "id": 1,
                        "tags": {"area": "yes"},
                        "relations": [],
                        "meta": {},
                    },
                    "geometry": {
                        "type": "Polygon",
                        "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 0]]],
                    },
                }
            ],
        },
    ),
    ParserCollectionCase(
        name="higher version wins by default",
        response={
            "elements": [
                {
                    "type": "node",
                    "id": 1,
                    "lat": 1,
                    "lon": 1,
                    "version": 2,
                    "tags": {"dupe": "x", "foo": "bar"},
                },
                {
                    "type": "node",
                    "id": 1,
                    "lat": 1,
                    "lon": 1,
                    "version": 1,
                    "tags": {"dupe": "y", "asd": "fasd"},
                },
            ]
        },
        flat_properties=False,
        expected={
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "id": "node/1",
                    "properties": {
                        "type": "node",
                        "id": 1,
                        "tags": {"dupe": "x", "foo": "bar"},
                        "relations": [],
                        "meta": {"version": 2},
                    },
                    "geometry": {
                        "type": "Point",
                        "coordinates": [1, 1],
                    },
                }
            ],
        },
    ),
    ParserCollectionCase(
        name="custom deduplicator",
        response={
            "elements": [
                {
                    "type": "node",
                    "id": 1,
                    "lat": 1,
                    "lon": 1,
                    "version": 2,
                    "tags": {"dupe": "x", "foo": "bar"},
                },
                {
                    "type": "node",
                    "id": 1,
                    "lat": 1,
                    "lon": 1,
                    "version": 1,
                    "tags": {"dupe": "y", "asd": "fasd"},
                },
            ]
        },
        flat_properties=False,
        deduplicator=_custom_deduplicator,
        expected={
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "id": "node/1",
                    "properties": {
                        "type": "node",
                        "id": 1,
                        "tags": {"dupe": "y", "asd": "fasd"},
                        "relations": [],
                        "meta": {"version": 1},
                    },
                    "geometry": {
                        "type": "Point",
                        "coordinates": [1, 1],
                    },
                }
            ],
        },
    ),
)


CALLBACK_CASES = (
    ParserCallbackCase(
        name="relation multipolygon callback",
        response={
            "elements": [
                {
                    "type": "relation",
                    "id": 1,
                    "tags": {"name": "foo", "type": "multipolygon"},
                    "members": [{"type": "way", "ref": 1, "role": "outer"}],
                },
                {
                    "type": "way",
                    "id": 1,
                    "nodes": [2, 3, 4, 5, 2],
                    "tags": {},
                },
                {"type": "node", "id": 2, "lat": 0, "lon": 0},
                {"type": "node", "id": 3, "lat": 1, "lon": 0},
                {"type": "node", "id": 4, "lat": 1, "lon": 1},
                {"type": "node", "id": 5, "lat": 0, "lon": 1},
            ]
        },
        flat_properties=False,
        expected_features=[
            {
                "type": "Feature",
                "id": "relation/1",
                "properties": {
                    "type": "relation",
                    "id": 1,
                    "tags": {"name": "foo", "type": "multipolygon"},
                    "relations": [],
                    "meta": {},
                },
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 1], [0, 0]]],
                },
            }
        ],
    ),
)


@pytest.mark.parametrize(
    "case",
    REFERENCE_CASES,
    ids=lambda case: case.name,
)
def test_reference_feature_collections(case: ParserCollectionCase) -> None:
    _assert_collection_case(case)


@pytest.mark.parametrize(
    "case",
    CALLBACK_CASES,
    ids=lambda case: case.name,
)
def test_feature_callbacks(case: ParserCallbackCase) -> None:
    _assert_callback_case(case)


def test_route_relation_joins_reversed_way_segments() -> None:
    from osminfo.overpass.json_parser import OverpassJsonParser

    parser = OverpassJsonParser.from_response(
        {
            "elements": [
                {
                    "type": "relation",
                    "id": 1,
                    "tags": {"type": "route"},
                    "members": [
                        {"type": "way", "ref": 2, "role": "forward"},
                        {"type": "way", "ref": 3, "role": "forward"},
                    ],
                },
                {"type": "way", "id": 2, "nodes": [10, 11]},
                {"type": "way", "id": 3, "nodes": [12, 11]},
                {"type": "node", "id": 10, "lat": 0.0, "lon": 0.0},
                {"type": "node", "id": 11, "lat": 1.0, "lon": 1.0},
                {"type": "node", "id": 12, "lat": 2.0, "lon": 2.0},
            ]
        },
        flat_properties=False,
    )

    result = parser.to_feature_collection()

    coordinates = result["features"][0]["geometry"]["coordinates"]

    assert result["features"][0]["geometry"]["type"] == "LineString"
    assert coordinates in (
        [[0.0, 0.0], [1.0, 1.0], [2.0, 2.0]],
        [[2.0, 2.0], [1.0, 1.0], [0.0, 0.0]],
    )


def _collect_features(elements: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    from osminfo.overpass.json_parser import OverpassJsonParser

    result = OverpassJsonParser.from_response(
        {"elements": elements},
        flat_properties=False,
    ).to_feature_collection()
    return result["features"]


@pytest.mark.parametrize(
    ("elements",),
    [
        ([{"type": "relation", "id": 1, "tags": {"type": "multipolygon"}}],),
        (
            [
                {
                    "type": "relation",
                    "id": 1,
                    "tags": {"type": "multipolygon"},
                    "members": [
                        {"type": "way", "ref": 1, "role": "outer"},
                    ],
                },
            ],
        ),
        (
            [
                {
                    "type": "relation",
                    "id": 1,
                    "tags": {"type": "multipolygon"},
                    "members": [
                        {"type": "way", "ref": 1, "role": "outer"},
                    ],
                },
                {"type": "way", "id": 1},
            ],
        ),
        ([{"type": "relation", "id": 1, "tags": {"type": "route"}}],),
        (
            [
                {
                    "type": "relation",
                    "id": 1,
                    "tags": {"type": "route"},
                    "members": [
                        {"type": "way", "ref": 1, "role": "forward"},
                    ],
                },
            ],
        ),
        (
            [
                {
                    "type": "relation",
                    "id": 1,
                    "tags": {"type": "route"},
                    "members": [
                        {"type": "way", "ref": 1, "role": "forward"},
                    ],
                },
                {"type": "way", "id": 1},
            ],
        ),
    ],
)
def test_upstream_invalid_relation_cases_return_no_features(
    elements: List[Dict[str, Any]],
) -> None:
    assert _collect_features(elements) == []


def test_upstream_outer_way_tagging_keeps_relation_and_outer_way() -> None:
    features = _collect_features(
        [
            {
                "type": "relation",
                "id": 1,
                "tags": {"type": "multipolygon", "amenity": "xxx"},
                "members": [
                    {"type": "way", "ref": 2, "role": "outer"},
                    {"type": "way", "ref": 3, "role": "inner"},
                ],
            },
            {
                "type": "way",
                "id": 2,
                "nodes": [4, 5, 6, 7, 4],
                "tags": {"amenity": "yyy"},
            },
            {"type": "way", "id": 3, "nodes": [8, 9, 10, 8]},
            {"type": "node", "id": 4, "lat": -1.0, "lon": -1.0},
            {"type": "node", "id": 5, "lat": -1.0, "lon": 1.0},
            {"type": "node", "id": 6, "lat": 1.0, "lon": 1.0},
            {"type": "node", "id": 7, "lat": 1.0, "lon": -1.0},
            {"type": "node", "id": 8, "lat": -0.5, "lon": 0.0},
            {"type": "node", "id": 9, "lat": 0.5, "lon": 0.0},
            {"type": "node", "id": 10, "lat": 0.0, "lon": 0.5},
        ]
    )

    assert [feature["id"] for feature in features] == ["relation/1", "way/2"]


def test_upstream_non_matching_inner_and_outer_rings() -> None:
    complex_features = _collect_features(
        [
            {
                "type": "relation",
                "id": 1,
                "tags": {"type": "multipolygon"},
                "members": [
                    {"type": "way", "ref": 2, "role": "outer"},
                    {"type": "way", "ref": -1, "role": "outer"},
                    {"type": "way", "ref": 3, "role": "inner"},
                ],
            },
            {"type": "way", "id": 2, "nodes": [4, 5, 6, 7, 4]},
            {"type": "node", "id": 4, "lat": 0.0, "lon": 0.0},
            {"type": "node", "id": 5, "lat": 1.0, "lon": 0.0},
            {"type": "node", "id": 6, "lat": 1.0, "lon": 1.0},
            {"type": "node", "id": 7, "lat": 0.0, "lon": 1.0},
            {"type": "way", "id": 3, "nodes": [8, 9, 10, 8]},
            {"type": "node", "id": 8, "lat": 3.0, "lon": 3.0},
            {"type": "node", "id": 9, "lat": 4.0, "lon": 3.0},
            {"type": "node", "id": 10, "lat": 3.0, "lon": 4.0},
        ]
    )

    assert len(complex_features) == 1
    assert complex_features[0]["id"] == "relation/1"
    assert complex_features[0]["geometry"]["type"] == "Polygon"
    assert len(complex_features[0]["geometry"]["coordinates"]) == 1

    simple_features = _collect_features(
        [
            {
                "type": "relation",
                "id": 1,
                "tags": {"type": "multipolygon"},
                "members": [
                    {"type": "way", "ref": 2, "role": "outer"},
                    {"type": "way", "ref": 3, "role": "inner"},
                ],
            },
            {"type": "way", "id": 2, "nodes": [4, 5, 6, 7, 4]},
            {"type": "node", "id": 4, "lat": 0.0, "lon": 0.0},
            {"type": "node", "id": 5, "lat": 1.0, "lon": 0.0},
            {"type": "node", "id": 6, "lat": 1.0, "lon": 1.0},
            {"type": "node", "id": 7, "lat": 0.0, "lon": 1.0},
            {"type": "way", "id": 3, "nodes": [8, 9, 10, 8]},
            {"type": "node", "id": 8, "lat": 3.0, "lon": 3.0},
            {"type": "node", "id": 9, "lat": 4.0, "lon": 3.0},
            {"type": "node", "id": 10, "lat": 3.0, "lon": 4.0},
        ]
    )

    assert len(simple_features) == 1
    assert simple_features[0]["id"] == "way/2"
    assert simple_features[0]["geometry"]["type"] == "Polygon"
    assert len(simple_features[0]["geometry"]["coordinates"]) == 1


def test_upstream_non_trivial_ring_building() -> None:
    way_order_features = _collect_features(
        [
            {
                "type": "relation",
                "id": 1,
                "tags": {"type": "multipolygon"},
                "members": [
                    {"type": "way", "ref": 1, "role": "outer"},
                    {"type": "way", "ref": 3, "role": "outer"},
                    {"type": "way", "ref": 2, "role": "outer"},
                ],
            },
            {"type": "way", "id": 1, "nodes": [1, 2]},
            {"type": "way", "id": 2, "nodes": [2, 3]},
            {"type": "way", "id": 3, "nodes": [3, 1]},
            {"type": "node", "id": 1, "lat": 1.0, "lon": 0.0},
            {"type": "node", "id": 2, "lat": 2.0, "lon": 0.0},
            {"type": "node", "id": 3, "lat": 3.0, "lon": 0.0},
        ]
    )

    assert len(way_order_features) == 1
    assert way_order_features[0]["id"] == "relation/1"
    assert way_order_features[0]["geometry"]["type"] == "Polygon"
    assert len(way_order_features[0]["geometry"]["coordinates"]) == 1
    assert len(way_order_features[0]["geometry"]["coordinates"][0]) == 4

    way_direction_features = _collect_features(
        [
            {
                "type": "relation",
                "id": 1,
                "tags": {"type": "multipolygon"},
                "members": [
                    {"type": "way", "ref": 1, "role": "outer"},
                    {"type": "way", "ref": 2, "role": "outer"},
                    {"type": "way", "ref": 3, "role": "outer"},
                    {"type": "way", "ref": 4, "role": "outer"},
                    {"type": "way", "ref": 5, "role": "outer"},
                    {"type": "way", "ref": 6, "role": "outer"},
                ],
            },
            {"type": "way", "id": 1, "nodes": [1, 2]},
            {"type": "way", "id": 2, "nodes": [2, 3]},
            {"type": "way", "id": 3, "nodes": [4, 3]},
            {"type": "way", "id": 4, "nodes": [5, 4]},
            {"type": "way", "id": 5, "nodes": [5, 6]},
            {"type": "way", "id": 6, "nodes": [1, 6]},
            {"type": "node", "id": 1, "lat": 1.0, "lon": 0.0},
            {"type": "node", "id": 2, "lat": 2.0, "lon": 0.0},
            {"type": "node", "id": 3, "lat": 3.0, "lon": 0.0},
            {"type": "node", "id": 4, "lat": 4.0, "lon": 0.0},
            {"type": "node", "id": 5, "lat": 5.0, "lon": 0.0},
            {"type": "node", "id": 6, "lat": 6.0, "lon": 0.0},
        ]
    )

    assert len(way_direction_features) == 1
    assert way_direction_features[0]["id"] == "relation/1"
    assert way_direction_features[0]["geometry"]["type"] == "Polygon"
    assert len(way_direction_features[0]["geometry"]["coordinates"]) == 1
    assert len(way_direction_features[0]["geometry"]["coordinates"][0]) == 7


def test_upstream_unclosed_ring_cases() -> None:
    mismatched_features = _collect_features(
        [
            {
                "type": "relation",
                "id": 1,
                "tags": {"type": "multipolygon"},
                "members": [
                    {"type": "way", "ref": 1, "role": "outer"},
                    {"type": "way", "ref": 2, "role": "outer"},
                ],
            },
            {"type": "way", "id": 1, "nodes": [1, 2, 3, 4]},
            {"type": "way", "id": 2, "nodes": [3, 2]},
            {"type": "node", "id": 1, "lat": 1.0, "lon": 0.0},
            {"type": "node", "id": 2, "lat": 2.0, "lon": 0.0},
            {"type": "node", "id": 3, "lat": 3.0, "lon": 0.0},
            {"type": "node", "id": 4, "lat": 4.0, "lon": 0.0},
        ]
    )

    assert len(mismatched_features) == 1
    assert mismatched_features[0]["id"] == "relation/1"
    assert mismatched_features[0]["geometry"]["type"] == "Polygon"
    assert len(mismatched_features[0]["geometry"]["coordinates"]) == 1
    assert len(mismatched_features[0]["geometry"]["coordinates"][0]) == 4
    assert mismatched_features[0]["properties"].get("tainted") is not True

    matching_features = _collect_features(
        [
            {
                "type": "relation",
                "id": 1,
                "tags": {"type": "multipolygon"},
                "members": [
                    {"type": "way", "ref": 1, "role": "outer"},
                    {"type": "way", "ref": 2, "role": "outer"},
                ],
            },
            {"type": "way", "id": 1, "nodes": [1, 2]},
            {"type": "way", "id": 2, "nodes": [2, 3, 4]},
            {"type": "node", "id": 1, "lat": 1.0, "lon": 0.0},
            {"type": "node", "id": 2, "lat": 2.0, "lon": 0.0},
            {"type": "node", "id": 3, "lat": 3.0, "lon": 0.0},
            {"type": "node", "id": 4, "lat": 4.0, "lon": 0.0},
        ]
    )

    assert len(matching_features) == 1
    assert matching_features[0]["id"] == "relation/1"
    assert matching_features[0]["geometry"]["type"] == "Polygon"
    assert len(matching_features[0]["geometry"]["coordinates"]) == 1
    assert len(matching_features[0]["geometry"]["coordinates"][0]) == 4
    assert matching_features[0]["properties"].get("tainted") is not True


def test_upstream_tainted_simple_multipolygon_cases() -> None:
    missing_way_features = _collect_features(
        [
            {
                "type": "relation",
                "id": 1,
                "tags": {"type": "multipolygon"},
                "members": [
                    {"type": "way", "ref": 2, "role": "outer"},
                    {"type": "way", "ref": 3, "role": "inner"},
                ],
            },
            {"type": "way", "id": 2, "nodes": [3, 4, 5, 3]},
            {"type": "node", "id": 3, "lat": 0.0, "lon": 0.0},
            {"type": "node", "id": 4, "lat": 0.0, "lon": 1.0},
            {"type": "node", "id": 5, "lat": 1.0, "lon": 0.0},
        ]
    )

    assert len(missing_way_features) == 1
    assert missing_way_features[0]["id"] == "way/2"
    assert missing_way_features[0]["properties"].get("tainted") is True

    missing_nodes_features = _collect_features(
        [
            {
                "type": "relation",
                "id": 1,
                "tags": {"type": "multipolygon"},
                "members": [
                    {"type": "way", "ref": 2, "role": "outer"},
                ],
            },
            {"type": "way", "id": 2, "nodes": [3, 4, 5, 3]},
        ]
    )

    assert missing_nodes_features == []

    missing_node_features = _collect_features(
        [
            {
                "type": "relation",
                "id": 1,
                "tags": {"type": "multipolygon"},
                "members": [
                    {"type": "way", "ref": 2, "role": "outer"},
                ],
            },
            {"type": "way", "id": 2, "nodes": [3, 4, 5, 6, 3]},
            {"type": "node", "id": 3, "lat": 0.0, "lon": 0.0},
            {"type": "node", "id": 4, "lat": 0.0, "lon": 1.0},
            {"type": "node", "id": 5, "lat": 1.0, "lon": 0.0},
        ]
    )

    assert len(missing_node_features) == 1
    assert missing_node_features[0]["id"] == "way/2"
    assert missing_node_features[0]["properties"].get("tainted") is True


def test_upstream_tainted_multipolygon_cases() -> None:
    missing_way_features = _collect_features(
        [
            {
                "type": "relation",
                "id": 1,
                "tags": {"type": "multipolygon"},
                "members": [
                    {"type": "way", "ref": 2, "role": "outer"},
                    {"type": "way", "ref": 3, "role": "outer"},
                ],
            },
            {"type": "way", "id": 2, "nodes": [4, 5, 6, 4]},
            {"type": "node", "id": 4, "lat": 0.0, "lon": 0.0},
            {"type": "node", "id": 5, "lat": 0.0, "lon": 1.0},
            {"type": "node", "id": 6, "lat": 1.0, "lon": 0.0},
        ]
    )

    assert len(missing_way_features) == 1
    assert missing_way_features[0]["id"] == "relation/1"
    assert missing_way_features[0]["properties"].get("tainted") is True

    missing_node_features = _collect_features(
        [
            {
                "type": "relation",
                "id": 1,
                "tags": {"type": "multipolygon"},
                "members": [
                    {"type": "way", "ref": 2, "role": "outer"},
                    {"type": "way", "ref": 3, "role": "outer"},
                ],
            },
            {"type": "way", "id": 2, "nodes": [4, 5, 6, 7, 4]},
            {"type": "way", "id": 3, "nodes": [4, 5, 6, 4]},
            {"type": "node", "id": 4, "lat": 0.0, "lon": 0.0},
            {"type": "node", "id": 5, "lat": 0.0, "lon": 1.0},
            {"type": "node", "id": 6, "lat": 1.0, "lon": 0.0},
        ]
    )

    assert len(missing_node_features) == 1
    assert missing_node_features[0]["id"] == "relation/1"
    assert missing_node_features[0]["properties"].get("tainted") is True


@pytest.mark.parametrize(
    ("elements",),
    [
        (
            [
                {
                    "type": "relation",
                    "id": 1,
                    "tags": {"type": "multipolygon"},
                    "members": [
                        {"type": "way", "ref": 2, "role": "outer"},
                        {"type": "way", "ref": 3, "role": "outer"},
                    ],
                },
                {"type": "way", "id": 2, "nodes": [4, 5, 6]},
                {"type": "way", "id": 3, "nodes": [6, 4]},
            ],
        ),
        (
            [
                {
                    "type": "relation",
                    "id": 1,
                    "tags": {"type": "multipolygon"},
                    "members": [
                        {"type": "way", "ref": 2, "role": "inner"},
                    ],
                },
                {"type": "way", "id": 2, "nodes": [3, 4, 5, 3]},
                {"type": "node", "id": 3, "lat": 0.0, "lon": 0.0},
                {"type": "node", "id": 4, "lat": 1.0, "lon": 1.0},
                {"type": "node", "id": 5, "lat": 1.0, "lon": 0.0},
            ],
        ),
        (
            [
                {
                    "type": "relation",
                    "id": 1,
                    "tags": {"type": "multipolygon"},
                    "members": [
                        {"type": "way", "ref": 2, "role": "outer"},
                        {"type": "way", "ref": 3, "role": "outer"},
                    ],
                },
                {"type": "way", "id": 2, "nodes": [4, 5, 6, 4]},
                {"type": "node", "id": 4, "lat": 0.0, "lon": 0.0},
                {"type": "node", "id": 5, "lat": 1.0, "lon": 1.0},
            ],
        ),
    ],
)
def test_upstream_degenerate_multipolygon_cases_return_no_features(
    elements: List[Dict[str, Any]],
) -> None:
    assert _collect_features(elements) == []


def test_uninteresting_tags_callback() -> None:
    case = ParserCollectionCase(
        name="uninteresting tags callback",
        response={
            "elements": [
                {"type": "way", "id": 1, "nodes": [2, 3]},
                {
                    "type": "node",
                    "id": 2,
                    "lat": 1,
                    "lon": 0,
                    "tags": {"tag": "0"},
                },
                {
                    "type": "node",
                    "id": 3,
                    "lat": 2,
                    "lon": 0,
                    "tags": {"tag": "1"},
                },
            ]
        },
        flat_properties=False,
        uninteresting_tags=_uninteresting_tags_callback,
        expected={
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "id": "way/1",
                    "properties": {
                        "type": "way",
                        "id": 1,
                        "tags": {},
                        "relations": [],
                        "meta": {},
                    },
                    "geometry": {
                        "type": "LineString",
                        "coordinates": [[0, 1], [0, 2]],
                    },
                },
                {
                    "type": "Feature",
                    "id": "node/3",
                    "properties": {
                        "type": "node",
                        "id": 3,
                        "tags": {"tag": "1"},
                        "relations": [],
                        "meta": {},
                    },
                    "geometry": {
                        "type": "Point",
                        "coordinates": [0, 2],
                    },
                },
            ],
        },
    )
    _assert_collection_case(case)


def test_polygon_features_callback() -> None:
    case = ParserCollectionCase(
        name="polygon detection callback",
        response={
            "elements": [
                {
                    "type": "way",
                    "id": 1,
                    "nodes": [1, 2, 3, 1],
                    "tags": {"tag": "1"},
                },
                {
                    "type": "way",
                    "id": 2,
                    "nodes": [1, 2, 3, 1],
                    "tags": {"tag": "0"},
                },
                {"type": "node", "id": 1, "lat": 1, "lon": 0},
                {"type": "node", "id": 2, "lat": 2, "lon": 0},
                {"type": "node", "id": 3, "lat": 0, "lon": 3},
            ]
        },
        polygon_features=_polygon_features_callback,
        expected={
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "id": "way/1",
                    "properties": {"id": "way/1", "tag": "1"},
                    "geometry": {
                        "type": "Polygon",
                        "coordinates": [[[0, 1], [3, 0], [0, 2], [0, 1]]],
                    },
                },
                {
                    "type": "Feature",
                    "id": "way/2",
                    "properties": {"id": "way/2", "tag": "0"},
                    "geometry": {
                        "type": "LineString",
                        "coordinates": [[0, 1], [0, 2], [3, 0], [0, 1]],
                    },
                },
            ],
        },
    )
    _assert_collection_case(case)


def test_feature_callback_does_not_materialize_collection_cache() -> None:
    from osminfo.overpass.json_parser import OverpassJsonParser

    parser = OverpassJsonParser.from_response(
        {"elements": [{"type": "node", "id": 1, "lat": 1.234, "lon": 4.321}]}
    )

    callback_features: List[Dict[str, Any]] = []

    assert parser.to_feature_collection(callback_features.append) is True
    assert callback_features == [
        {
            "type": "Feature",
            "id": "node/1",
            "properties": {
                "type": "node",
                "id": 1,
                "tags": {},
                "relations": [],
                "meta": {},
            },
            "geometry": {
                "type": "Point",
                "coordinates": [4.321, 1.234],
            },
        }
    ]
    assert parser._cached_features is None
