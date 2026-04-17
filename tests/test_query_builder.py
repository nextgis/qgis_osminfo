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
import sys
import types
from pathlib import Path

import pytest

SOURCE_ROOT = Path(__file__).resolve().parents[1] / "src"


class SettingsStub:
    fetch_nearby = True
    fetch_enclosing = True
    distance = 25
    is_timeout_enabled = False
    timeout = 60
    is_max_size_enabled = False
    max_size_megabytes = 512


@pytest.fixture
def query_builder_module(configure_wizard_imports, monkeypatch):
    settings_package = types.ModuleType("osminfo.settings")
    settings_package.__path__ = [str(SOURCE_ROOT / "osminfo" / "settings")]

    settings_module = types.ModuleType("osminfo.settings.osm_info_settings")
    settings_module.OsmInfoSettings = SettingsStub  # pyright: ignore[reportAttributeAccessIssue]
    settings_package.osm_info_settings = settings_module  # pyright: ignore[reportAttributeAccessIssue]

    monkeypatch.setitem(sys.modules, "osminfo.settings", settings_package)
    monkeypatch.setitem(
        sys.modules,
        "osminfo.settings.osm_info_settings",
        settings_module,
    )
    sys.modules.pop(
        "osminfo.overpass.query_builder.coordinates_query_strategy",
        None,
    )
    sys.modules.pop("osminfo.overpass.query_builder.query_builder", None)

    return importlib.import_module(
        "osminfo.overpass.query_builder.query_builder"
    )


def test_build_for_coords_accepts_qgs_point_xy(query_builder_module) -> None:
    point = query_builder_module.QgsPointXY(37.617635, 55.755814)
    builder = query_builder_module.QueryBuilder(SettingsStub())

    queries = builder.build_for_coords(point)

    assert builder.last_strategy_name == "coords"
    assert queries == [
        "[out:json];\n(\n"
        "    node(around:25,55.755814,37.617635);\n"
        "    way(around:25,55.755814,37.617635);\n"
        "    relation(around:25,55.755814,37.617635);\n"
        ");\nout tags geom;",
        "[out:json];\nis_in(55.755814,37.617635)->.a;\n"
        "way(pivot.a)->.b;\n.b out tags geom;\n.b <;\nout geom;\n"
        "relation(pivot.a);\nout geom;",
    ]


def test_build_for_string_parses_coordinates_to_qgs_point_xy(
    query_builder_module,
) -> None:
    builder = query_builder_module.QueryBuilder(SettingsStub())

    queries = builder.build_for_string(" 37.617635 , 55.755814 ")

    assert builder.last_strategy_name == "coords"
    assert len(queries) == 2
    assert "55.755814,37.617635" in queries[0]


def test_build_for_string_rejects_out_of_range_coordinates(
    query_builder_module,
) -> None:
    builder = query_builder_module.QueryBuilder(SettingsStub())

    with pytest.raises(
        query_builder_module.OsmInfoQueryBuilderError,
        match=r"181, 55 are wrong coords!",
    ):
        builder.build_for_string("181, 55")


def test_repair_search_returns_wizard_typo_suggestion(
    query_builder_module,
) -> None:
    builder = query_builder_module.QueryBuilder(SettingsStub())

    repaired_search = builder.repair_search("restarant in Berlin")

    assert repaired_search == "Restaurant in Berlin"
