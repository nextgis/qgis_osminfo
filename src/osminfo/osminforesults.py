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
from typing import TYPE_CHECKING, Dict, List, Optional, Tuple, cast

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
    QgsProject,
    QgsRectangle,
    QgsVectorLayer,
)
from qgis.gui import QgisInterface, QgsDockWidget, QgsMessageBar
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
    QMainWindow,
    QMenu,
    QMessageBox,
    QTreeWidgetItem,
)
from qgis.utils import iface

from osminfo.compat import (
    FieldType,
    GeometryType,
    addMapLayer,
)
from osminfo.logging import logger
from osminfo.openstreetmap.tag2link import TagLink, TagLinkResolver
from osminfo.osmelements import OsmElement, parseOsmElement
from osminfo.overpass.query_task import OverpassQueryTask
from osminfo.settings.osm_info_settings import OsmInfoSettings
from osminfo.ui.icon import material_icon, plugin_icon, qgis_icon
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
            QMessageBox.StandardButtons()
            | Button.Yes
            | Button.No
            | Button.Cancel,
        )
        self.setDefaultButton(Button.Yes)


class OsmInfoResultsDock(QgsDockWidget, FORM_CLASS):
    loadingStateChanged = pyqtSignal(bool)

    def __init__(self, title: str, result_render):
        main_window = cast(QMainWindow, iface.mainWindow())
        super().__init__(title, parent=main_window)

        self.setupUi(self)
        self.setWindowTitle(title)
        self.setObjectName("OsmInfoResultsDock")

        self.setAllowedAreas(
            Qt.DockWidgetAreas()
            | Qt.DockWidgetArea.LeftDockWidgetArea
            | Qt.DockWidgetArea.RightDockWidgetArea
        )

        self.__rb = result_render
        self.__tag_link_resolver = TagLinkResolver()
        self.__selected_id = None
        self.__selected_geom = None
        self.__active_task: Optional[OverpassQueryTask] = None
        self.__active_task_kind: Optional[str] = None
        self.__active_endpoint = ""
        self.__pending_queries: List[Tuple[str, str]] = []
        self.__query_results: Dict[str, List] = {
            "nearby": [],
            "enclosing": [],
        }
        self.__is_loading = False

        self.__resultsTree = self.results_tree
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

        vLayer = None
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
            vLayer = iface.layerTreeView().selectedLayers()[0]

        if vLayer is None:
            return

        dataProvider = vLayer.dataProvider()
        assert dataProvider is not None

        string_type = FieldType.QString
        if create_new:
            dataProvider.addAttributes(
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

                    dataProvider.addAttributes(
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
                QgsMessageBar.WARNING,
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

    def getInfo(self, xx, yy):
        self.__cancel_active_task()

        self.__resultsTree.clear()
        self.__resultsTree.addTopLevelItem(
            QTreeWidgetItem([self.tr("Loading...")])
        )

        validation_error = self.__validate_coordinates(xx, yy)
        if validation_error is not None:
            self.__finish_loading()
            self.showError(validation_error)
            return

        settings = OsmInfoSettings()
        if not settings.fetch_nearby and not settings.fetch_enclosing:
            self.__finish_loading()
            self.showError(self.tr("No object category selected in settings"))
            return

        self.__active_endpoint = settings.overpass_url
        if len(self.__active_endpoint) == 0:
            self.__finish_loading()
            self.showError(self.tr("Custom Overpass API URL is not set"))
            return

        self.__pending_queries = self.__build_queries(settings, xx, yy)
        self.__query_results = {
            "nearby": [],
            "enclosing": [],
        }

        self.__start_loading()
        self.__start_next_query()

    def __start_loading(self) -> None:
        if self.__is_loading:
            return

        self.__is_loading = True
        self.loadingStateChanged.emit(True)

    def __finish_loading(self) -> None:
        if not self.__is_loading:
            return

        self.__is_loading = False
        self.loadingStateChanged.emit(False)

    def __cancel_active_task(self) -> None:
        if self.__active_task is not None:
            self.__active_task.cancel()

        self.__reset_query_state()

    def __reset_query_state(self) -> None:
        self.__active_task = None
        self.__active_task_kind = None
        self.__active_endpoint = ""
        self.__pending_queries = []
        self.__query_results = {
            "nearby": [],
            "enclosing": [],
        }

    def __validate_coordinates(self, xx: str, yy: str) -> Optional[str]:
        try:
            longitude = float(xx)
            latitude = float(yy)
        except (TypeError, ValueError):
            return self.tr("%s, %s are wrong coords!") % (xx, yy)

        if abs(longitude) > 180 or abs(latitude) > 90:
            return self.tr("%s, %s are wrong coords!") % (xx, yy)

        return None

    def __build_queries(
        self,
        settings: OsmInfoSettings,
        xx: str,
        yy: str,
    ) -> List[Tuple[str, str]]:
        queries: List[Tuple[str, str]] = []

        if settings.fetch_nearby:
            queries.append(
                ("nearby", self.__build_nearby_query(settings, xx, yy))
            )

        if settings.fetch_enclosing:
            queries.append(
                (
                    "enclosing",
                    self.__build_enclosing_query(settings, xx, yy),
                )
            )

        return queries

    def __build_nearby_query(
        self,
        settings: OsmInfoSettings,
        xx: str,
        yy: str,
    ) -> str:
        distance = settings.distance
        return f"""
            [out:json][timeout:{settings.timeout}];
            (
                node(around:{distance},{yy},{xx});
                way(around:{distance},{yy},{xx});
                relation(around:{distance},{yy},{xx});
            );
            out tags geom;
        """

    def __build_enclosing_query(
        self,
        settings: OsmInfoSettings,
        xx: str,
        yy: str,
    ) -> str:
        # TODO is .b really needed there? Probably this is a bug in overpass
        return f"""
            [out:json][timeout:{settings.timeout}];
            is_in({yy},{xx})->.a;
            way(pivot.a)->.b;
            .b out tags geom;
            .b <;
            out geom;
            relation(pivot.a);
            out geom;
        """

    def __start_next_query(self) -> None:
        if len(self.__pending_queries) == 0:
            nearby_elements = self.__query_results["nearby"]
            enclosing_elements = self.__query_results["enclosing"]
            self.__query_results = {
                "nearby": [],
                "enclosing": [],
            }
            self.__active_endpoint = ""
            self.showData(nearby_elements, enclosing_elements)
            self.__finish_loading()
            return

        query_kind, query = self.__pending_queries.pop(0)
        task = OverpassQueryTask(self.__active_endpoint, query)
        task.taskCompleted.connect(self.__on_query_task_completed)
        task.taskTerminated.connect(self.__on_query_task_terminated)

        self.__active_task = task
        self.__active_task_kind = query_kind
        QgsApplication.taskManager().addTask(task)

    @pyqtSlot()
    def __on_query_task_completed(self) -> None:
        sender = self.sender()
        if sender is not self.__active_task or self.__active_task_kind is None:
            return

        self.__query_results[self.__active_task_kind] = (
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
        }
        self.__finish_loading()

        if error is not None:
            self.showError(error.user_message)

    def showError(self, msg):
        logger.error(msg)
        self.__resultsTree.clear()
        self.__resultsTree.addTopLevelItem(QTreeWidgetItem([msg]))

    def showData(self, l1: List, l2: List):
        self.__resultsTree.clear()

        settings = OsmInfoSettings()
        if len(l1) + len(l2) == 0:
            self.__resultsTree.addTopLevelItem(
                QTreeWidgetItem([self.tr("No features found")])
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
