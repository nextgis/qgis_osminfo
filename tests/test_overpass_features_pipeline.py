# pyright: reportMissingImports=false
# ruff: noqa: I001

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

import json
from pathlib import Path
from typing import Any, Dict


def test_parse_relation_collection_geometry() -> None:
    from osminfo.overpass.json_parser import OverpassJsonParser
    from osminfo.openstreetmap.models import OsmGeometryCollection

    raw_relation: Dict[str, Any] = {
        "type": "relation",
        "id": 77,
        "members": [
            {"type": "node", "id": 1, "lon": 30.0, "lat": 60.0},
            {
                "type": "way",
                "id": 2,
                "geometry": [
                    {"lon": 30.0, "lat": 60.0},
                    {"lon": 31.0, "lat": 61.0},
                ],
            },
        ],
    }

    geometry = OverpassJsonParser.from_element(
        raw_relation
    ).geometry_for_element(raw_relation)

    assert isinstance(geometry, OsmGeometryCollection)
    assert geometry.points is not None
    assert geometry.lines is not None
    assert geometry.polygons is None


def test_boundary_relation_keeps_member_point_and_marks_incomplete() -> None:
    from osminfo.openstreetmap.features_parser import OsmFeaturesParser
    from osminfo.openstreetmap.features_tree_model import OsmFeaturesTreeModel
    from osminfo.openstreetmap.models import (
        OsmResultGroup,
        OsmResultGroupType,
        OsmResultTree,
    )
    from osminfo.overpass.json_parser import OverpassJsonParser
    from osminfo.openstreetmap.models import OsmGeometryCollection

    raw_relation: Dict[str, Any] = {
        "type": "relation",
        "id": 46294,
        "members": [
            {
                "type": "way",
                "ref": 170281870,
                "role": "outer",
                "geometry": [
                    {"lat": 0.0, "lon": 0.0},
                    {"lat": 0.0, "lon": 1.0},
                    None,
                    {"lat": 1.0, "lon": 0.0},
                    {"lat": 0.0, "lon": 0.0},
                ],
            },
            {
                "type": "node",
                "ref": 963946611,
                "role": "admin_centre",
                "lat": 0.5,
                "lon": 0.5,
            },
        ],
        "tags": {
            "boundary": "administrative",
            "name": "Oyace",
            "type": "boundary",
        },
    }

    geometry = OverpassJsonParser.from_element(
        raw_relation
    ).geometry_for_element(raw_relation)

    assert isinstance(geometry, OsmGeometryCollection)
    assert geometry.points is not None
    assert geometry.polygons is not None
    assert geometry.lines is None

    element = OsmFeaturesParser("en").parse_element(raw_relation)

    assert element is not None
    assert element.geometry_type() is not None
    assert element.geometry_type().name == "COLLECTION"
    assert element.is_incomplete is True
    assert all(tag.key != "Attention" for tag in element.tag_items)

    model = OsmFeaturesTreeModel()
    model.set_result_tree(
        OsmResultTree(
            groups=(
                OsmResultGroup(
                    group_type=OsmResultGroupType.SEARCH,
                    title="Search results",
                    elements=(element,),
                ),
            )
        )
    )
    notice_index = model.index(0, 0, model.index(0, 0, model.index(0, 0)))
    assert model.data(notice_index) == "Attention"
    assert model.data(
        model.index(0, 1, model.index(0, 0, model.index(0, 0)))
    ) == ("incomplete geometry (e.g. some nodes missing)")


def test_boundary_relation_with_empty_member_geometry_is_incomplete() -> None:
    from osminfo.openstreetmap.features_parser import OsmFeaturesParser

    raw_relation: Dict[str, Any] = {
        "type": "relation",
        "id": 46294,
        "members": [
            {
                "type": "way",
                "ref": 170281870,
                "role": "outer",
                "geometry": [
                    None,
                    None,
                    {"lat": 45.8116207, "lon": 7.4071278},
                    {"lat": 45.8123552, "lon": 7.4068752},
                    {"lat": 45.8128668, "lon": 7.4067705},
                    {"lat": 45.8116207, "lon": 7.4071278},
                ],
            },
            {
                "type": "way",
                "ref": 170289674,
                "role": "outer",
                "geometry": [],
            },
            {
                "type": "way",
                "ref": 170281883,
                "role": "outer",
                "geometry": [
                    {"lat": 45.8404692, "lon": 7.4670997},
                    {"lat": 45.8403739, "lon": 7.4667031},
                    {"lat": 45.8401183, "lon": 7.4657701},
                    {"lat": 45.8404692, "lon": 7.4670997},
                ],
            },
            {
                "type": "node",
                "ref": 963946611,
                "role": "admin_centre",
                "lat": 45.8507653,
                "lon": 7.3828659,
            },
        ],
        "tags": {
            "admin_level": "8",
            "boundary": "administrative",
            "name": "Oyace",
            "type": "boundary",
        },
    }

    element = OsmFeaturesParser("en").parse_element(raw_relation)

    assert element is not None
    assert element.is_incomplete is True


