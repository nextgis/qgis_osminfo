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
from typing import Any, Dict, Optional, cast

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

    qgis_module = types.ModuleType("qgis")
    qgis_core_module = types.ModuleType("qgis.core")
    qgis_gui_module = types.ModuleType("qgis.gui")
    qgis_pyqt_module = types.ModuleType("qgis.PyQt")
    qgis_pyqt_qtcore_module = types.ModuleType("qgis.PyQt.QtCore")
    qgis_pyqt_qtgui_module = types.ModuleType("qgis.PyQt.QtGui")
    qgis_pyqt_qtwidgets_module = types.ModuleType("qgis.PyQt.QtWidgets")

    class QgsApplication:
        @staticmethod
        def translate(context: str, message: str) -> str:
            return message

    class QgsSettings:
        def value(
            self,
            key: str,
            defaultValue=None,
            value_type=None,
            **kwargs: Any,
        ):
            if "type" in kwargs:
                kwargs["type"]

            if key == "locale/overrideFlag":
                return False

            if key == "locale/userLocale":
                return "en_US"

            return defaultValue

        def setValue(self, key: str, value: Any) -> None:
            setattr(self, key.replace("/", "_"), value)

    class QSettings(QgsSettings):
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            super().__init__()

        def allKeys(self):
            return []

    class QgsPointXY:
        def __init__(self, x: Any = 0.0, y: Optional[float] = None) -> None:
            if y is None and hasattr(x, "x") and hasattr(x, "y"):
                self._x = float(x.x())
                self._y = float(x.y())
                return

            self._x = float(x)
            self._y = float(0.0 if y is None else y)

        def x(self) -> float:
            return self._x

        def y(self) -> float:
            return self._y

    class QgsRectangle:
        def __init__(
            self,
            x_minimum: Any = 0.0,
            y_minimum: float = 0.0,
            x_maximum: float = 0.0,
            y_maximum: float = 0.0,
        ) -> None:
            if isinstance(x_minimum, QgsRectangle):
                self._xmin = x_minimum.xMinimum()
                self._ymin = x_minimum.yMinimum()
                self._xmax = x_minimum.xMaximum()
                self._ymax = x_minimum.yMaximum()
                return

            self._xmin = float(x_minimum)
            self._ymin = float(y_minimum)
            self._xmax = float(x_maximum)
            self._ymax = float(y_maximum)

        def xMinimum(self) -> float:
            return self._xmin

        def yMinimum(self) -> float:
            return self._ymin

        def xMaximum(self) -> float:
            return self._xmax

        def yMaximum(self) -> float:
            return self._ymax

        def center(self) -> QgsPointXY:
            return QgsPointXY(
                (self._xmin + self._xmax) / 2.0,
                (self._ymin + self._ymax) / 2.0,
            )

    class QgsProject:
        @staticmethod
        def instance() -> "QgsProject":
            return QgsProject()

    class QgsCoordinateReferenceSystem:
        def __init__(self, epsg_id: int = 4326) -> None:
            self._epsg_id = epsg_id

        @classmethod
        def fromEpsgId(cls, epsg_id: int) -> "QgsCoordinateReferenceSystem":
            return cls(epsg_id)

        def postgisSrid(self) -> int:
            return self._epsg_id

    class QgsCoordinateTransform:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            pass

        def transform(self, point: QgsPointXY) -> QgsPointXY:
            return QgsPointXY(point)

        def transformBoundingBox(
            self,
            rectangle: QgsRectangle,
        ) -> QgsRectangle:
            return QgsRectangle(rectangle)

    class QLocale:
        @staticmethod
        def system():
            return QLocale()

        def name(self) -> str:
            return "en_US"

    class QByteArray(bytes):
        pass

    class QModelIndex:
        def __init__(self, row_index: int = -1) -> None:
            self._row_index = row_index

        def isValid(self) -> bool:
            return self._row_index >= 0

        def row(self) -> int:
            return self._row_index

    class QAbstractListModel:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            pass

        def beginResetModel(self) -> None:
            pass

        def endResetModel(self) -> None:
            pass

    class Qt:
        class ItemDataRole:
            DisplayRole = 0
            EditRole = 2

        class CaseSensitivity:
            CaseInsensitive = 0

    class QMimeData:
        def setData(self, mime_type: str, data) -> None:
            self.mime_type = mime_type
            self.data = data

        def setText(self, text: str) -> None:
            self.text = text

    class QClipboard:
        class Mode:
            Selection = 1
            Clipboard = 2

    class QCompleter:
        class CompletionMode:
            PopupCompletion = 0

        def __init__(self, model=None, parent: Any = None) -> None:
            self._model = model
            self._parent = parent
            self._widget = None
            self._case_sensitivity = None
            self._completion_mode = None

        def setCaseSensitivity(self, value: Any) -> None:
            self._case_sensitivity = value

        def setCompletionMode(self, value: Any) -> None:
            self._completion_mode = value

        def widget(self):
            return self._widget

        def setWidget(self, widget: Any) -> None:
            self._widget = widget

    class QWidget:
        def __init__(self, parent: Optional["QWidget"] = None) -> None:
            self._parent = parent

    class QLineEdit(QWidget):
        def __init__(
            self,
            text: str = "",
            parent: Optional[QWidget] = None,
        ) -> None:
            super().__init__(parent)
            self._text = text
            self._cursor_position = len(text)

        def text(self) -> str:
            return self._text

        def setText(self, text: str) -> None:
            self._text = text
            self._cursor_position = len(text)

        def cursorPosition(self) -> int:
            return self._cursor_position

        def setCursorPosition(self, position: int) -> None:
            self._cursor_position = position

    class QComboBox(QWidget):
        def __init__(self, parent: Optional[QWidget] = None) -> None:
            super().__init__(parent)
            self._line_edit = QLineEdit(parent=self)

        def lineEdit(self) -> QLineEdit:
            return self._line_edit

        def setLineEdit(self, line_edit: QLineEdit) -> None:
            self._line_edit = line_edit

    class QgsMapCanvas:
        pass

    qgis_module_any = cast(Any, qgis_module)
    qgis_core_module_any = cast(Any, qgis_core_module)
    qgis_gui_module_any = cast(Any, qgis_gui_module)
    qgis_pyqt_module_any = cast(Any, qgis_pyqt_module)
    qgis_pyqt_qtcore_module_any = cast(Any, qgis_pyqt_qtcore_module)
    qgis_pyqt_qtgui_module_any = cast(Any, qgis_pyqt_qtgui_module)
    qgis_pyqt_qtwidgets_module_any = cast(Any, qgis_pyqt_qtwidgets_module)
    qgis_core_module_any.QgsApplication = QgsApplication
    qgis_core_module_any.QgsPointXY = QgsPointXY
    qgis_core_module_any.QgsRectangle = QgsRectangle
    qgis_core_module_any.QgsProject = QgsProject
    qgis_core_module_any.QgsCoordinateReferenceSystem = (
        QgsCoordinateReferenceSystem
    )
    qgis_core_module_any.QgsCoordinateTransform = QgsCoordinateTransform
    qgis_core_module_any.QgsSettings = QgsSettings
    qgis_module_any.core = qgis_core_module
    qgis_gui_module_any.QgsMapCanvas = QgsMapCanvas
    qgis_module_any.gui = qgis_gui_module
    qgis_pyqt_qtcore_module_any.QByteArray = QByteArray
    qgis_pyqt_qtcore_module_any.QAbstractListModel = QAbstractListModel
    qgis_pyqt_qtcore_module_any.QModelIndex = QModelIndex
    qgis_pyqt_qtcore_module_any.QSettings = QSettings
    qgis_pyqt_qtcore_module_any.Qt = Qt
    qgis_pyqt_qtcore_module_any.QLocale = QLocale
    qgis_pyqt_qtcore_module_any.QMimeData = QMimeData
    qgis_pyqt_qtgui_module_any.QClipboard = QClipboard
    qgis_pyqt_qtwidgets_module_any.QComboBox = QComboBox
    qgis_pyqt_qtwidgets_module_any.QCompleter = QCompleter
    qgis_pyqt_qtwidgets_module_any.QLineEdit = QLineEdit
    qgis_pyqt_qtwidgets_module_any.QWidget = QWidget
    qgis_pyqt_qtcore_module_any.QLocale = QLocale
    qgis_pyqt_module_any.QtCore = qgis_pyqt_qtcore_module
    qgis_pyqt_module_any.QtGui = qgis_pyqt_qtgui_module
    qgis_pyqt_module_any.QtWidgets = qgis_pyqt_qtwidgets_module
    qgis_module_any.PyQt = qgis_pyqt_module
    sys.modules["qgis"] = qgis_module
    sys.modules["qgis.core"] = qgis_core_module
    sys.modules["qgis.gui"] = qgis_gui_module
    sys.modules["qgis.PyQt"] = qgis_pyqt_module
    sys.modules["qgis.PyQt.QtCore"] = qgis_pyqt_qtcore_module
    sys.modules["qgis.PyQt.QtGui"] = qgis_pyqt_qtgui_module
    sys.modules["qgis.PyQt.QtWidgets"] = qgis_pyqt_qtwidgets_module

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
