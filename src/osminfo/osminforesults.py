# ******************************************************************************
#
# OSMInfo
# ---------------------------------------------------------
# This plugin takes coordinates of a mouse click and gets information about all
# objects from this point from OSM using Overpass API.
#
# Author:   Maxim Dubinin, sim@gis-lab.info
# Author:   Alexander Lisovenko, alexander.lisovenko@nextgis.com
# Author:   Artem Svetlov, artem.svetlov@nextgis.com
# *****************************************************************************
# Copyright (c) 2012-2023. NextGIS, info@nextgis.com
#
# This source is free software; you can redistribute it and/or modify it under
# the terms of the GNU General Public License as published by the Free
# Software Foundation, either version 2 of the License, or (at your option)
# any later version.
#
# This code is distributed in the hope that it will be useful, but WITHOUT ANY
# WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS
# FOR A PARTICULAR PURPOSE. See the GNU General Public License for more
# details.
#
# A copy of the GNU General Public License is available on the World Wide Web
# at <http://www.gnu.org/licenses/>. You can also obtain it by writing
# to the Free Software Foundation, 51 Franklin Street, Suite 500 Boston,
# MA 02110-1335 USA.
#
# ******************************************************************************

from datetime import datetime, timezone
from enum import IntEnum
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple, cast

from qgis.core import (
    Qgis,
    QgsApplication,
    QgsCoordinateReferenceSystem,
    QgsCoordinateTransform,
    QgsEditError,
    QgsFeature,
    QgsField,
    QgsGeometry,
    QgsMessageLog,
    QgsPointXY,
    QgsProject,
    QgsRectangle,
    QgsVectorLayer,
)
from qgis.gui import QgisInterface, QgsDockWidget
from qgis.PyQt import uic
from qgis.PyQt.QtCore import (
    QByteArray,
    QLocale,
    QSettings,
    Qt,
    QUrl,
    pyqtSignal,
    pyqtSlot,
)
from qgis.PyQt.QtGui import QBrush, QDesktopServices
from qgis.PyQt.QtWidgets import (
    QAction,
    QHeaderView,
    QMenu,
    QMessageBox,
    QToolButton,
    QTreeWidgetItem,
)
from qgis.utils import iface

from osminfo.about_dialog import AboutDialog
from osminfo.compat import (
    FieldType,
    GeometryType,
    addMapLayer,
)
from osminfo.core.constants import PACKAGE_NAME
from osminfo.core.exceptions import OsmInfoQueryBuilderError
from osminfo.logging import logger
from osminfo.nominatim.geocode_task import GeocodeTask
from osminfo.openstreetmap.tag2link import TagLink, TagLinkResolver
from osminfo.osmelements import OsmElement, parseOsmElement
from osminfo.overpass.query_builder import (
    QueryBuilder,
    QueryContext,
    QueryPostprocessor,
)
from osminfo.overpass.query_builder.wizard import PlaceholderBuilder
from osminfo.overpass.query_task import OverpassQueryTask
from osminfo.settings.osm_info_settings import OsmInfoSettings
from osminfo.ui.icon import material_icon, plugin_icon, qgis_icon
from osminfo.ui.loading_tool_button import LoadingToolButton
from osminfo.utils import set_clipboard_data

if TYPE_CHECKING:
    assert isinstance(iface, QgisInterface)


class ResultTreeItemType(IntEnum):
    FEATURE = 1001
    TAG = 1002


class ResultTreeItemDataRole(IntEnum):
    OSM_ELEMENT = int(Qt.ItemDataRole.UserRole)
    TAG_LINKS = int(Qt.ItemDataRole.UserRole) + 1


class ResultTreeColumn(IntEnum):
    FEATURE_OR_KEY = 0
    VALUE = 1


FORM_CLASS, _ = uic.loadUiType(
    Path(__file__).parent / "ui" / "osm_info_results_widget_base.ui"
)


class AttributeMismatchMessageBox(QMessageBox):
    def __init__(self, parent=None):
        super().__init__(parent)

        self.setIcon(QMessageBox.Icon.Question)
        self.setWindowTitle(self.tr("Attribute mismatch"))
        self.setInformativeText(self.tr("Add missing attributes?"))
        self.setText(
            self.tr(
                "The feature you are trying to add has attributes that are not "
                "present in the target layer."
            )
        )

        Button = QMessageBox.StandardButton
        self.setStandardButtons(
            Button.Yes | Button.No | Button.Cancel,
        )
        self.setDefaultButton(Button.Yes)


