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


def test_collect_geometry_subset_for_way_with_inline_geometry() -> None:
    from osminfo.openstreetmap.raw_elements_subset import (
        RawElementsSubsetCollector,
    )

    raw_way = {
        "type": "way",
        "id": 10,
        "geometry": [
            {"lat": 60.0, "lon": 30.0},
            {"lat": 60.001, "lon": 30.001},
        ],
        "tags": {"highway": "service"},
    }
    raw_node = {"type": "node", "id": 1, "lat": 60.0, "lon": 30.0}

    subset = RawElementsSubsetCollector(
        (raw_way, raw_node)
    ).collect_geometry_subset(
        (raw_way,),
    )

    assert subset == (raw_way,)


def test_collect_geometry_subset_for_way_with_node_dependencies() -> None:
    from osminfo.openstreetmap.raw_elements_subset import (
        RawElementsSubsetCollector,
    )

    raw_way = {
        "type": "way",
        "id": 20,
        "nodes": [1, 2, 3],
        "tags": {"highway": "service"},
    }
    raw_node_1 = {"type": "node", "id": 1, "lat": 60.0, "lon": 30.0}
    raw_node_2 = {"type": "node", "id": 2, "lat": 60.1, "lon": 30.1}
    raw_node_3 = {"type": "node", "id": 3, "lat": 60.2, "lon": 30.2}

    subset = RawElementsSubsetCollector(
        (raw_way, raw_node_1, raw_node_2, raw_node_3)
    ).collect_geometry_subset((raw_way,))

    assert subset == (raw_way, raw_node_1, raw_node_2, raw_node_3)


def test_collect_geometry_subset_for_relation_collects_nested_dependencies() -> (
    None
):
    from osminfo.openstreetmap.raw_elements_subset import (
        RawElementsSubsetCollector,
    )

    raw_relation = {
        "type": "relation",
        "id": 30,
        "members": [
            {"type": "way", "ref": 20, "role": "outer"},
            {"type": "node", "ref": 5, "role": "label"},
        ],
        "tags": {"type": "multipolygon"},
    }
    raw_way = {
        "type": "way",
        "id": 20,
        "nodes": [1, 2, 3, 1],
        "tags": {"building": "yes"},
    }
    raw_node_1 = {"type": "node", "id": 1, "lat": 60.0, "lon": 30.0}
    raw_node_2 = {"type": "node", "id": 2, "lat": 60.0, "lon": 30.1}
    raw_node_3 = {"type": "node", "id": 3, "lat": 60.1, "lon": 30.0}
    raw_node_5 = {"type": "node", "id": 5, "lat": 60.05, "lon": 30.05}

    subset = RawElementsSubsetCollector(
        (
            raw_relation,
            raw_way,
            raw_node_1,
            raw_node_2,
            raw_node_3,
            raw_node_5,
        )
    ).collect_geometry_subset((raw_relation,))

    assert subset == (
        raw_relation,
        raw_way,
        raw_node_1,
        raw_node_2,
        raw_node_3,
        raw_node_5,
    )


def test_raw_elements_subset_collector_exposes_raw_element_by_key() -> None:
    from osminfo.openstreetmap.raw_elements_subset import (
        RawElementsSubsetCollector,
    )

    raw_way = {
        "type": "way",
        "id": 20,
        "nodes": [1, 2, 3],
        "tags": {"highway": "service"},
    }
    raw_node = {"type": "node", "id": 1, "lat": 60.0, "lon": 30.0}

    collector = RawElementsSubsetCollector((raw_way, raw_node))

    assert collector.all_raw_elements() == (raw_way, raw_node)
    assert collector.is_empty() is False
    assert collector.raw_element_for_key(("way", 20)) is raw_way
    assert collector.raw_element_for_key(("node", 1)) is raw_node
    assert collector.raw_element_for_key(("node", 999)) is None
