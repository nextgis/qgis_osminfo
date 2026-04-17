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

import importlib
import re

import pytest


@pytest.fixture
def query_postprocessor_module(configure_wizard_imports):
    importlib.invalidate_caches()
    sys_modules = importlib.import_module("sys").modules
    sys_modules.pop("osminfo.overpass.query_builder.query_context", None)
    sys_modules.pop("osminfo.overpass.query_builder.query_postprocessor", None)
    return importlib.import_module(
        "osminfo.overpass.query_builder.query_postprocessor"
    )


def test_extract_geocoding_data_deduplicates_and_preserves_order(
    query_postprocessor_module,
) -> None:
    geocoding_data = (
        query_postprocessor_module.QueryPostprocessor.extract_geocoding_data(
            [
                "{{geocodeArea:Berlin}} {{geocodeCoords:Berlin}}",
                "{{geocodeId:Berlin Cathedral}} {{geocodeArea:Berlin}}",
                "{{geocodeBbox:Paris}} {{geocodeCoords:Berlin}}",
            ]
        )
    )

    assert geocoding_data.id_queries == ("Berlin Cathedral",)
    assert geocoding_data.area_queries == ("Berlin",)
    assert geocoding_data.bbox_queries == ("Paris",)
    assert geocoding_data.coordinate_queries == ("Berlin",)


def test_process_replaces_bbox_center_radius_and_geocoding(
    query_postprocessor_module,
) -> None:
    query_context_module = importlib.import_module(
        "osminfo.overpass.query_builder.query_context"
    )
    context = query_context_module.QueryContext(
        bbox=query_context_module.QgsRectangle(20.0, 10.0, 40.0, 30.0),
        center=query_context_module.QgsPointXY(30.0, 20.0),
        geocode_ids={"Berlin Cathedral": "way(id:123)"},
        geocode_areas={"Berlin": "area(id:3600062422)"},
        geocode_bboxes={"Paris": "1,2,3,4"},
        geocode_coords={"Berlin": "52.5,13.4"},
    )

    processed_queries = query_postprocessor_module.QueryPostprocessor().process(
        [
            "{{radius=250}}\nnode(around:{{radius}},{{center}});\nout;",
            "way({{bbox}});{{geocodeId:Berlin Cathedral}};",
            "rel({{geocodeArea:Berlin}});node({{geocodeBbox:Paris}});",
            "{{radius=250}}\nnode(around:{{radius}},{{geocodeCoords:Berlin}});",
            "{{tag=shop}}\n{{tag=amenity}}\n{{value=drinking_water}}"
            '\nnode[{{tag}}="{{value}}"]({{bbox}});',
        ],
        context,
    )

    assert processed_queries[0] == "node(around:250,20,30);\nout;"
    assert processed_queries[1] == "way(10,20,30,40);way(id:123);"
    assert processed_queries[2] == "rel(area(id:3600062422));node(1,2,3,4);"
    assert processed_queries[3] == "node(around:250,52.5,13.4);"
    assert (
        processed_queries[4] == 'node[amenity="drinking_water"](10,20,30,40);'
    )


def test_process_resolves_relative_date_placeholder(
    query_postprocessor_module,
) -> None:
    query_context_module = importlib.import_module(
        "osminfo.overpass.query_builder.query_context"
    )
    context = query_context_module.QueryContext(
        bbox=query_context_module.QgsRectangle(0.0, 0.0, 1.0, 1.0),
        center=query_context_module.QgsPointXY(0.5, 0.5),
    )

    processed_query = query_postprocessor_module.QueryPostprocessor().process(
        ['node(newer:"{{date:1 day}}");'],
        context,
    )[0]

    match = re.search(
        r'node\(newer:"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z"\);',
        processed_query,
    )
    assert match is not None


@pytest.mark.parametrize(
    "query",
    [
        "node(around:{{radius}},{{center}});",
        'node[{{tag}}="drinking_water"]({{bbox}});',
    ],
)
def test_process_raises_for_uninitialized_shortcut_placeholder(
    query_postprocessor_module,
    query: str,
) -> None:
    query_context_module = importlib.import_module(
        "osminfo.overpass.query_builder.query_context"
    )
    context = query_context_module.QueryContext(
        bbox=query_context_module.QgsRectangle(0.0, 0.0, 1.0, 1.0),
        center=query_context_module.QgsPointXY(0.5, 0.5),
    )

    with pytest.raises(query_postprocessor_module.OsmInfoQueryBuilderError):
        query_postprocessor_module.QueryPostprocessor().process(
            [query],
            context,
        )