def test_multipolygon_relation_with_member_geometry_is_complete() -> None:
    from osminfo.openstreetmap.features_parser import OsmFeaturesParser
    from osminfo.overpass.json_parser import OverpassJsonParser

    raw_relation: Dict[str, Any] = {
        "type": "relation",
        "id": 9036465,
        "bounds": {
            "minlat": 46.9475579,
            "minlon": 7.4544908,
            "maxlat": 46.9478332,
            "maxlon": 7.4547561,
        },
        "members": [
            {
                "type": "way",
                "ref": 647527709,
                "role": "outer",
                "geometry": [
                    {"lat": 46.9476564, "lon": 7.4546958},
                    {"lat": 46.9476508, "lon": 7.4546840},
                    {"lat": 46.9478332, "lon": 7.4545540},
                    {"lat": 46.9478232, "lon": 7.4545224},
                    {"lat": 46.9478131, "lon": 7.4544908},
                    {"lat": 46.9476376, "lon": 7.4546265},
                    {"lat": 46.9475579, "lon": 7.4546959},
                    {"lat": 46.9475787, "lon": 7.4547561},
                    {"lat": 46.9476564, "lon": 7.4546958},
                ],
            },
            {
                "type": "way",
                "ref": 647527710,
                "role": "inner",
                "geometry": [
                    {"lat": 46.9476902, "lon": 7.4546163},
                    {"lat": 46.9476725, "lon": 7.4546306},
                    {"lat": 46.9476824, "lon": 7.4546556},
                    {"lat": 46.9477188, "lon": 7.4546296},
                    {"lat": 46.9477116, "lon": 7.4546083},
                    {"lat": 46.9477107, "lon": 7.4546103},
                    {"lat": 46.9477098, "lon": 7.4546121},
                    {"lat": 46.9477087, "lon": 7.4546139},
                    {"lat": 46.9477073, "lon": 7.4546155},
                    {"lat": 46.9477060, "lon": 7.4546168},
                    {"lat": 46.9477045, "lon": 7.4546178},
                    {"lat": 46.9477030, "lon": 7.4546187},
                    {"lat": 46.9477013, "lon": 7.4546194},
                    {"lat": 46.9476998, "lon": 7.4546196},
                    {"lat": 46.9476984, "lon": 7.4546197},
                    {"lat": 46.9476970, "lon": 7.4546196},
                    {"lat": 46.9476955, "lon": 7.4546193},
                    {"lat": 46.9476942, "lon": 7.4546188},
                    {"lat": 46.9476927, "lon": 7.4546181},
                    {"lat": 46.9476914, "lon": 7.4546173},
                    {"lat": 46.9476902, "lon": 7.4546163},
                ],
            },
        ],
        "tags": {
            "building": "apartments",
            "type": "multipolygon",
        },
    }

    parser = OverpassJsonParser.from_element(raw_relation)

    assert parser.is_incomplete_element(raw_relation) is False

    feature = parser.feature_for_element(raw_relation)
    assert feature is not None
    assert feature["properties"].get("tainted") is not True

    element = OsmFeaturesParser("en").parse_element(raw_relation)

    assert element is not None
    assert element.geometry_type() is not None
    assert element.geometry_type().name == "POLYGON"
    assert element.is_incomplete is False


def test_boundary_relation_with_subarea_member_is_complete() -> None:
    from osminfo.openstreetmap.features_parser import OsmFeaturesParser
    from osminfo.overpass.json_parser import OverpassJsonParser

    raw_relation: Dict[str, Any] = {
        "type": "relation",
        "id": 51701,
        "members": [
            {
                "type": "way",
                "ref": 1001,
                "role": "outer",
                "geometry": [
                    {"lat": 46.0, "lon": 7.0},
                    {"lat": 46.0, "lon": 8.0},
                    {"lat": 47.0, "lon": 8.0},
                    {"lat": 46.0, "lon": 7.0},
                ],
            },
            {
                "type": "relation",
                "ref": 1690227,
                "role": "subarea",
            },
        ],
        "tags": {
            "admin_level": "2",
            "boundary": "administrative",
            "name": "Switzerland",
            "type": "boundary",
        },
    }

    parser = OverpassJsonParser.from_element(raw_relation)

    assert parser.is_incomplete_element(raw_relation) is False

    feature = parser.feature_for_element(raw_relation)
    assert feature is not None
    assert feature["properties"].get("tainted") is not True

    element = OsmFeaturesParser("en").parse_element(raw_relation)

    assert element is not None
    assert element.geometry_type() is not None
    assert element.geometry_type().name == "POLYGON"
    assert element.is_incomplete is False


def test_features_parser_builds_groups_and_sorts_enclosing() -> None:
    from osminfo.openstreetmap.features_parser import OsmFeaturesParser
    from osminfo.openstreetmap.models import OsmResultGroupType

    parser = OsmFeaturesParser(locale_name="en")
    raw_search = [
        {
            "type": "node",
            "id": 10,
            "lon": 30.0,
            "lat": 60.0,
            "tags": {
                "name:en": "Central Cafe",
                "website": "https://example.com/cafe",
                "amenity": "cafe",
            },
        }
    ]
    raw_nearby = [
        {
            "type": "way",
            "id": 20,
            "geometry": [
                {"lon": 30.0, "lat": 60.0},
                {"lon": 30.1, "lat": 60.0},
            ],
            "tags": {"highway": "service"},
        }
    ]
    raw_enclosing = [
        {
            "type": "way",
            "id": 30,
            "bounds": {
                "minlon": 29.0,
                "minlat": 59.0,
                "maxlon": 32.0,
                "maxlat": 62.0,
            },
            "geometry": [
                {"lon": 29.0, "lat": 59.0},
                {"lon": 32.0, "lat": 59.0},
                {"lon": 32.0, "lat": 62.0},
                {"lon": 29.0, "lat": 59.0},
            ],
            "tags": {"boundary": "administrative"},
        },
        {
            "type": "way",
            "id": 31,
            "bounds": {
                "minlon": 29.9,
                "minlat": 59.9,
                "maxlon": 30.2,
                "maxlat": 60.2,
            },
            "geometry": [
                {"lon": 29.9, "lat": 59.9},
                {"lon": 30.2, "lat": 59.9},
                {"lon": 30.2, "lat": 60.2},
                {"lon": 29.9, "lat": 59.9},
            ],
            "tags": {"landuse": "residential"},
        },
    ]

    result_tree = parser.parse_result_tree(
        nearby_elements=raw_nearby,
        enclosing_elements=raw_enclosing,
        search_elements=raw_search,
        titles={
            OsmResultGroupType.SEARCH: "Search results",
            OsmResultGroupType.NEARBY: "Nearby features",
            OsmResultGroupType.ENCLOSING: "Is inside",
        },
    )

    assert [group.group_type for group in result_tree.groups] == [
        OsmResultGroupType.SEARCH,
        OsmResultGroupType.NEARBY,
        OsmResultGroupType.ENCLOSING,
    ]
    assert result_tree.groups[0].elements[0].title == "Central Cafe"
    assert result_tree.groups[0].elements[0].tag_items[2].has_links
    assert [element.osm_id for element in result_tree.groups[2].elements] == [
        31,
        30,
    ]
    assert result_tree.groups[2].elements[1].max_scale is not None
    assert result_tree.groups[2].elements[0].max_scale is not None
    assert (
        result_tree.groups[2].elements[0].max_scale
        < result_tree.groups[2].elements[1].max_scale
    )


