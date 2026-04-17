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
from dataclasses import dataclass
from pathlib import Path

import pytest

SOURCE_ROOT = Path(__file__).resolve().parents[1] / "src"


@dataclass
class SettingsStub:
    is_timeout_enabled: bool = False
    timeout: int = 60
    is_max_size_enabled: bool = False
    max_size_megabytes: int = 512


@pytest.fixture
def query_header_module(configure_wizard_imports, monkeypatch):
    settings_package = types.ModuleType("osminfo.settings")
    settings_package.__path__ = [str(SOURCE_ROOT / "osminfo" / "settings")]

    settings_module = types.ModuleType("osminfo.settings.osm_info_settings")

    class OsmInfoSettings:
        pass

    settings_module.OsmInfoSettings = OsmInfoSettings  # pyright: ignore[reportAttributeAccessIssue]
    settings_package.osm_info_settings = settings_module  # pyright: ignore[reportAttributeAccessIssue]

    monkeypatch.setitem(sys.modules, "osminfo.settings", settings_package)
    monkeypatch.setitem(
        sys.modules,
        "osminfo.settings.osm_info_settings",
        settings_module,
    )
    sys.modules.pop("osminfo.overpass.query_builder.query_header", None)

    return importlib.import_module(
        "osminfo.overpass.query_builder.query_header"
    )


def test_build_returns_default_header_without_settings(
    query_header_module,
) -> None:
    builder = query_header_module.QueryHeaderBuilder()

    assert builder.build() == "[out:json];"


def test_build_appends_preserved_options_and_enabled_limits(
    query_header_module,
) -> None:
    builder = query_header_module.QueryHeaderBuilder(
        SettingsStub(
            is_timeout_enabled=True,
            timeout=90,
            is_max_size_enabled=True,
            max_size_megabytes=256,
        )
    )

    assert builder.build(
        out_option="[out:xml]",
        preserved_options=["[bbox:1,2,3,4]", '[date:"2024-01-01T00:00:00Z"]'],
    ) == (
        "[out:xml][bbox:1,2,3,4]"
        '[date:"2024-01-01T00:00:00Z"]'
        "[timeout:90][maxsize:256Mi];"
    )


@pytest.mark.parametrize("max_size_megabytes", [0, -1])
def test_build_skips_non_positive_max_size(
    query_header_module,
    max_size_megabytes: int,
) -> None:
    builder = query_header_module.QueryHeaderBuilder(
        SettingsStub(
            is_max_size_enabled=True,
            max_size_megabytes=max_size_megabytes,
        )
    )

    assert builder.build() == "[out:json];"


def test_apply_replaces_existing_timeout_and_maxsize(
    query_header_module,
) -> None:
    builder = query_header_module.QueryHeaderBuilder(
        SettingsStub(
            is_timeout_enabled=True,
            timeout=120,
            is_max_size_enabled=True,
            max_size_megabytes=512,
        )
    )

    query = (
        "/* keep comment */\n"
        "[out:xml][anytag:1,2,3,4][timeout:25][maxsize:64Mi];\n"
        "node[amenity=restaurant](1,2,3,4);\n"
        "out;"
    )

    assert builder.apply(query) == (
        "/* keep comment */\n"
        "[out:xml][anytag:1,2,3,4][timeout:120][maxsize:512Mi];\n"
        "node[amenity=restaurant](1,2,3,4);\n"
        "out;"
    )


def test_apply_inserts_header_for_query_without_header(
    query_header_module,
) -> None:
    builder = query_header_module.QueryHeaderBuilder(
        SettingsStub(
            is_timeout_enabled=True,
            timeout=45,
        )
    )

    assert (
        builder.apply(
            "node(1,2,3,4);out;",
            default_out_option="[out:csv]",
        )
        == "[out:csv][timeout:45];\nnode(1,2,3,4);out;"
    )


def test_apply_returns_only_header_for_empty_query(
    query_header_module,
) -> None:
    builder = query_header_module.QueryHeaderBuilder(
        SettingsStub(
            is_timeout_enabled=True,
            timeout=30,
            is_max_size_enabled=True,
            max_size_megabytes=128,
        )
    )

    assert builder.apply("") == "[out:json][timeout:30][maxsize:128Mi];"
