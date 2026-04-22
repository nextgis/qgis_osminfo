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

import gc
import importlib
import json
import os
import shutil
import sys
import tempfile
import types
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Generator, Optional
from unittest.mock import MagicMock, Mock

import pytest
import qgis.utils
from qgis.core import (
    QgsApplication,
    QgsLayerTreeModel,
    QgsProject,
    QgsSettings,
)
from qgis.gui import QgisInterface, QgsLayerTreeView, QgsMapCanvas
from qgis.PyQt.QtCore import QSize, Qt
from qgis.PyQt.QtWidgets import QMainWindow

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


@dataclass(frozen=True)
class ApplicationInfo:
    application: QgsApplication
    qgis_custom_config_path: Path
    qgis_auth_db_path: Path


APPLICATION_INFO: Optional[ApplicationInfo] = None


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


def start_qgis() -> QgsApplication:
    global APPLICATION_INFO

    if APPLICATION_INFO is not None:
        return APPLICATION_INFO.application

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

    qgis_custom_config_path = Path(
        tempfile.mkdtemp(prefix="TestOSMInfo-config-")
    )
    qgis_auth_db_path = Path(tempfile.mkdtemp(prefix="TestOSMInfo-authdb-"))
    os.environ["QGIS_CUSTOM_CONFIG_PATH"] = str(qgis_custom_config_path)
    os.environ["QGIS_AUTH_DB_DIR_PATH"] = str(qgis_auth_db_path)

    QgsApplication.setAttribute(
        Qt.ApplicationAttribute.AA_ShareOpenGLContexts,
        True,
    )
    QgsApplication.setOrganizationName("NextGIS_Test")
    QgsApplication.setOrganizationDomain("TestOSMInfo.com")
    QgsApplication.setApplicationName("TestOSMInfo")
    QgsSettings().clear()

    application = QgsApplication(list(map(os.fsencode, sys.argv)), True)
    application.initQgis()
    init_interface()
    APPLICATION_INFO = ApplicationInfo(
        application=application,
        qgis_custom_config_path=qgis_custom_config_path,
        qgis_auth_db_path=qgis_auth_db_path,
    )
    return application


def stop_qgis() -> None:
    global APPLICATION_INFO

    if APPLICATION_INFO is None:
        return

    QgsSettings().clear()
    for _ in range(3):
        gc.collect()
        QgsApplication.processEvents()

    APPLICATION_INFO.application.exitQgis()
    shutil.rmtree(APPLICATION_INFO.qgis_custom_config_path, ignore_errors=True)
    shutil.rmtree(APPLICATION_INFO.qgis_auth_db_path, ignore_errors=True)
    APPLICATION_INFO = None


@pytest.fixture(scope="session")
def qgis_app() -> Generator[QgsApplication, None, None]:
    application = start_qgis()
    try:
        yield application
    finally:
        stop_qgis()


def init_interface() -> QgisInterface:
    iface = getattr(qgis.utils, "iface", None)
    if iface is None:
        iface = Mock(spec=QgisInterface)
        qgis.utils.iface = iface

    assert isinstance(iface, Mock)

    main_window = iface.mainWindow.return_value
    if not isinstance(main_window, QMainWindow):
        main_window = QMainWindow()
        iface.mainWindow.return_value = main_window

    map_canvas = iface.mapCanvas.return_value
    if not isinstance(map_canvas, QgsMapCanvas):
        map_canvas = QgsMapCanvas(main_window)
        map_canvas.resize(QSize(400, 400))
        iface.mapCanvas.return_value = map_canvas

    layer_tree_view = iface.layerTreeView.return_value
    if not isinstance(layer_tree_view, QgsLayerTreeView):
        layer_tree_view = QgsLayerTreeView(main_window)
        iface.layerTreeView.return_value = layer_tree_view

    layer_tree_model = QgsLayerTreeModel(
        QgsProject.instance().layerTreeRoot(),
        layer_tree_view,
    )
    layer_tree_view.setModel(layer_tree_model)

    user_profile_manager = iface.userProfileManager.return_value
    if not isinstance(user_profile_manager, MagicMock):
        user_profile = MagicMock()
        user_profile.folder.return_value = tempfile.mkdtemp(
            prefix="TestOSMInfo-profile-"
        )
        user_profile_manager = MagicMock()
        user_profile_manager.userProfile.return_value = user_profile
        iface.userProfileManager.return_value = user_profile_manager

    return iface


@pytest.fixture
def qgis_iface(qgis_app) -> QgisInterface:
    del qgis_app

    iface = init_interface()
    QgsProject.instance().removeAllMapLayers()
    iface.mapCanvas().setLayers([])
    iface.mapCanvas().resize(QSize(400, 400))
    return iface


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