def test_parse_task_builds_result_tree() -> None:
    from osminfo.openstreetmap.features_parse_task import (
        OverpassFeaturesParseTask,
    )
    from osminfo.openstreetmap.models import OsmResultGroupType

    task = OverpassFeaturesParseTask(
        locale_name="en",
        nearby_elements=[],
        enclosing_elements=[],
        search_elements=[
            {
                "type": "node",
                "id": 15,
                "lon": 30.0,
                "lat": 60.0,
                "tags": {"name": "Library"},
            }
        ],
        titles={
            OsmResultGroupType.SEARCH: "Search results",
            OsmResultGroupType.NEARBY: "Nearby features",
            OsmResultGroupType.ENCLOSING: "Is inside",
        },
    )

    assert task.run() is True
    assert len(task.result_tree.groups) == 1
    assert task.result_tree.groups[0].elements[0].title == "Library"


def test_features_parser_preserves_upstream_relation_membership() -> None:
    from osminfo.openstreetmap.features_parser import OsmFeaturesParser
    from osminfo.openstreetmap.models import OsmResultGroupType

    parser = OsmFeaturesParser(locale_name="en")
    result_group = parser.parse_group(
        OsmResultGroupType.SEARCH,
        "Search results",
        [
            {
                "type": "relation",
                "id": 501,
                "tags": {"type": "multipolygon", "name": "Square"},
                "members": [{"type": "way", "ref": 201, "role": "outer"}],
            },
            {
                "type": "way",
                "id": 201,
                "nodes": [1, 2, 3, 1],
                "tags": {"building": "yes"},
            },
            {"type": "node", "id": 1, "lat": 0.0, "lon": 0.0},
            {"type": "node", "id": 2, "lat": 0.0, "lon": 1.0},
            {"type": "node", "id": 3, "lat": 1.0, "lon": 0.0},
        ],
    )

    parsed_way = next(
        element
        for element in result_group.elements
        if element.element_type.value == "way"
    )

    assert parsed_way.is_relation_member is True
    assert parsed_way.relation_role == "outer"
    assert len(parsed_way.relation_refs) == 1
    assert parsed_way.relation_refs[0].relation_id == 501
    assert parsed_way.relation_refs[0].role == "outer"
    assert parsed_way.relation_refs[0].relation_tags == {
        "type": "multipolygon",
        "name": "Square",
    }


def test_tree_model_exposes_element_and_tag_links() -> None:
    from qgis.core import QgsGeometry, QgsPointXY
    from qgis.PyQt.QtCore import Qt
    from qgis.PyQt.QtGui import QIcon

    from osminfo.openstreetmap.features_tree_model import OsmFeaturesTreeModel
    from osminfo.openstreetmap.models import (
        OsmElement,
        OsmElementType,
        OsmResultGroup,
        OsmResultGroupType,
        OsmResultTree,
        OsmTag,
    )
    from osminfo.openstreetmap.tag2link import TagLink

    model = OsmFeaturesTreeModel()
    tag = OsmTag(
        key="website",
        value="https://example.com",
        links=(TagLink(title="website", url="https://example.com"),),
    )
    element = OsmElement(
        osm_id=101,
        element_type=OsmElementType.NODE,
        title="Feature title",
        geometry=QgsGeometry.fromPointXY(QgsPointXY(30.0, 60.0)),
        tag_items=(tag,),
        tags={"website": "https://example.com"},
    )
    model.set_result_tree(
        OsmResultTree(
            groups=(
                OsmResultGroup(
                    group_type=OsmResultGroupType.SEARCH,
                    title="Search results",
                    elements=(element,),
                ),
            )
        )
    )

    group_index = model.index(0, 0)
    feature_index = model.index(0, 0, group_index)
    tag_index = model.index(0, 1, feature_index)

    assert model.rowCount() == 1
    assert (
        model.data(group_index, Qt.ItemDataRole.DisplayRole)
        == "Search results (1)"
    )
    assert (
        model.data(feature_index, Qt.ItemDataRole.DisplayRole)
        == "Feature title"
    )
    assert model.osm_element_for_index(tag_index).osm_id == 101
    assert model.tag_links_for_index(tag_index)[0].url == "https://example.com"
    icon = model.data(feature_index, Qt.ItemDataRole.DecorationRole)
    assert isinstance(icon, QIcon)
    assert not icon.isNull()


def test_title_builder_prefers_name_without_duplicate_type(
    preset_repository,
) -> None:
    from osminfo.openstreetmap.title_builder import OsmElementTitleBuilder

    builder = OsmElementTitleBuilder(
        locale_name="en",
        repository=preset_repository,
    )

    assert (
        builder.build(
            {
                "name": "Restaurant Roma",
                "amenity": "restaurant",
            },
            7,
        )
        == "Restaurant Roma"
    )


def test_title_builder_formats_name_with_type(preset_repository) -> None:
    from osminfo.openstreetmap.title_builder import OsmElementTitleBuilder

    builder = OsmElementTitleBuilder(
        locale_name="en",
        repository=preset_repository,
    )

    assert (
        builder.build(
            {
                "name": "Roma",
                "amenity": "restaurant",
            },
            7,
        )
        == "Roma · restaurant"
    )


def test_title_builder_prefers_primary_preset_type_over_secondary_tag(
    preset_repository,
) -> None:
    from osminfo.openstreetmap.title_builder import OsmElementTitleBuilder

    builder = OsmElementTitleBuilder(
        locale_name="en",
        repository=preset_repository,
    )

    assert (
        builder.build(
            {
                "name": "Lesbar",
                "amenity": "cafe",
                "internet_access": "wlan",
            },
            7,
        )
        == "Lesbar · cafe"
    )


def test_title_builder_prefers_short_address(preset_repository) -> None:
    from osminfo.openstreetmap.title_builder import OsmElementTitleBuilder

    builder = OsmElementTitleBuilder(
        locale_name="en",
        repository=preset_repository,
    )

    assert (
        builder.build(
            {
                "amenity": "hospital",
                "addr:street": "Main Street",
                "addr:housenumber": "10",
            },
            15,
        )
        == "hospital · Main Street, 10"
    )


def test_title_builder_uses_single_best_detail(preset_repository) -> None:
    from osminfo.openstreetmap.title_builder import OsmElementTitleBuilder

    builder = OsmElementTitleBuilder(
        locale_name="en",
        repository=preset_repository,
    )

    assert (
        builder.build(
            {
                "amenity": "restaurant",
                "cuisine": "italian;pizza",
                "operator": "Roma Group",
                "ref": "R-1",
            },
            23,
        )
        == "restaurant · italian cuisine"
    )


