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
from pathlib import Path
from typing import TYPE_CHECKING, List, Optional, cast

from qgis.core import (
    Qgis,
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
    QMetaType,
    QSettings,
    Qt,
    QUrl,
    QVariant,
    pyqtSlot,
)
from qgis.PyQt.QtGui import QDesktopServices, QIcon
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
    LineGeometry,
    PointGeometry,
    PolygonGeometry,
    addMapLayer,
)
from osminfo.logging import logger
from osminfo.osmelements import OsmElement, parseOsmElement
from osminfo.osminfo_worker import Worker
from osminfo.settings.osm_info_settings import OsmInfoSettings
from osminfo.utils import set_clipboard_data

if TYPE_CHECKING:
    assert isinstance(iface, QgisInterface)

FeatureItemType = 1001
TagItemType = 1002


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
        self.__selected_id = None
        self.__selected_geom = None
        self.__rel_reply = None
        self.worker = None

        self.__resultsTree = self.results_tree
        self.__resultsTree.setContextMenuPolicy(
            Qt.ContextMenuPolicy.CustomContextMenu
        )
        self.__resultsTree.customContextMenuRequested.connect(self.openMenu)

        self.__resultsTree.setMinimumSize(350, 250)
        self.__resultsTree.setColumnCount(2)
        self.__resultsTree.setHeaderLabels(
            [self.tr("Feature/Key"), self.tr("Value")]
        )
        if hasattr(self.__resultsTree.header(), "setResizeMode"):
            self.__resultsTree.header().setResizeMode(
                QHeaderView.ResizeToContents
            )
        else:
            self.__resultsTree.header().setSectionResizeMode(
                QHeaderView.ResizeToContents
            )
        self.__resultsTree.header().setStretchLastSection(False)
        self.__resultsTree.itemSelectionChanged.connect(self.selItemChanged)
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

    def show_info(self) -> None:
        black_friday_start = datetime(
            year=2024, month=11, day=26, hour=21, minute=1, tzinfo=timezone.utc
        ).timestamp()
        black_friday_finish = datetime(
            year=2024, month=12, day=3, hour=5, minute=59, tzinfo=timezone.utc
        ).timestamp()

        now = datetime.now().timestamp()

        is_black_friday = black_friday_start <= now <= black_friday_finish

        campaign = "constant" if not is_black_friday else "black-friday24"
        utm = f"utm_source=qgis_plugin&utm_medium=banner&utm_campaign={campaign}&utm_term=osminfo&utm_content={self.qgisLocale}"

        info = {
            "constant": self.tr(
                '<a href="https://data.nextgis.com/?{utm}">Download geodata</a> for your project'
            ).format(utm=utm),
            "black-friday24": self.tr(
                '<a href="https://data.nextgis.com/?{utm}">Fresh geodata</a> for your project <b>(50% off!)</b>'
            ).format(utm=utm),
        }
        icon = {
            "constant": ":/plugins/osminfo/icons/news.png",
            "black-friday24": ":/plugins/osminfo/icons/fire.png",
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
            TagItemType,
            FeatureItemType,
        ]:
            return

        menu = QMenu()

        actionZoom = QAction(
            QIcon(":/plugins/osminfo/icons/zoom2feature.png"),
            self.tr("Zoom to feature"),
            self,
        )
        menu.addAction(actionZoom)
        actionZoom.triggered.connect(self.zoom2feature)

        actionCopy2Clipboard = QAction(
            QIcon(":/images/themes/default/mActionEditCopy.svg"),
            self.tr("Copy feature to clipboard"),
            self,
        )
        actionCopy2Clipboard.triggered.connect(self.copy2Clipboard)
        menu.addAction(actionCopy2Clipboard)

        actionMove2NewTempLayer = QAction(
            QIcon(":/images/themes/default/mActionCreateMemory.svg"),
            self.tr("Save feature in new temporary layer"),
            self,
        )
        menu.addAction(actionMove2NewTempLayer)
        actionMove2NewTempLayer.triggered.connect(
            lambda: self.copy2Layer(True)
        )

        actionMove2SelectedLayer = QAction(
            QIcon(":/images/themes/default/mActionCreateMemory.svg"),
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
            QIcon(":/plugins/osminfo/icons/osm_logo.svg"),
            self.tr("Open in OpenStreetMap"),
            self,
        )
        open_in_osm_action.triggered.connect(self.__open_in_osm)
        menu.addAction(open_in_osm_action)

        copy_link_to_osm_action = QAction(
            QIcon(":/plugins/osminfo/icons/osm_logo.svg"),
            self.tr("Copy OpenStreetMap URL"),
            self,
        )
        copy_link_to_osm_action.triggered.connect(self.__copy_osm_url)
        menu.addAction(copy_link_to_osm_action)

        menu.exec(self.__resultsTree.viewport().mapToGlobal(position))

    def zoom2feature(self):
        selected_items = self.__resultsTree.selectedItems()
        if len(selected_items) == 0:
            return

        item = selected_items[0]
        # if selected tag - use parent
        if item.type() == TagItemType:
            item = item.parent()
        if item and item.type() == FeatureItemType:
            osm_element = item.data(0, Qt.ItemDataRole.UserRole)
            geom = osm_element.asQgisGeometry()
            self.__rb.zoom_to_bbox(geom.boundingBox())

    def copy2Layer(self, create_new: bool):
        selected_items = self.__resultsTree.selectedItems()
        if len(selected_items) != 1:
            return

        item = selected_items[0]
        # if selected tag - use parent
        if item.type() == TagItemType:
            item = item.parent()
        if not item or item.type() != FeatureItemType:
            return

        osm_element: Optional[OsmElement] = item.data(
            0, Qt.ItemDataRole.UserRole
        )

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

        if geom.type() == PolygonGeometry:
            geom_type = "Polygon"
        elif geom.type() == LineGeometry:
            geom_type = "LineString"
        elif geom.type() == PointGeometry:
            geom_type = "Point"
        else:
            return

        geom_type = "Multi" * geom.isMultipart() + geom_type

        vLayer = None
        if create_new:
            vLayer = QgsVectorLayer(
                f"{geom_type}?crs=EPSG:4326",
                item.data(0, Qt.ItemDataRole.DisplayRole),
                "memory",
            )
        else:
            vLayer = iface.layerTreeView().selectedLayers()[0]

        if vLayer is None:
            return

        dataProvider = vLayer.dataProvider()
        assert dataProvider is not None

        string_type = (
            QVariant.Type.String
            if Qgis.versionInt() < 33800
            else QMetaType.Type.QString
        )
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

                    string_type = (
                        QVariant.Type.String
                        if Qgis.versionInt() < 33800
                        else QMetaType.Type.QString
                    )
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

        if item.type() == TagItemType:
            item = item.parent()
        if not item or item.type() != FeatureItemType:
            return False

        osm_element: OsmElement = item.data(0, Qt.ItemDataRole.UserRole)

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
        if item.type() == TagItemType:
            item = item.parent()

        if not item or item.type() != FeatureItemType:
            return

        osm_element: OsmElement = item.data(0, Qt.ItemDataRole.UserRole)

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
        if geom.type() == PolygonGeometry:
            geom_type = "Polygon"
        elif geom.type() == LineGeometry:
            geom_type = "LineString"
        elif geom.type() == PointGeometry:
            geom_type = "Point"
        else:
            return

        geom_type = "Multi" * geom.isMultipart() + geom_type

        vl = QgsVectorLayer(
            f"{geom_type}?crs=EPSG:4326",
            item.data(0, Qt.ItemDataRole.DisplayRole),
            "memory",
        )

        pr = vl.dataProvider()

        # add fields
        pr.addAttributes(
            [QgsField(k, QVariant.String) for k in osm_element.tags]
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
        self.__resultsTree.clear()
        self.__resultsTree.addTopLevelItem(
            QTreeWidgetItem([self.tr("Loading...")])
        )

        if self.worker:
            self.worker.gotData.disconnect(self.showData)
            self.worker.gotError.disconnect(self.showError)
            self.worker.finished.connect(self.worker.deleteLater)

        worker = Worker(xx, yy)
        worker.gotData.connect(self.showData)
        worker.gotError.connect(self.showError)
        worker.start()

        self.worker = worker

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
                            FeatureItemType,
                        )
                        elementItem.setData(
                            0, Qt.ItemDataRole.UserRole, osm_element
                        )

                        for tag in sorted(osm_element.tags.items()):
                            elementItem.addChild(
                                QTreeWidgetItem(tag, TagItemType)
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

        if settings.fetch_surrounding:
            isin = QTreeWidgetItem([self.tr("Is inside")])
            self.__resultsTree.addTopLevelItem(isin)
            self.__resultsTree.expandItem(isin)

            l2Sorted = sorted(
                l2,
                key=lambda element: QgsGeometry()
                .fromRect(
                    QgsRectangle(
                        element["bounds"]["minlon"],
                        element["bounds"]["minlat"],
                        element["bounds"]["maxlon"],
                        element["bounds"]["maxlat"],
                    )
                )
                .area(),
            )

            for element in l2Sorted:
                try:
                    osm_element = parseOsmElement(element)
                    if osm_element is not None:
                        elementItem = QTreeWidgetItem(
                            isin,
                            [osm_element.title(self.qgisLocale)],
                            FeatureItemType,
                        )
                        elementItem.setData(
                            0, Qt.ItemDataRole.UserRole, osm_element
                        )
                        for tag in sorted(osm_element.tags.items()):
                            elementItem.addChild(
                                QTreeWidgetItem(tag, TagItemType)
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
        if item.type() == TagItemType:
            item = item.parent()
        # if already selected - exit
        if self.__selected_id == item:
            return

        self.__selected_geom = None

        # clear old highlights
        self.__rb.clear_feature()
        # set new
        if item and item.type() == FeatureItemType:
            self.__selected_id = item
            osm_element = item.data(0, Qt.ItemDataRole.UserRole)

            self.__rb.show_feature(osm_element.asQgisGeometry())

    @pyqtSlot()
    def __open_in_osm(self) -> None:
        selected_items = self.__resultsTree.selectedItems()
        if len(selected_items) == 0:
            return

        item = selected_items[0]
        if item.type() == TagItemType:
            item = item.parent()
        if not item or item.type() != FeatureItemType:
            return

        osm_element: Optional[OsmElement] = item.data(
            0, Qt.ItemDataRole.UserRole
        )

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
        if item.type() == TagItemType:
            item = item.parent()
        if not item or item.type() != FeatureItemType:
            return

        osm_element: Optional[OsmElement] = item.data(
            0, Qt.ItemDataRole.UserRole
        )
        link = f"https://www.openstreetmap.org/{osm_element.type()}/{osm_element.osm_id}"
        data = QByteArray(link.encode())
        set_clipboard_data("text/plain", data, link)