class OsmInfoResultsDock(QgsDockWidget, FORM_CLASS):
    loadingStateChanged = pyqtSignal(bool)

    def __init__(self, title: str, result_render, parent=None):
        super().__init__(title, parent=parent)

        self.setupUi(self)
        self.setWindowTitle(title)
        self.setObjectName("OsmInfoResultsDock")

        self.setAllowedAreas(
            Qt.DockWidgetArea.LeftDockWidgetArea
            | Qt.DockWidgetArea.RightDockWidgetArea
        )

        self.__rb = result_render
        self.__tag_link_resolver = TagLinkResolver()
        self.__selected_id = None
        self.__selected_geom = None
        self.__active_task: Optional[OverpassQueryTask] = None
        self.__active_geocode_task: Optional[GeocodeTask] = None
        self.__active_task_kind: Optional[str] = None
        self.__active_endpoint = ""
        self.__pending_queries: List[Tuple[str, str, Optional[int]]] = []
        self.__staged_queries: List[str] = []
        self.__staged_query_kinds: List[str] = []
        self.__staged_timeout_seconds: Optional[int] = None
        self.__query_context: Optional[QueryContext] = None
        self.__query_results: Dict[str, List] = {
            "nearby": [],
            "enclosing": [],
            "search": [],
        }
        self.__is_loading = False
        self.__placeholder_builder = PlaceholderBuilder()

        self.search_combobox.lineEdit().setPlaceholderText(
            self.__placeholder_builder.build()
        )

        self.__resultsTree = self.results_tree
        self.search_button = LoadingToolButton(
            ":images/themes/default/mIconLoading.gif",
            material_icon("map_search"),
            material_icon("cancel"),
            self,
        )
        self.search_button.setObjectName("search_button")
        self.search_button.setToolTip(self.tr("Search OSM features"))
        self.search_button.clicked.connect(self.__search_by_current_text)
        self.search_button.cancelRequested.connect(self.__cancel_search)
        self.search_button.setFixedSize(
            self.search_combobox.sizeHint().height(),
            self.search_combobox.sizeHint().height(),
        )
        self.search_layout.addWidget(self.search_button)

        self.menu_button = QToolButton(self)
        self.menu_button.setObjectName("menu_button")
        self.menu_button.setIcon(material_icon("menu"))
        self.menu_button.setToolTip(self.tr("Open OSMInfo menu"))
        self.menu_button.setFixedSize(
            self.search_combobox.sizeHint().height(),
            self.search_combobox.sizeHint().height(),
        )
        self.menu_button.setStyleSheet(
            """
            QToolButton::menu-indicator {
                image: none;
            }
            """
        )

        search_menu = QMenu(self.menu_button)
        settings_action = QAction(
            qgis_icon("iconSettingsConsole.svg"),
            self.tr("Settings"),
            self.menu_button,
        )
        settings_action.triggered.connect(self.__open_settings)
        about_action = QAction(
            qgis_icon("mActionPropertiesWidget.svg"),
            self.tr("About plugin…"),
            self,
        )
        about_action.triggered.connect(self.__show_about)

        search_menu.addAction(settings_action)
        search_menu.addAction(about_action)

        self.menu_button.setMenu(search_menu)
        self.menu_button.setPopupMode(
            QToolButton.ToolButtonPopupMode.InstantPopup
        )

        self.search_layout.addWidget(self.menu_button)

        self.__resultsTree.setContextMenuPolicy(
            Qt.ContextMenuPolicy.CustomContextMenu
        )
        self.__resultsTree.customContextMenuRequested.connect(self.openMenu)

        self.__resultsTree.setMinimumSize(150, 300)
        self.__resultsTree.setColumnCount(2)
        self.__resultsTree.setHeaderLabels(
            [self.tr("Feature/Key"), self.tr("Value")]
        )
        if hasattr(self.__resultsTree.header(), "setResizeMode"):
            self.__resultsTree.header().setResizeMode(
                QHeaderView.ResizeMode.ResizeToContents
            )
        else:
            self.__resultsTree.header().setSectionResizeMode(
                QHeaderView.ResizeMode.ResizeToContents
            )
        self.__resultsTree.header().setStretchLastSection(False)
        self.__resultsTree.itemSelectionChanged.connect(self.selItemChanged)
        self.__resultsTree.itemActivated.connect(self.__on_item_activated)

        self.__tag_link_brush = QBrush(self.__resultsTree.palette().link())
        self.__tag_link_font = self.__resultsTree.font()
        self.__tag_link_font.setUnderline(True)

        self.__resultsTree.clear()

        search_line_edit = self.search_combobox.lineEdit()
        if search_line_edit is not None:
            search_line_edit.returnPressed.connect(
                self.__search_by_current_text
            )

        overrideLocale = QSettings().value(
            "locale/overrideFlag", False, type=bool
        )
        if not overrideLocale:
            self.qgisLocale = QLocale.system().name()[:2]
        else:
            self.qgisLocale = QSettings().value(
                "locale/userLocale", "", type=str
            )[:2]

        self.show_info()

    def __del__(self) -> None:
        self.__cancel_active_task()

    def show_info(self) -> None:
        black_friday_start = datetime(
            year=2025, month=12, day=1, hour=6, minute=1, tzinfo=timezone.utc
        ).timestamp()
        black_friday_finish = datetime(
            year=2025, month=12, day=6, hour=5, minute=59, tzinfo=timezone.utc
        ).timestamp()

        now = datetime.now().timestamp()

        is_black_friday = black_friday_start <= now <= black_friday_finish

        campaign = "constant" if not is_black_friday else "black-friday25"
        utm = f"utm_source=qgis_plugin&utm_medium=banner&utm_campaign={campaign}&utm_term=osminfo&utm_content={self.qgisLocale}"

        info = {
            "constant": self.tr(
                '<a href="https://data.nextgis.com/?{utm}">Download geodata</a> for your project'
            ).format(utm=utm),
            "black-friday25": self.tr(
                '<a href="https://data.nextgis.com/?{utm}">Fresh geodata</a> for your project <b>(50% off!)</b>'
            ).format(utm=utm),
        }
        icon = {
            "constant": ":/plugins/osminfo/icons/news.png",
            "black-friday25": ":/plugins/osminfo/icons/fire.png",
        }
        html = f"""
            <html>
            <head></head>
            <body>
                <center>
                    <table>
                        <tr>
                            <td><img src="{icon[campaign]}"></td>
                            <td>&nbsp;{info[campaign]}</td>
                        </tr>
                    </table>
                </center>
            </body>
            </html>
        """
        self.info_label.setText(html)

    def openMenu(self, position):
        selected_items = self.__resultsTree.selectedItems()
        if len(selected_items) == 0 or selected_items[0].type() not in [
            ResultTreeItemType.TAG,
            ResultTreeItemType.FEATURE,
        ]:
            return

        menu = QMenu()

        actionZoom = QAction(
            plugin_icon("zoom2feature.png"),
            self.tr("Zoom to feature"),
            self,
        )
        menu.addAction(actionZoom)
        actionZoom.triggered.connect(self.zoom2feature)

        actionCopy2Clipboard = QAction(
            qgis_icon("mActionEditCopy.svg"),
            self.tr("Copy feature to clipboard"),
            self,
        )
        actionCopy2Clipboard.triggered.connect(self.copy2Clipboard)
        menu.addAction(actionCopy2Clipboard)

        actionMove2NewTempLayer = QAction(
            qgis_icon("mActionCreateMemory.svg"),
            self.tr("Save feature in new temporary layer"),
            self,
        )
        menu.addAction(actionMove2NewTempLayer)
        actionMove2NewTempLayer.triggered.connect(
            lambda: self.copy2Layer(True)
        )

        actionMove2SelectedLayer = QAction(
            qgis_icon("mActionCreateMemory.svg"),
            self.tr("Save feature in selected layer"),
            self,
        )
        actionMove2SelectedLayer.setEnabled(
            self.__is_current_layer_can_store_element()
        )
        menu.addAction(actionMove2SelectedLayer)
        actionMove2SelectedLayer.triggered.connect(
            lambda: self.copy2Layer(False)
        )

        open_in_osm_action = QAction(
            plugin_icon("osm_logo.svg"),
            self.tr("Open in OpenStreetMap"),
            self,
        )
        open_in_osm_action.triggered.connect(self.__open_in_osm)
        menu.addAction(open_in_osm_action)

        copy_link_to_osm_action = QAction(
            plugin_icon("osm_logo.svg"),
            self.tr("Copy OpenStreetMap URL"),
            self,
        )
        copy_link_to_osm_action.triggered.connect(self.__copy_osm_url)
        menu.addAction(copy_link_to_osm_action)

        tag_item = selected_items[0]
        if tag_item.type() == ResultTreeItemType.TAG:
            tag_links = self.__tag_links_from_item(tag_item)
            if len(tag_links) > 0:
                menu.addSeparator()
                self.__populate_tag_link_menu(menu, tag_links)

        menu.exec(self.__resultsTree.viewport().mapToGlobal(position))

    def __populate_tag_link_menu(
        self, menu: QMenu, tag_links: Tuple[TagLink, ...]
    ) -> None:
        if len(tag_links) == 1:
            tag_link = tag_links[0]

            open_link_action = QAction(self.tr("Open tag link"), self)
            open_link_action.setIcon(material_icon("open_in_new"))
            open_link_action.triggered.connect(
                lambda checked=False, url=tag_link.url: self.__open_url(url)
            )
            menu.addAction(open_link_action)

            copy_link_action = QAction(self.tr("Copy tag link"), self)
            copy_link_action.setIcon(material_icon("link"))
            copy_link_action.triggered.connect(
                lambda checked=False, url=tag_link.url: self.__copy_link(url)
            )
            menu.addAction(copy_link_action)
            return

        open_links_menu = menu.addMenu(self.tr("Open tag links"))
        copy_links_menu = menu.addMenu(self.tr("Copy tag links"))
        open_links_menu.setIcon(material_icon("open_in_new"))
        copy_links_menu.setIcon(material_icon("link"))

        for tag_link in tag_links:
            open_action = QAction(tag_link.title, self)
            open_action.triggered.connect(
                lambda checked=False, url=tag_link.url: self.__open_url(url)
            )
            open_links_menu.addAction(open_action)

            copy_action = QAction(tag_link.title, self)
            copy_action.triggered.connect(
                lambda checked=False, url=tag_link.url: self.__copy_link(url)
            )
            copy_links_menu.addAction(copy_action)

    def zoom2feature(self):
        selected_items = self.__resultsTree.selectedItems()
        if len(selected_items) == 0:
            return

        item = selected_items[0]
        # if selected tag - use parent
        if item.type() == ResultTreeItemType.TAG:
            item = item.parent()
        if item and item.type() == ResultTreeItemType.FEATURE:
            osm_element = self.__osm_element_from_item(item)
            geom = osm_element.asQgisGeometry()
            self.__rb.zoom_to_bbox(geom.boundingBox())

    def copy2Layer(self, create_new: bool):
        selected_items = self.__resultsTree.selectedItems()
        if len(selected_items) != 1:
            return

        item = selected_items[0]
        # if selected tag - use parent
        if item.type() == ResultTreeItemType.TAG:
            item = item.parent()
        if not item or item.type() != ResultTreeItemType.FEATURE:
            return

        osm_element = self.__osm_element_from_item(item)

        if osm_element is None:
            iface.messageBar().pushMessage(
                "OSM Info",
                "Cann't parse OSM Element.",
                Qgis.MessageLevel.Warning,
                2,
            )
            return

        geom = osm_element.asQgisGeometry()
        if geom is None:
            geom = self.__selected_geom

        assert geom is not None

        if geom.type() == GeometryType.Polygon:
            geom_type = "Polygon"
        elif geom.type() == GeometryType.Line:
            geom_type = "LineString"
        elif geom.type() == GeometryType.Point:
            geom_type = "Point"
        else:
            return

        geom_type = "Multi" * geom.isMultipart() + geom_type

        vLayer: Optional[QgsVectorLayer] = None
        if create_new:
            vLayer = QgsVectorLayer(
                f"{geom_type}?crs=EPSG:4326",
                item.data(
                    ResultTreeColumn.FEATURE_OR_KEY,
                    Qt.ItemDataRole.DisplayRole,
                ),
                "memory",
            )
        else:
            selected_layer = iface.layerTreeView().selectedLayers()[0]
            if not isinstance(selected_layer, QgsVectorLayer):
                return

            vLayer = selected_layer

        if vLayer is None:
            return

        data_provider = cast(Any, vLayer.dataProvider())
        assert data_provider is not None

        string_type = FieldType.QString
        if create_new:
            data_provider.addAttributes(
                [QgsField(k, string_type) for k in osm_element.tags]
            )
        else:
            if not self.__is_current_layer_contains_all_fields(osm_element):
                message_box = AttributeMismatchMessageBox()
                result_button = message_box.exec()
                Button = QMessageBox.StandardButton
                if result_button == Button.Cancel:
                    return

                if result_button == Button.Yes:
                    element_tags = osm_element.tags.keys()
                    layer_fields = vLayer.fields().names()
                    new_fields = set(element_tags) - set(layer_fields)

                    data_provider.addAttributes(
                        [
                            QgsField(key, string_type)
                            for key in element_tags
                            if key in new_fields
                        ]
                    )

        vLayer.updateFields()

        # add a feature
        feature = QgsFeature(vLayer.fields())
        if vLayer.crs().authid() != "EPSG:4326":
            transformator = QgsCoordinateTransform(
                QgsCoordinateReferenceSystem.fromEpsgId(4326),
                vLayer.crs(),
                QgsProject.instance(),
            )
            geom.transform(transformator)
        feature.setGeometry(geom)

        layer_fields = vLayer.fields().names()

        attributes = [
            osm_element.tags.get(layer_field) for layer_field in layer_fields
        ]
        feature.setAttributes(attributes)

        in_edit_mode = vLayer.isEditable()
        if not in_edit_mode:
            assert vLayer.startEditing()

        vLayer.beginEditCommand(f"Added OSM feature (id={osm_element.osm_id})")
        vLayer.addFeature(feature)
        vLayer.endEditCommand()

        if not in_edit_mode:
            is_committed = vLayer.commitChanges(stopEditing=True)
            if not is_committed:
                raise QgsEditError(vLayer.commitErrors())

        if create_new:
            addMapLayer(vLayer)
        else:
            vLayer.reload()

    def __is_current_layer_can_store_element(self) -> bool:
        layers = iface.layerTreeView().selectedLayers()
        if len(layers) != 1:
            return False

        if not isinstance(layers[0], QgsVectorLayer):
            return False

        items = self.__resultsTree.selectedItems()
        if not items:
            return False

        item = items[0]

        if item.type() == ResultTreeItemType.TAG:
            item = item.parent()
        if not item or item.type() != ResultTreeItemType.FEATURE:
            return False

        osm_element = self.__osm_element_from_item(item)
        if osm_element is None:
            return False

        layer: QgsVectorLayer = layers[0]
        geom = osm_element.asQgisGeometry()
        if layer.geometryType() != geom.type():
            return False

        return True

    def __is_current_layer_contains_all_fields(
        self, element: OsmElement
    ) -> bool:
        layers = iface.layerTreeView().selectedLayers()
        if len(layers) != 1:
            return False

        if not isinstance(layers[0], QgsVectorLayer):
            return False

        layer: QgsVectorLayer = layers[0]
        field_names = layer.fields().names()

        element_tags = element.tags.keys()

        return len(set(element_tags) - set(field_names)) == 0

    def copy2Clipboard(self):
        selected_items = self.__resultsTree.selectedItems()
        if len(selected_items) != 1:
            return

        item = selected_items[0]
        # if selected tag - use parent
        if item.type() == ResultTreeItemType.TAG:
            item = item.parent()

        if not item or item.type() != ResultTreeItemType.FEATURE:
            return

        osm_element = self.__osm_element_from_item(item)
        if osm_element is None:
            return

        # dst_crs = iface.mapCanvas().mapSettings().destinationCrs().authid()
        if osm_element is None:
            iface.messageBar().pushMessage(
                "OSM Info",
                "Cann't parse OSM Element.",
                Qgis.MessageLevel.Warning,
                2,
            )
            return

        geom = osm_element.asQgisGeometry()
        if geom is None:
            geom = self.__selected_geom
        assert geom is not None
        if geom.type() == GeometryType.Polygon:
            geom_type = "Polygon"
        elif geom.type() == GeometryType.Line:
            geom_type = "LineString"
        elif geom.type() == GeometryType.Point:
            geom_type = "Point"
        else:
            return

        geom_type = "Multi" * geom.isMultipart() + geom_type

        vl = QgsVectorLayer(
            f"{geom_type}?crs=EPSG:4326",
            item.data(
                ResultTreeColumn.FEATURE_OR_KEY,
                Qt.ItemDataRole.DisplayRole,
            ),
            "memory",
        )

        pr = vl.dataProvider()

        # add fields
        pr.addAttributes(
            [QgsField(k, FieldType.QString) for k in osm_element.tags]
        )
        vl.updateFields()

        # add a feature
        feature = QgsFeature()
        feature.setGeometry(geom)
        feature.setAttributes(list(osm_element.tags.values()))
        pr.addFeatures([feature])

        vl.selectAll()

        # Set the feature as the clipboard content
        iface.copySelectionToClipboard(vl)

    def getInfo(self, point: QgsPointXY) -> None:
        settings = OsmInfoSettings()
        query_builder = QueryBuilder(settings)

        try:
            queries = query_builder.build_for_coords(point)
        except OsmInfoQueryBuilderError as error:
            self.__cancel_active_task()
            self.showError(error.user_message)
            return

        self.__run_queries(
            settings.overpass_url,
            self.__coordinate_query_kinds(settings),
            queries,
            self.__query_timeout_seconds(settings),
        )

    def set_search_text(self, search_text: str) -> None:
        self.search_combobox.setCurrentText(search_text.strip())

    @pyqtSlot()
    def __search_by_current_text(self) -> None:
        if self.__is_loading:
            return

        settings = OsmInfoSettings()
        query_builder = QueryBuilder(settings)
        search_text = self.search_combobox.currentText().strip()

        try:
            queries = query_builder.build_for_string(search_text)
        except OsmInfoQueryBuilderError as error:
            self.__cancel_active_task()
            repaired_search = query_builder.repair_search(search_text)
            if repaired_search is not None and repaired_search != search_text:
                applied_repair = self.__offer_search_repair(
                    search_text,
                    repaired_search,
                )
                if applied_repair:
                    return

            self.showError(error.user_message)
            return

        if query_builder.last_strategy_name == "coords":
            query_kinds = self.__coordinate_query_kinds(settings)
            timeout_seconds = self.__query_timeout_seconds(settings)
        else:
            query_kinds = ["search"] * len(queries)
            timeout_seconds = self.__query_timeout_seconds(settings)

        self.__run_queries(
            settings.overpass_url,
            query_kinds,
            queries,
            timeout_seconds,
        )

    def __offer_search_repair(
        self,
        original_search: str,
        repaired_search: str,
    ) -> bool:
        return True

    def __run_queries(
        self,
        endpoint: str,
        query_kinds: List[str],
        queries: List[str],
        timeout_seconds: Optional[int],
    ) -> None:
        self.__cancel_active_task()

        self.__resultsTree.clear()
        self.__resultsTree.addTopLevelItem(
            QTreeWidgetItem([self.tr("Loading...")])
        )

        if len(endpoint) == 0:
            self.showError(self.tr("Custom Overpass API URL is not set"))
            return

        map_canvas = iface.mapCanvas()
        if map_canvas is None:
            self.showError(self.tr("Failed to read current map extent."))
            return

        try:
            query_context = QueryContext.from_map_canvas(map_canvas)
            geocoding_data = QueryPostprocessor.extract_geocoding_data(queries)
        except OsmInfoQueryBuilderError as error:
            self.showError(error.user_message)
            return

        if geocoding_data.has_requests():
            self.__active_endpoint = endpoint
            self.__staged_queries = list(queries)
            self.__staged_query_kinds = list(query_kinds)
            self.__staged_timeout_seconds = timeout_seconds
            self.__query_context = query_context
            self.__query_results = {
                "nearby": [],
                "enclosing": [],
                "search": [],
            }
            self.__start_loading()
            self.__start_geocode_task(
                geocoding_data.id_queries,
                geocoding_data.area_queries,
                geocoding_data.bbox_queries,
                geocoding_data.coordinate_queries,
            )
            return

        try:
            queries = QueryPostprocessor().process(queries, query_context)
        except OsmInfoQueryBuilderError as error:
            self.showError(error.user_message)
            return

        if len(queries) == 0 or len(query_kinds) != len(queries):
            self.showError(self.tr("Failed to build Overpass query"))
            return

        self.__active_endpoint = endpoint
        self.__pending_queries = [
            (query_kind, query, timeout_seconds)
            for query_kind, query in zip(query_kinds, queries)
        ]
        self.__query_results = {
            "nearby": [],
            "enclosing": [],
            "search": [],
        }

        self.__start_loading()
        self.__start_next_query()

    def __start_geocode_task(
        self,
        id_queries: Tuple[str, ...],
        area_queries: Tuple[str, ...],
        bbox_queries: Tuple[str, ...],
        coordinate_queries: Tuple[str, ...],
    ) -> None:
        if self.__query_context is None:
            self.showError(self.tr("Failed to read current map extent."))
            self.__finish_loading()
            self.__reset_query_state()
            return

        task = GeocodeTask(
            self.__query_context,
            id_queries,
            area_queries,
            bbox_queries,
            coordinate_queries,
        )
        task.taskCompleted.connect(self.__on_geocode_task_completed)
        task.taskTerminated.connect(self.__on_geocode_task_terminated)
        self.__active_geocode_task = task
        QgsApplication.taskManager().addTask(task)

    def __coordinate_query_kinds(
        self,
        settings: OsmInfoSettings,
    ) -> List[str]:
        query_kinds: List[str] = []
        if settings.fetch_nearby:
            query_kinds.append("nearby")

        if settings.fetch_enclosing:
            query_kinds.append("enclosing")

        return query_kinds

    def __start_loading(self) -> None:
        if self.__is_loading:
            return

        self.__is_loading = True
        self.search_button.start()
        self.loadingStateChanged.emit(True)

    def __finish_loading(self) -> None:
        if not self.__is_loading:
            return

        self.__is_loading = False
        self.search_button.stop()
        self.loadingStateChanged.emit(False)

    def __cancel_active_task(self) -> None:
        if self.__active_task is not None:
            self.__active_task.cancel()
        if self.__active_geocode_task is not None:
            self.__active_geocode_task.cancel()

        self.__finish_loading()
        self.__reset_query_state()

    @pyqtSlot()
    def __cancel_search(self) -> None:
        if not self.__is_loading:
            return

        self.__cancel_active_task()
        self.__resultsTree.clear()
        self.__resultsTree.addTopLevelItem(
            QTreeWidgetItem([self.tr("Search cancelled")])
        )

    def __reset_query_state(self) -> None:
        self.__active_task = None
        self.__active_geocode_task = None
        self.__active_task_kind = None
        self.__active_endpoint = ""
        self.__pending_queries = []
        self.__staged_queries = []
        self.__staged_query_kinds = []
        self.__staged_timeout_seconds = None
        self.__query_context = None
        self.__query_results = {
            "nearby": [],
            "enclosing": [],
            "search": [],
        }

    def __query_timeout_seconds(
        self,
        settings: OsmInfoSettings,
    ) -> Optional[int]:
        if not settings.is_timeout_enabled:
            return None

        return settings.timeout

    def __start_next_query(self) -> None:
        if len(self.__pending_queries) == 0:
            nearby_elements = self.__query_results["nearby"]
            enclosing_elements = self.__query_results["enclosing"]
            search_elements = self.__query_results["search"]
            self.__query_results = {
                "nearby": [],
                "enclosing": [],
                "search": [],
            }
            self.__active_endpoint = ""
            self.showData(
                nearby_elements,
                enclosing_elements,
                search_elements,
            )
            self.__finish_loading()
            return

        query_kind, query, timeout_seconds = self.__pending_queries.pop(0)
        task = OverpassQueryTask(
            self.__active_endpoint,
            query,
            timeout_seconds=timeout_seconds,
        )
        task.taskCompleted.connect(self.__on_query_task_completed)
        task.taskTerminated.connect(self.__on_query_task_terminated)

        self.__active_task = task
        self.__active_task_kind = query_kind
        QgsApplication.taskManager().addTask(task)

    @pyqtSlot()
    def __on_geocode_task_completed(self) -> None:
        sender = self.sender()
        if sender is not self.__active_geocode_task:
            return

        query_context = self.__active_geocode_task.query_context
        staged_queries = list(self.__staged_queries)
        staged_query_kinds = list(self.__staged_query_kinds)
        timeout_seconds = self.__staged_timeout_seconds
        endpoint = self.__active_endpoint

        self.__active_geocode_task = None
        self.__staged_queries = []
        self.__staged_query_kinds = []
        self.__staged_timeout_seconds = None
        self.__query_context = query_context

        try:
            processed_queries = QueryPostprocessor().process(
                staged_queries,
                query_context,
            )
        except OsmInfoQueryBuilderError as error:
            self.__finish_loading()
            self.__reset_query_state()
            self.showError(error.user_message)
            return

        if len(processed_queries) == 0 or len(staged_query_kinds) != len(
            processed_queries
        ):
            self.__finish_loading()
            self.__reset_query_state()
            self.showError(self.tr("Failed to build Overpass query"))
            return

        self.__active_endpoint = endpoint
        self.__pending_queries = [
            (query_kind, query, timeout_seconds)
            for query_kind, query in zip(
                staged_query_kinds,
                processed_queries,
            )
        ]
        self.__start_next_query()

    @pyqtSlot()
    def __on_geocode_task_terminated(self) -> None:
        sender = self.sender()
        if sender is not self.__active_geocode_task:
            return

        error = self.__active_geocode_task.error
        self.__finish_loading()
        self.__reset_query_state()

        if error is not None:
            self.showError(error.user_message)

    @pyqtSlot()
    def __on_query_task_completed(self) -> None:
        sender = self.sender()
        if sender is not self.__active_task or self.__active_task_kind is None:
            return

        self.__query_results[self.__active_task_kind].extend(
            self.__active_task.elements
        )
        self.__active_task = None
        self.__active_task_kind = None

        self.__start_next_query()

    @pyqtSlot()
    def __on_query_task_terminated(self) -> None:
        sender = self.sender()
        if sender is not self.__active_task:
            return

        error = self.__active_task.error
        self.__active_task = None
        self.__active_task_kind = None
        self.__active_endpoint = ""
        self.__pending_queries = []
        self.__query_results = {
            "nearby": [],
            "enclosing": [],
            "search": [],
        }
        self.__finish_loading()

        if error is not None:
            self.showError(error.user_message)

    def showError(self, msg):
        logger.error(msg)
        self.__resultsTree.clear()
        self.__resultsTree.addTopLevelItem(QTreeWidgetItem([msg]))

    def showData(
        self,
        l1: List,
        l2: List,
        search_results: Optional[List] = None,
    ):
        self.__resultsTree.clear()

        settings = OsmInfoSettings()
        if search_results is None:
            search_results = []

        if len(l1) + len(l2) + len(search_results) == 0:
            self.__resultsTree.addTopLevelItem(
                QTreeWidgetItem([self.tr("No features found")])
            )
            return

        if len(search_results) > 0:
            search_root = QTreeWidgetItem([self.tr("Search results")])
            self.__resultsTree.addTopLevelItem(search_root)
            self.__resultsTree.expandItem(search_root)

            for element in search_results:
                try:
                    osm_element = parseOsmElement(element)
                    if osm_element is not None:
                        elementItem = QTreeWidgetItem(
                            search_root,
                            [osm_element.title(self.qgisLocale)],
                            ResultTreeItemType.FEATURE,
                        )
                        self.__set_osm_element_item_data(
                            elementItem, osm_element
                        )

                        for tag in sorted(osm_element.tags.items()):
                            elementItem.addChild(
                                self.__create_tag_item(tag[0], tag[1])
                            )

                        self.__resultsTree.addTopLevelItem(elementItem)
                except Exception as e:
                    QgsMessageLog.logMessage(
                        self.tr(
                            f"Element process error: {e}. Element: {element}."
                        ),
                        self.tr("OSMInfo"),
                        Qgis.MessageLevel.Critical,
                    )
            return

        if settings.fetch_nearby:
            near = QTreeWidgetItem([self.tr("Nearby features")])
            self.__resultsTree.addTopLevelItem(near)
            self.__resultsTree.expandItem(near)

            for element in l1:
                try:
                    osm_element = parseOsmElement(element)
                    # osm_element.asQgisGeometry()
                    if osm_element is not None:
                        elementItem = QTreeWidgetItem(
                            near,
                            [osm_element.title(self.qgisLocale)],
                            ResultTreeItemType.FEATURE,
                        )
                        self.__set_osm_element_item_data(
                            elementItem, osm_element
                        )

                        for tag in sorted(osm_element.tags.items()):
                            elementItem.addChild(
                                self.__create_tag_item(tag[0], tag[1])
                            )

                        self.__resultsTree.addTopLevelItem(elementItem)

                        # qApp.processEvents()
                except Exception as e:
                    QgsMessageLog.logMessage(
                        self.tr(
                            f"Element process error: {e}. Element: {element}."
                        ),
                        self.tr("OSMInfo"),
                        Qgis.MessageLevel.Critical,
                    )

        if settings.fetch_enclosing:
            isin = QTreeWidgetItem([self.tr("Is inside")])
            self.__resultsTree.addTopLevelItem(isin)
            self.__resultsTree.expandItem(isin)

            l2Sorted = sorted(
                l2,
                key=lambda element: (
                    QgsGeometry()
                    .fromRect(
                        QgsRectangle(
                            element["bounds"]["minlon"],
                            element["bounds"]["minlat"],
                            element["bounds"]["maxlon"],
                            element["bounds"]["maxlat"],
                        )
                    )
                    .area()
                ),
            )

            for element in l2Sorted:
                try:
                    osm_element = parseOsmElement(element)
                    if osm_element is not None:
                        elementItem = QTreeWidgetItem(
                            isin,
                            [osm_element.title(self.qgisLocale)],
                            ResultTreeItemType.FEATURE,
                        )
                        self.__set_osm_element_item_data(
                            elementItem, osm_element
                        )
                        for tag in sorted(osm_element.tags.items()):
                            elementItem.addChild(
                                self.__create_tag_item(tag[0], tag[1])
                            )

                        self.__resultsTree.addTopLevelItem(elementItem)
                        # qApp.processEvents()
                except Exception as e:
                    QgsMessageLog.logMessage(
                        self.tr(
                            f"Element process error: {e}. Element: {element}."
                        ),
                        self.tr("OSMInfo"),
                        Qgis.MessageLevel.Critical,
                    )

    def selItemChanged(self):
        selection = self.__resultsTree.selectedItems()
        if not selection:
            return
        item = selection[0]
        # if selected tag - use parent
        if item.type() == ResultTreeItemType.TAG:
            item = item.parent()
        # if already selected - exit
        if self.__selected_id == item:
            return

        self.__selected_geom = None

        # clear old highlights
        self.__rb.clear_feature()
        # set new
        if item and item.type() == ResultTreeItemType.FEATURE:
            self.__selected_id = item
            osm_element = self.__osm_element_from_item(item)
            if osm_element is None:
                return

            self.__rb.show_feature(osm_element.asQgisGeometry())

    def __create_tag_item(self, key: str, value: str) -> QTreeWidgetItem:
        tag_item = QTreeWidgetItem([key, value], ResultTreeItemType.TAG)
        tag_links = self.__tag_link_resolver.resolve(
            key, value, self.qgisLocale
        )
        if len(tag_links) == 0:
            return tag_item

        tag_item.setData(
            ResultTreeColumn.VALUE,
            ResultTreeItemDataRole.TAG_LINKS,
            tag_links,
        )
        tag_item.setForeground(ResultTreeColumn.VALUE, self.__tag_link_brush)
        tag_item.setToolTip(
            ResultTreeColumn.VALUE,
            self.__tag_links_tooltip(tag_links),
        )
        tag_item.setFont(ResultTreeColumn.VALUE, self.__tag_link_font)

        return tag_item

    def __tag_links_tooltip(self, tag_links: Tuple[TagLink, ...]) -> str:
        if len(tag_links) == 1:
            return tag_links[0].url

        return "\n".join(link.url for link in tag_links)

    def __tag_links_from_item(
        self, item: QTreeWidgetItem
    ) -> Tuple[TagLink, ...]:
        if item.type() != ResultTreeItemType.TAG:
            return tuple()

        tag_links = item.data(
            ResultTreeColumn.VALUE, ResultTreeItemDataRole.TAG_LINKS
        )
        if tag_links is None:
            return tuple()

        return tuple(tag_links)

    def __set_osm_element_item_data(
        self, item: QTreeWidgetItem, osm_element: OsmElement
    ) -> None:
        item.setData(
            ResultTreeColumn.FEATURE_OR_KEY,
            ResultTreeItemDataRole.OSM_ELEMENT,
            osm_element,
        )

    def __osm_element_from_item(
        self, item: QTreeWidgetItem
    ) -> Optional[OsmElement]:
        osm_element = item.data(
            ResultTreeColumn.FEATURE_OR_KEY,
            ResultTreeItemDataRole.OSM_ELEMENT,
        )
        if osm_element is None:
            return None

        return cast(OsmElement, osm_element)

    @pyqtSlot(QTreeWidgetItem, int)
    def __on_item_activated(self, item: QTreeWidgetItem, column: int) -> None:
        del column
        tag_links = self.__tag_links_from_item(item)
        if len(tag_links) == 0:
            return

        self.__open_url(tag_links[0].url)

    def __open_url(self, url: str) -> None:
        QDesktopServices.openUrl(QUrl(url))

    def __copy_link(self, link: str) -> None:
        data = QByteArray(link.encode())
        set_clipboard_data("text/plain", data, link)

    @pyqtSlot()
    def __open_in_osm(self) -> None:
        selected_items = self.__resultsTree.selectedItems()
        if len(selected_items) == 0:
            return

        item = selected_items[0]
        if item.type() == ResultTreeItemType.TAG:
            item = item.parent()
        if not item or item.type() != ResultTreeItemType.FEATURE:
            return

        osm_element = self.__osm_element_from_item(item)
        if osm_element is None:
            return

        QDesktopServices.openUrl(
            QUrl(
                f"https://www.openstreetmap.org/{osm_element.type()}/{osm_element.osm_id}"
            )
        )

    @pyqtSlot()
    def __copy_osm_url(self) -> None:
        selected_items = self.__resultsTree.selectedItems()
        if len(selected_items) == 0:
            return

        item = selected_items[0]
        if item.type() == ResultTreeItemType.TAG:
            item = item.parent()
        if not item or item.type() != ResultTreeItemType.FEATURE:
            return

        osm_element = self.__osm_element_from_item(item)
        if osm_element is None:
            return
        link = f"https://www.openstreetmap.org/{osm_element.type()}/{osm_element.osm_id}"
        data = QByteArray(link.encode())
        set_clipboard_data("text/plain", data, link)

    @pyqtSlot()
    def __open_settings(self) -> None:
        iface.showOptionsDialog(iface.mainWindow(), "OSMInfo")

    @pyqtSlot()
    def __show_about(self) -> None:
        dialog = AboutDialog(PACKAGE_NAME)
        dialog.exec()