def test_title_builder_uses_ref_as_route_detail(preset_repository) -> None:
    from osminfo.openstreetmap.title_builder import OsmElementTitleBuilder

    builder = OsmElementTitleBuilder(
        locale_name="en",
        repository=preset_repository,
    )

    assert (
        builder.build(
            {
                "route": "bus",
                "ref": "M4",
                "operator": "City Transport",
            },
            42,
        )
        == "route · M4"
    )


def test_title_builder_falls_back_to_name_only_without_type() -> None:
    from osminfo.openstreetmap.title_builder import OsmElementTitleBuilder

    builder = OsmElementTitleBuilder(locale_name="en")

    assert (
        builder.build(
            {
                "name": "Cafe",
                "unknown": "value",
            },
            7,
        )
        == "Cafe"
    )


def test_title_builder_prefers_brand_over_type_and_address(
    preset_repository,
) -> None:
    from osminfo.openstreetmap.title_builder import OsmElementTitleBuilder

    builder = OsmElementTitleBuilder(
        locale_name="en",
        repository=preset_repository,
    )

    assert (
        builder.build(
            {
                "shop": "supermarket",
                "brand": "SPAR",
                "addr:street": "Main",
                "addr:housenumber": "1",
            },
            31,
        )
        == "SPAR · Main, 1"
    )


def test_title_builder_uses_localized_medium_name(preset_repository) -> None:
    from osminfo.openstreetmap.title_builder import OsmElementTitleBuilder

    builder = OsmElementTitleBuilder(
        locale_name="ru",
        repository=preset_repository,
    )

    assert (
        builder.build(
            {
                "amenity": "pharmacy",
                "brand:ru": "Аптека Озерки",
                "brand": "Ozerki",
            },
            32,
        )
        == "Аптека Озерки · pharmacy"
    )


def test_title_builder_does_not_treat_substring_as_type_match(
    preset_repository,
) -> None:
    from osminfo.openstreetmap.title_builder import OsmElementTitleBuilder

    builder = OsmElementTitleBuilder(
        locale_name="en",
        repository=preset_repository,
    )

    assert (
        builder.build(
            {
                "amenity": "bar",
                "name": "Barcelona",
            },
            33,
        )
        == "Barcelona · bar"
    )


def test_title_builder_filters_presets_by_geometry(tmp_path: Path) -> None:
    from osminfo.openstreetmap.preset_repository import PresetRepository
    from osminfo.openstreetmap.title_builder import OsmElementTitleBuilder

    presets_path = tmp_path / "presets.json"
    presets_path.write_text(
        json.dumps(
            {
                "amenity/parking_point": {
                    "name": "Parking Point",
                    "geometry": ["point"],
                    "tags": {"amenity": "parking"},
                },
                "amenity/parking_area": {
                    "name": "Parking Area",
                    "geometry": ["area"],
                    "tags": {"amenity": "parking"},
                    "matchScore": 0.5,
                },
            }
        ),
        encoding="utf-8",
    )

    repository = PresetRepository(presets_path=presets_path, locale_name="en")
    builder = OsmElementTitleBuilder(
        locale_name="en",
        repository=repository,
    )

    assert (
        builder.build(
            {"amenity": "parking"},
            34,
            geometry_type="point",
        )
        == "parking point"
    )
    assert (
        builder.build(
            {"amenity": "parking"},
            34,
            geometry_type="area",
        )
        == "parking area"
    )


def test_title_builder_uses_postal_code_for_boundary_detail() -> None:
    from osminfo.openstreetmap.title_builder import OsmElementTitleBuilder

    builder = OsmElementTitleBuilder(locale_name="en")

    assert (
        builder.build(
            {
                "boundary": "postal_code",
                "postal_code": "3110",
                "note": "3110 Munsingen",
                "type": "boundary",
            },
            35,
        )
        == "postal code · 3110"
    )


def test_title_builder_uses_country_for_level_two_boundary() -> None:
    from osminfo.openstreetmap.title_builder import OsmElementTitleBuilder

    builder = OsmElementTitleBuilder(locale_name="en")

    assert (
        builder.build(
            {
                "admin_level": "2",
                "boundary": "administrative",
                "name": "Switzerland",
                "type": "boundary",
            },
            36,
        )
        == "Switzerland · country"
    )


def test_title_builder_uses_administrative_boundary_label() -> None:
    from osminfo.openstreetmap.title_builder import OsmElementTitleBuilder

    builder = OsmElementTitleBuilder(locale_name="en")

    assert (
        builder.build(
            {
                "admin_level": "8",
                "boundary": "administrative",
                "name": "Oyace",
                "type": "boundary",
            },
            37,
        )
        == "Oyace · administrative boundary"
    )


def test_title_builder_uses_relation_boundary_preset_for_area_geometry() -> (
    None
):
    from osminfo.openstreetmap.title_builder import OsmElementTitleBuilder

    builder = OsmElementTitleBuilder(locale_name="en")

    assert (
        builder.build(
            {
                "admin_level": "4",
                "boundary": "administrative",
                "name": "Bern/Berne",
                "type": "boundary",
            },
            38,
            geometry_type="area",
        )
        == "Bern/Berne · administrative boundary"
    )


