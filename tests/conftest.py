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
import json
import sys
import types
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict

import pytest

WORKSPACE_ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = WORKSPACE_ROOT / "src"


@dataclass(frozen=True)
class WizardModules:
    compiler: Any
    exceptions: Any
    free_form: Any
    models: Any
    normalizer: Any
    parser: Any
    repair: Any
    renderer: Any
    semantic: Any


def _install_package_stub(module_name: str, path: Path) -> None:
    module = types.ModuleType(module_name)
    module.__path__ = [str(path)]
    sys.modules[module_name] = module


@pytest.fixture(scope="session", autouse=True)
def configure_wizard_imports() -> None:
    source_root = str(SOURCE_ROOT)
    if source_root not in sys.path:
        sys.path.insert(0, source_root)

    _install_package_stub("osminfo", SOURCE_ROOT / "osminfo")
    _install_package_stub("osminfo.core", SOURCE_ROOT / "osminfo" / "core")
    _install_package_stub(
        "osminfo.overpass",
        SOURCE_ROOT / "osminfo" / "overpass",
    )
    _install_package_stub(
        "osminfo.overpass.query_builder",
        SOURCE_ROOT / "osminfo" / "overpass" / "query_builder",
    )
    _install_package_stub(
        "osminfo.search",
        SOURCE_ROOT / "osminfo" / "search",
    )


@pytest.fixture(scope="session")
def wizard_modules() -> WizardModules:
    return WizardModules(
        compiler=importlib.import_module(
            "osminfo.overpass.query_builder.wizard.compiler"
        ),
        exceptions=importlib.import_module("osminfo.core.exceptions"),
        free_form=importlib.import_module(
            "osminfo.overpass.query_builder.wizard.free_form"
        ),
        models=importlib.import_module(
            "osminfo.overpass.query_builder.wizard.models"
        ),
        normalizer=importlib.import_module(
            "osminfo.overpass.query_builder.wizard.normalizer"
        ),
        parser=importlib.import_module(
            "osminfo.overpass.query_builder.wizard.parser"
        ),
        repair=importlib.import_module(
            "osminfo.overpass.query_builder.wizard.repair"
        ),
        renderer=importlib.import_module(
            "osminfo.overpass.query_builder.wizard.renderer"
        ),
        semantic=importlib.import_module(
            "osminfo.overpass.query_builder.wizard.semantic"
        ),
    )


@pytest.fixture(scope="session")
def compiler_class(wizard_modules: WizardModules):
    return wizard_modules.compiler.WizardQueryCompiler


@pytest.fixture
def compiler(compiler_class):
    return compiler_class()


@pytest.fixture
def parser(wizard_modules: WizardModules):
    return wizard_modules.parser.WizardSyntaxParser()


@pytest.fixture
def normalizer(wizard_modules: WizardModules):
    return wizard_modules.normalizer.WizardAstNormalizer()


@pytest.fixture
def renderer(wizard_modules: WizardModules):
    return wizard_modules.renderer.OverpassWizardRenderer()


@pytest.fixture
def preset_payload() -> Dict[str, Dict[str, Any]]:
    return {
        "amenity/hospital": {
            "name": "Hospital",
            "terms": [],
            "geometry": ["point", "area"],
            "tags": {"amenity": "hospital"},
        },
        "amenity/restaurant": {
            "name": "Restaurant",
            "terms": ["shared", "food", "shared"],
            "geometry": ["point", "area"],
            "tags": {"amenity": "restaurant"},
        },
        "amenity/cafe": {
            "name": "Cafe",
            "terms": ["coffee"],
            "geometry": ["point", "area"],
            "tags": {"amenity": "cafe"},
        },
        "amenity/shelter": {
            "name": "Shelter",
            "terms": [],
            "geometry": ["point"],
            "tags": {"amenity": "shelter"},
        },
        "highway": {
            "name": "Highway",
            "terms": [],
            "geometry": ["line"],
            "tags": {"highway": "*"},
        },
        "shop/cafe": {
            "name": "Cafe",
            "terms": ["other", "shared"],
            "geometry": ["point"],
            "tags": {"shop": "cafe"},
        },
        "shop/kiosk": {
            "name": "Kiosk",
            "terms": ["booth"],
            "geometry": ["point"],
            "tags": {"shop": "kiosk"},
        },
        "internet_access/wlan": {
            "name": "Wi-Fi Hotspot",
            "terms": ["wifi", "wlan"],
            "geometry": ["point", "area"],
            "tags": {"internet_access": "wlan"},
            "matchScore": 0.25,
        },
        "amenity/hidden": {
            "name": "Hidden",
            "terms": ["secret"],
            "geometry": ["point"],
            "tags": {"amenity": "hidden"},
            "searchable": False,
        },
    }


@pytest.fixture
def preset_repository(
    tmp_path: Path, wizard_modules: WizardModules, preset_payload
):
    presets_path = tmp_path / "presets.json"
    presets_path.write_text(json.dumps(preset_payload), encoding="utf-8")

    repository_class = wizard_modules.free_form.PresetRepository
    repository_class._cache = {}
    repository = repository_class(presets_path, locale_name="en")
    yield repository
    repository_class._cache = {}


@pytest.fixture
def preset_resolver(wizard_modules: WizardModules, preset_repository):
    return wizard_modules.free_form.PresetFreeFormResolver(preset_repository)


@pytest.fixture
def semantic_resolver(wizard_modules: WizardModules, preset_resolver):
    return wizard_modules.semantic.WizardSemanticResolver(preset_resolver)


@pytest.fixture
def search_repairer(wizard_modules: WizardModules, preset_resolver):
    return wizard_modules.repair.WizardSearchRepairer(preset_resolver)