def test_results_renderer_creates_layers_only_for_results(monkeypatch) -> None:
    from qgis.core import QgsGeometry, QgsPointXY, QgsVectorLayer
    from qgis.utils import iface

    import osminfo.search.results_renderer as results_renderer_module
    from osminfo.openstreetmap.models import (
        OsmElement,
        OsmElementType,
        OsmResultGroup,
        OsmResultGroupType,
        OsmResultTree,
    )

    class FakeSignal:
        def connect(self, callback) -> None:
            self._callback = callback

        def disconnect(self, callback) -> None:
            del callback

        def emit(self, *args) -> None:
            callback = getattr(self, "_callback", None)
            if callback is not None:
                callback(*args)

    class FakeCrs:
        def authid(self) -> str:
            return "EPSG:4326"

        def postgisSrid(self) -> int:
            return 4326

    class FakeMapSettings:
        def destinationCrs(self) -> FakeCrs:
            return FakeCrs()

    class FakeCanvas:
        def __init__(self) -> None:
            self.scaleChanged = FakeSignal()
            self.layersChanged = FakeSignal()
            self.destinationCrsChanged = FakeSignal()
            self._layers = []
            self._map_units_per_pixel = 0.0001

        def scale(self) -> float:
            return 1000.0

        def mapUnitsPerPixel(self) -> float:
            return self._map_units_per_pixel

        def layers(self):
            return list(self._layers)

        def setLayers(self, layers) -> None:
            self._layers = list(layers)
            self.layersChanged.emit()

        def mapSettings(self) -> FakeMapSettings:
            return FakeMapSettings()

        def setExtent(self, bbox) -> None:
            self._bbox = bbox

        def refresh(self) -> None:
            return None

    class FakeIface:
        def __init__(self) -> None:
            self._canvas = FakeCanvas()

        def mapCanvas(self) -> FakeCanvas:
            return self._canvas

    fake_iface = FakeIface()
    monkeypatch.setattr(results_renderer_module, "iface", fake_iface)
    monkeypatch.setattr("qgis.utils.iface", fake_iface)

    point_element = OsmElement(
        osm_id=1,
        element_type=OsmElementType.NODE,
        title="Point",
        geometry=QgsGeometry.fromPointXY(QgsPointXY(30.0, 60.0)),
    )
    line_element = OsmElement(
        osm_id=2,
        element_type=OsmElementType.WAY,
        title="Line",
        geometry=QgsGeometry.fromPolylineXY(
            [
                QgsPointXY(30.0, 60.0),
                QgsPointXY(30.1, 60.1),
            ]
        ),
    )
    polygon_element = OsmElement(
        osm_id=3,
        element_type=OsmElementType.WAY,
        title="Polygon",
        geometry=QgsGeometry.fromPolygonXY(
            [
                [
                    QgsPointXY(30.0, 60.0),
                    QgsPointXY(30.2, 60.0),
                    QgsPointXY(30.2, 60.2),
                    QgsPointXY(30.0, 60.0),
                ]
            ]
        ),
    )

    renderer = results_renderer_module.OsmResultsRenderer()
    del iface
    assert len(renderer._layers) == 0
    assert len(fake_iface.mapCanvas().layers()) == 0

    renderer.set_result_tree(
        OsmResultTree(
            groups=(
                OsmResultGroup(
                    group_type=OsmResultGroupType.SEARCH,
                    title="Search results",
                    elements=(point_element, line_element, polygon_element),
                ),
            )
        )
    )
    renderer.set_active_elements((point_element, polygon_element))

    point_geometry_type = point_element.geometry_type()
    line_geometry_type = line_element.geometry_type()
    polygon_geometry_type = polygon_element.geometry_type()

    assert point_geometry_type is not None
    assert line_geometry_type is not None
    assert polygon_geometry_type is not None

    canvas_layers = fake_iface.mapCanvas().layers()
    assert len(renderer._layers) == 3
    assert len(canvas_layers) == 3
    assert canvas_layers[0] is renderer._layers[point_geometry_type]
    assert canvas_layers[1] is renderer._layers[line_geometry_type]
    assert canvas_layers[2] is renderer._layers[polygon_geometry_type]
    assert renderer._layers[point_geometry_type].featureCount() == 1
    assert renderer._layers[line_geometry_type].featureCount() == 1
    assert renderer._layers[polygon_geometry_type].featureCount() == 1

    renderer.clear()

    assert len(renderer._layers) == 0
    assert len(fake_iface.mapCanvas().layers()) == 0

    renderer.unload()

    base_layer = QgsVectorLayer("Point?crs=EPSG:4326", "Base", "memory")
    renderer = results_renderer_module.OsmResultsRenderer()
    renderer.set_result_tree(
        OsmResultTree(
            groups=(
                OsmResultGroup(
                    group_type=OsmResultGroupType.SEARCH,
                    title="Search results",
                    elements=(point_element,),
                ),
            )
        )
    )

    fake_iface.mapCanvas().setLayers([base_layer])

    canvas_layers = fake_iface.mapCanvas().layers()
    assert base_layer in canvas_layers
    assert len(canvas_layers) == 4
    assert canvas_layers[0] is renderer._layers[point_geometry_type]
    assert canvas_layers[1] is renderer._layers[line_geometry_type]
    assert canvas_layers[2] is renderer._layers[polygon_geometry_type]
    assert canvas_layers[3] is base_layer
    assert any(
        layer.customProperty("osminfo_result_layer", 0)
        for layer in canvas_layers
    )

    renderer.unload()


def test_results_renderer_updates_active_attribute_in_place(
    monkeypatch,
) -> None:
    from qgis.core import QgsGeometry, QgsPointXY

    import osminfo.search.results_renderer as results_renderer_module
    from osminfo.openstreetmap.models import (
        OsmElement,
        OsmElementType,
        OsmResultGroup,
        OsmResultGroupType,
        OsmResultTree,
    )

    class FakeSignal:
        def connect(self, callback) -> None:
            self._callback = callback

        def disconnect(self, callback) -> None:
            del callback

        def emit(self, *args) -> None:
            callback = getattr(self, "_callback", None)
            if callback is not None:
                callback(*args)

    class FakeCrs:
        def authid(self) -> str:
            return "EPSG:4326"

        def postgisSrid(self) -> int:
            return 4326

    class FakeMapSettings:
        def destinationCrs(self) -> FakeCrs:
            return FakeCrs()

    class FakeCanvas:
        def __init__(self) -> None:
            self.scaleChanged = FakeSignal()
            self.layersChanged = FakeSignal()
            self.destinationCrsChanged = FakeSignal()
            self._layers = []

        def scale(self) -> float:
            return 1000.0

        def layers(self):
            return list(self._layers)

        def setLayers(self, layers) -> None:
            self._layers = list(layers)
            self.layersChanged.emit()

        def mapSettings(self) -> FakeMapSettings:
            return FakeMapSettings()

        def setExtent(self, bbox) -> None:
            self._bbox = bbox

        def refresh(self) -> None:
            return None

    class FakeIface:
        def __init__(self) -> None:
            self._canvas = FakeCanvas()

        def mapCanvas(self) -> FakeCanvas:
            return self._canvas

    fake_iface = FakeIface()
    monkeypatch.setattr(results_renderer_module, "iface", fake_iface)

    point_element = OsmElement(
        osm_id=21,
        element_type=OsmElementType.NODE,
        title="Point",
        geometry=QgsGeometry.fromPointXY(QgsPointXY(30.0, 60.0)),
    )

    renderer = results_renderer_module.OsmResultsRenderer()
    renderer.set_result_tree(
        OsmResultTree(
            groups=(
                OsmResultGroup(
                    group_type=OsmResultGroupType.SEARCH,
                    title="Search results",
                    elements=(point_element,),
                ),
            )
        )
    )

    point_layer = renderer._layers[
        results_renderer_module.OsmGeometryType.POINT
    ]
    initial_feature = next(point_layer.getFeatures())
    initial_feature_id = initial_feature.id()

    assert initial_feature[results_renderer_module.FIELD_ACTIVE] == 0

    renderer.set_active_elements((point_element,))

    active_feature = next(point_layer.getFeatures())
    assert active_feature.id() == initial_feature_id
    assert active_feature[results_renderer_module.FIELD_ACTIVE] == 1

    renderer.set_active_elements(tuple())

    inactive_feature = next(point_layer.getFeatures())
    assert inactive_feature.id() == initial_feature_id
    assert inactive_feature[results_renderer_module.FIELD_ACTIVE] == 0

    renderer.unload()


def test_results_renderer_centers_single_point_bbox(monkeypatch) -> None:
    from qgis.core import QgsRectangle

    import osminfo.search.results_renderer as results_renderer_module

    class FakeSignal:
        def connect(self, callback) -> None:
            self._callback = callback

        def disconnect(self, callback) -> None:
            del callback

        def emit(self, *args) -> None:
            callback = getattr(self, "_callback", None)
            if callback is not None:
                callback(*args)

    class FakeCrs:
        def authid(self) -> str:
            return "EPSG:4326"

        def postgisSrid(self) -> int:
            return 4326

    class FakeMapSettings:
        def destinationCrs(self) -> FakeCrs:
            return FakeCrs()

    class FakeCanvas:
        def __init__(self) -> None:
            self.scaleChanged = FakeSignal()
            self.layersChanged = FakeSignal()
            self.destinationCrsChanged = FakeSignal()
            self._layers = []
            self._extent = QgsRectangle(0.0, 0.0, 10.0, 10.0)

        def layers(self):
            return list(self._layers)

        def setLayers(self, layers) -> None:
            self._layers = list(layers)
            self.layersChanged.emit()

        def mapSettings(self) -> FakeMapSettings:
            return FakeMapSettings()

        def extent(self) -> QgsRectangle:
            return QgsRectangle(self._extent)

        def setExtent(self, bbox) -> None:
            self._extent = QgsRectangle(bbox)

        def refresh(self) -> None:
            return None

    class FakeIface:
        def __init__(self) -> None:
            self._canvas = FakeCanvas()

        def mapCanvas(self) -> FakeCanvas:
            return self._canvas

    class FakeCoordinateTransform:
        def __init__(self, source_crs, destination_crs, project) -> None:
            del source_crs
            del destination_crs
            del project

        def transform(self, point):
            return point

    class FakeProject:
        @staticmethod
        def instance():
            return object()

    fake_iface = FakeIface()
    monkeypatch.setattr(results_renderer_module, "iface", fake_iface)
    monkeypatch.setattr(
        results_renderer_module,
        "QgsCoordinateTransform",
        FakeCoordinateTransform,
    )
    monkeypatch.setattr(results_renderer_module, "QgsProject", FakeProject)

    renderer = results_renderer_module.OsmResultsRenderer()
    renderer.zoom_to_bbox(QgsRectangle(30.0, 60.0, 30.0, 60.0))

    extent = fake_iface.mapCanvas().extent()
    center = extent.center()
    assert extent.width() == 10.0
    assert extent.height() == 10.0
    assert center.x() == 30.0
    assert center.y() == 60.0

    renderer.unload()


def test_results_renderer_keeps_collection_points_at_overview_scale(
    monkeypatch,
) -> None:
    from qgis.core import QgsGeometry, QgsPointXY

    import osminfo.search.results_renderer as results_renderer_module
    from osminfo.openstreetmap.models import (
        OsmElement,
        OsmElementType,
        OsmGeometryCollection,
        OsmResultGroup,
        OsmResultGroupType,
        OsmResultTree,
    )

    class FakeSignal:
        def connect(self, callback) -> None:
            self._callback = callback

        def disconnect(self, callback) -> None:
            del callback

        def emit(self, *args) -> None:
            callback = getattr(self, "_callback", None)
            if callback is not None:
                callback(*args)

    class FakeCrs:
        def authid(self) -> str:
            return "EPSG:4326"

        def postgisSrid(self) -> int:
            return 4326

    class FakeMapSettings:
        def destinationCrs(self) -> FakeCrs:
            return FakeCrs()

    class FakeCanvas:
        def __init__(self) -> None:
            self.scaleChanged = FakeSignal()
            self.layersChanged = FakeSignal()
            self.destinationCrsChanged = FakeSignal()
            self._layers = []
            self._map_units_per_pixel = 1.0

        def scale(self) -> float:
            return 1000.0

        def mapUnitsPerPixel(self) -> float:
            return self._map_units_per_pixel

        def layers(self):
            return list(self._layers)

        def setLayers(self, layers) -> None:
            self._layers = list(layers)
            self.layersChanged.emit()

        def mapSettings(self) -> FakeMapSettings:
            return FakeMapSettings()

        def setExtent(self, bbox) -> None:
            self._bbox = bbox

        def refresh(self) -> None:
            return None

    class FakeIface:
        def __init__(self) -> None:
            self._canvas = FakeCanvas()

        def mapCanvas(self) -> FakeCanvas:
            return self._canvas

    fake_iface = FakeIface()
    monkeypatch.setattr(results_renderer_module, "iface", fake_iface)

    collection_element = OsmElement(
        osm_id=10,
        element_type=OsmElementType.RELATION,
        title="Collection",
        geometry=OsmGeometryCollection(
            points=QgsGeometry.fromMultiPointXY([QgsPointXY(30.0, 60.0)]),
            lines=QgsGeometry.fromMultiPolylineXY(
                [[QgsPointXY(30.0, 60.0), QgsPointXY(30.1, 60.1)]]
            ),
        ),
        max_scale=100.0,
    )

    renderer = results_renderer_module.OsmResultsRenderer()
    renderer.set_result_tree(
        OsmResultTree(
            groups=(
                OsmResultGroup(
                    group_type=OsmResultGroupType.SEARCH,
                    title="Search results",
                    elements=(collection_element,),
                ),
            )
        )
    )

    assert (
        renderer._layers[
            results_renderer_module.OsmGeometryType.POINT
        ].featureCount()
        == 1
    )
    assert (
        renderer._layers[
            results_renderer_module.OsmGeometryType.LINESTRING
        ].featureCount()
        == 1
    )

    line_feature = next(
        renderer._layers[
            results_renderer_module.OsmGeometryType.LINESTRING
        ].getFeatures()
    )
    assert line_feature[results_renderer_module.FIELD_MAX_SCALE] is None

    renderer.unload()


def test_results_renderer_stores_max_scale_for_non_point_features(
    monkeypatch,
) -> None:
    from qgis.core import QgsGeometry, QgsPointXY

    import osminfo.search.results_renderer as results_renderer_module
    from osminfo.openstreetmap.models import (
        OsmElement,
        OsmElementType,
        OsmResultGroup,
        OsmResultGroupType,
        OsmResultTree,
    )

    class FakeSignal:
        def connect(self, callback) -> None:
            self._callback = callback

        def disconnect(self, callback) -> None:
            del callback

        def emit(self, *args) -> None:
            callback = getattr(self, "_callback", None)
            if callback is not None:
                callback(*args)

    class FakeCrs:
        def authid(self) -> str:
            return "EPSG:4326"

        def postgisSrid(self) -> int:
            return 4326

    class FakeMapSettings:
        def destinationCrs(self) -> FakeCrs:
            return FakeCrs()

    class FakeCanvas:
        def __init__(self) -> None:
            self.scaleChanged = FakeSignal()
            self.layersChanged = FakeSignal()
            self.destinationCrsChanged = FakeSignal()
            self._layers = []

        def scale(self) -> float:
            return 1000.0

        def layers(self):
            return list(self._layers)

        def setLayers(self, layers) -> None:
            self._layers = list(layers)
            self.layersChanged.emit()

        def mapSettings(self) -> FakeMapSettings:
            return FakeMapSettings()

        def setExtent(self, bbox) -> None:
            self._bbox = bbox

        def refresh(self) -> None:
            return None

    class FakeIface:
        def __init__(self) -> None:
            self._canvas = FakeCanvas()

        def mapCanvas(self) -> FakeCanvas:
            return self._canvas

    fake_iface = FakeIface()
    monkeypatch.setattr(results_renderer_module, "iface", fake_iface)

    polygon_element = OsmElement(
        osm_id=11,
        element_type=OsmElementType.WAY,
        title="Polygon",
        geometry=QgsGeometry.fromPolygonXY(
            [
                [
                    QgsPointXY(0.0, 0.0),
                    QgsPointXY(5.0, 0.0),
                    QgsPointXY(5.0, 5.0),
                    QgsPointXY(0.0, 0.0),
                ]
            ]
        ),
        max_scale=250.0,
    )

    renderer = results_renderer_module.OsmResultsRenderer()
    renderer.set_result_tree(
        OsmResultTree(
            groups=(
                OsmResultGroup(
                    group_type=OsmResultGroupType.SEARCH,
                    title="Search results",
                    elements=(polygon_element,),
                ),
            )
        )
    )

    assert (
        renderer._layers[
            results_renderer_module.OsmGeometryType.POLYGON
        ].featureCount()
        == 1
    )

    polygon_feature = next(
        renderer._layers[
            results_renderer_module.OsmGeometryType.POLYGON
        ].getFeatures()
    )
    assert polygon_feature[results_renderer_module.FIELD_MAX_SCALE] == 250.0

    renderer.unload()


def test_results_renderer_can_disable_centroid_rules(monkeypatch) -> None:
    from qgis.core import QgsGeometry, QgsPointXY

    import osminfo.search.results_renderer as results_renderer_module
    from osminfo.openstreetmap.models import (
        OsmElement,
        OsmElementType,
        OsmResultGroup,
        OsmResultGroupType,
        OsmResultTree,
    )

    class FakeSignal:
        def connect(self, callback) -> None:
            self._callback = callback

        def disconnect(self, callback) -> None:
            del callback

        def emit(self, *args) -> None:
            callback = getattr(self, "_callback", None)
            if callback is not None:
                callback(*args)

    class FakeCrs:
        def authid(self) -> str:
            return "EPSG:4326"

        def postgisSrid(self) -> int:
            return 4326

    class FakeMapSettings:
        def destinationCrs(self) -> FakeCrs:
            return FakeCrs()

    class FakeCanvas:
        def __init__(self) -> None:
            self.scaleChanged = FakeSignal()
            self.layersChanged = FakeSignal()
            self.destinationCrsChanged = FakeSignal()
            self._layers = []

        def scale(self) -> float:
            return 1000.0

        def layers(self):
            return list(self._layers)

        def setLayers(self, layers) -> None:
            self._layers = list(layers)
            self.layersChanged.emit()

        def mapSettings(self) -> FakeMapSettings:
            return FakeMapSettings()

        def setExtent(self, bbox) -> None:
            self._bbox = bbox

        def refresh(self) -> None:
            return None

    class FakeIface:
        def __init__(self) -> None:
            self._canvas = FakeCanvas()

        def mapCanvas(self) -> FakeCanvas:
            return self._canvas

    fake_iface = FakeIface()
    monkeypatch.setattr(results_renderer_module, "iface", fake_iface)

    polygon_element = OsmElement(
        osm_id=12,
        element_type=OsmElementType.WAY,
        title="Polygon",
        geometry=QgsGeometry.fromPolygonXY(
            [
                [
                    QgsPointXY(0.0, 0.0),
                    QgsPointXY(5.0, 0.0),
                    QgsPointXY(5.0, 5.0),
                    QgsPointXY(0.0, 0.0),
                ]
            ]
        ),
        max_scale=250.0,
    )

    renderer = results_renderer_module.OsmResultsRenderer()
    renderer.set_result_tree(
        OsmResultTree(
            groups=(
                OsmResultGroup(
                    group_type=OsmResultGroupType.SEARCH,
                    title="Search results",
                    elements=(polygon_element,),
                ),
            )
        )
    )

    polygon_layer = renderer._layers[
        results_renderer_module.OsmGeometryType.POLYGON
    ]
    assert len(polygon_layer.renderer().rootRule().children()) == 10

    renderer.set_centroid_rendering_enabled(False)

    assert len(polygon_layer.renderer().rootRule().children()) == 5

    renderer.unload()


def test_results_renderer_uses_mutually_exclusive_style_filters(
    monkeypatch,
) -> None:
    from qgis.core import QgsGeometry, QgsPointXY

    import osminfo.search.results_renderer as results_renderer_module
    from osminfo.openstreetmap.models import (
        OsmElement,
        OsmElementType,
        OsmResultGroup,
        OsmResultGroupType,
        OsmResultTree,
    )

    class FakeSignal:
        def connect(self, callback) -> None:
            self._callback = callback

        def disconnect(self, callback) -> None:
            del callback

        def emit(self, *args) -> None:
            callback = getattr(self, "_callback", None)
            if callback is not None:
                callback(*args)

    class FakeCrs:
        def authid(self) -> str:
            return "EPSG:4326"

        def postgisSrid(self) -> int:
            return 4326

    class FakeMapSettings:
        def destinationCrs(self) -> FakeCrs:
            return FakeCrs()

    class FakeCanvas:
        def __init__(self) -> None:
            self.scaleChanged = FakeSignal()
            self.layersChanged = FakeSignal()
            self.destinationCrsChanged = FakeSignal()
            self._layers = []

        def scale(self) -> float:
            return 1000.0

        def layers(self):
            return list(self._layers)

        def setLayers(self, layers) -> None:
            self._layers = list(layers)
            self.layersChanged.emit()

        def mapSettings(self) -> FakeMapSettings:
            return FakeMapSettings()

        def setExtent(self, bbox) -> None:
            self._bbox = bbox

        def refresh(self) -> None:
            return None

    class FakeIface:
        def __init__(self) -> None:
            self._canvas = FakeCanvas()

        def mapCanvas(self) -> FakeCanvas:
            return self._canvas

    fake_iface = FakeIface()
    monkeypatch.setattr(results_renderer_module, "iface", fake_iface)

    polygon_element = OsmElement(
        osm_id=13,
        element_type=OsmElementType.RELATION,
        title="Polygon",
        geometry=QgsGeometry.fromPolygonXY(
            [
                [
                    QgsPointXY(0.0, 0.0),
                    QgsPointXY(5.0, 0.0),
                    QgsPointXY(5.0, 5.0),
                    QgsPointXY(0.0, 0.0),
                ]
            ]
        ),
        max_scale=250.0,
        is_incomplete=True,
    )

    renderer = results_renderer_module.OsmResultsRenderer()
    renderer.set_result_tree(
        OsmResultTree(
            groups=(
                OsmResultGroup(
                    group_type=OsmResultGroupType.SEARCH,
                    title="Search results",
                    elements=(polygon_element,),
                ),
            )
        )
    )

    polygon_layer = renderer._layers[
        results_renderer_module.OsmGeometryType.POLYGON
    ]
    filters = [
        rule.filterExpression()
        for rule in polygon_layer.renderer().rootRule().children()
    ]
    assert any(
        '"relation_related" = 1 AND "is_tainted" = 1' in filter_text
        for filter_text in filters
    )
    assert any(
        '"relation_related" = 0 AND "is_tainted" = 0' in filter_text
        for filter_text in filters
    )

    renderer.unload()


def test_results_renderer_adds_larger_polygons_first(monkeypatch) -> None:
    from qgis.core import QgsGeometry, QgsPointXY

    import osminfo.search.results_renderer as results_renderer_module
    from osminfo.openstreetmap.models import (
        OsmElement,
        OsmElementType,
        OsmResultGroup,
        OsmResultGroupType,
        OsmResultTree,
    )

    class FakeSignal:
        def connect(self, callback) -> None:
            self._callback = callback

        def disconnect(self, callback) -> None:
            del callback

        def emit(self, *args) -> None:
            callback = getattr(self, "_callback", None)
            if callback is not None:
                callback(*args)

    class FakeCrs:
        def authid(self) -> str:
            return "EPSG:4326"

        def postgisSrid(self) -> int:
            return 4326

    class FakeMapSettings:
        def destinationCrs(self) -> FakeCrs:
            return FakeCrs()

    class FakeCanvas:
        def __init__(self) -> None:
            self.scaleChanged = FakeSignal()
            self.layersChanged = FakeSignal()
            self.destinationCrsChanged = FakeSignal()
            self._layers = []

        def scale(self) -> float:
            return 1000.0

        def layers(self):
            return list(self._layers)

        def setLayers(self, layers) -> None:
            self._layers = list(layers)
            self.layersChanged.emit()

        def mapSettings(self) -> FakeMapSettings:
            return FakeMapSettings()

        def setExtent(self, bbox) -> None:
            self._bbox = bbox

        def refresh(self) -> None:
            return None

    class FakeIface:
        def __init__(self) -> None:
            self._canvas = FakeCanvas()

        def mapCanvas(self) -> FakeCanvas:
            return self._canvas

    fake_iface = FakeIface()
    monkeypatch.setattr(results_renderer_module, "iface", fake_iface)

    small_polygon = OsmElement(
        osm_id=14,
        element_type=OsmElementType.WAY,
        title="Small",
        geometry=QgsGeometry.fromPolygonXY(
            [
                [
                    QgsPointXY(0.0, 0.0),
                    QgsPointXY(1.0, 0.0),
                    QgsPointXY(1.0, 1.0),
                    QgsPointXY(0.0, 0.0),
                ]
            ]
        ),
    )
    large_polygon = OsmElement(
        osm_id=15,
        element_type=OsmElementType.WAY,
        title="Large",
        geometry=QgsGeometry.fromPolygonXY(
            [
                [
                    QgsPointXY(0.0, 0.0),
                    QgsPointXY(3.0, 0.0),
                    QgsPointXY(3.0, 3.0),
                    QgsPointXY(0.0, 0.0),
                ]
            ]
        ),
    )

    renderer = results_renderer_module.OsmResultsRenderer()
    renderer.set_result_tree(
        OsmResultTree(
            groups=(
                OsmResultGroup(
                    group_type=OsmResultGroupType.SEARCH,
                    title="Search results",
                    elements=(small_polygon, large_polygon),
                ),
            )
        )
    )

    polygon_layer = renderer._layers[
        results_renderer_module.OsmGeometryType.POLYGON
    ]
    feature_areas = [
        feature.geometry().area() for feature in polygon_layer.getFeatures()
    ]
    assert feature_areas == sorted(feature_areas, reverse=True)

    renderer.unload()
