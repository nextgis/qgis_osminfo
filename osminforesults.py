# -*- coding: utf-8 -*-
#******************************************************************************
#
# OSMInfo
# ---------------------------------------------------------
# This plugin takes coordinates of a mouse click and gets information about all 
# objects from this point from OSM using Overpass API.
#
# Author:   Maxim Dubinin, sim@gis-lab.info
# Author:   Alexander Lisovenko, alexander.lisovenko@nextgis.ru
# *****************************************************************************
# Copyright (c) 2012-2015. NextGIS, info@nextgis.com
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
#******************************************************************************
import json

from PyQt4.QtCore import *
from PyQt4.QtGui import *
from PyQt4.QtNetwork import QNetworkRequest
from qgis.core import *
from qgis.gui import QgsMessageBar
from qgis.utils import iface

from osminfo_worker import Worker
from osmelements import *

FeatureItemType = 1001
TagItemType = 1002


class ResultsDialog(QDockWidget):
    def __init__(self, title, result_render, parent=None):
        self.__rb = result_render
        self.__selected_id = None
        self.__selected_geom = None
        self.__rel_reply = None
        self.worker = None
        QDockWidget.__init__(self, title, parent)
        self.__mainWidget = QWidget()

        self.__layout = QVBoxLayout(self.__mainWidget)

        self.__resultsTree = QTreeWidget(self)
        self.__resultsTree.setContextMenuPolicy(Qt.CustomContextMenu)
        self.__resultsTree.customContextMenuRequested.connect(self.openMenu)

        self.__resultsTree.setMinimumSize(350, 250)
        self.__resultsTree.setColumnCount(2)
        self.__resultsTree.setHeaderLabels([self.tr('Feature/Key'), self.tr('Value')])
        self.__resultsTree.header().setResizeMode(QHeaderView.ResizeToContents)
        self.__resultsTree.header().setStretchLastSection(False)
        self.__resultsTree.itemSelectionChanged.connect(self.selItemChanged)
        self.__layout.addWidget(self.__resultsTree)
        self.__resultsTree.clear()

        self.setWidget(self.__mainWidget)

        overrideLocale = QSettings().value('locale/overrideFlag', False, type=bool)
        if not overrideLocale:
            self.qgisLocale = QLocale.system().name()[:2]
        else:
            self.qgisLocale = QSettings().value('locale/userLocale', '', type=unicode)[:2]

    def openMenu(self, position):                
        selected_items = self.__resultsTree.selectedItems()
        if len(selected_items) > 0 and selected_items[0].type() in [TagItemType, FeatureItemType]:
            menu = QMenu()
            
            actionZoom = QAction(QIcon(':/plugins/osminfo/icons/zoom2feature.png'), self.tr('Zoom to feature'), self)
            menu.addAction(actionZoom)
            actionZoom.setStatusTip(self.tr('Zoom to selected item'))
            actionZoom.triggered.connect(self.zoom2feature)
            
            actionMove2NewTempLayer = QAction(QIcon(':/images/themes/default/mActionCreateMemory.svg'), self.tr('Save as temporary layer'), self)
            menu.addAction(actionMove2NewTempLayer)
            actionMove2NewTempLayer.setStatusTip(self.tr('Zoom to selected item'))
            actionMove2NewTempLayer.triggered.connect(self.move2NewTempLayer)

            menu.exec_(self.__resultsTree.viewport().mapToGlobal(position))
    
    def zoom2feature(self):
        selected_items = self.__resultsTree.selectedItems()
        if len(selected_items) > 0:
            item = selected_items[0]
            # if selected tag - use parent
            if item.type() == TagItemType:
                item = item.parent()
            if item and item.type() == FeatureItemType:
                osm_element = item.data(0, Qt.UserRole)
                geom = osm_element.asQgisGeometry()[0]
                self.__rb.zoom_to_bbox(geom.boundingBox())

    def move2NewTempLayer(self):
        selected_items = self.__resultsTree.selectedItems()
        if len(selected_items) > 0:
            item = selected_items[0]
            # if selected tag - use parent
            if item.type() == TagItemType:
                item = item.parent()
            if item and item.type() == FeatureItemType:
                osm_element = item.data(0, Qt.UserRole)

                # dst_crs = iface.mapCanvas().mapSettings().destinationCrs().authid()
                if osm_element is None:
                    iface.messageBar().pushMessage(
                        "OSM Info",
                        "Cann't parse OSM Element.",
                        QgsMessageBar.WARNING,
                        2
                    )
                    return

                geoms = osm_element.asQgisGeometry()
                for geom in geoms:
                    if geom is None:
                        geom = self.__selected_geom
                    if geom.type() == QGis.Polygon:
                        geom_type = "Polygon"
                    elif geom.type() == QGis.Line:
                        geom_type = "LineString"
                    elif geom.type() == QGis.Point:
                        geom_type = "Point"
                    else:
                        return

                    geom_type = "Multi"*geom.isMultipart() + geom_type 

                    vl = QgsVectorLayer(
                        "%s?crs=EPSG:4326" % (geom_type, ),
                        item.data(0, Qt.DisplayRole),
                        "memory"
                    )

                    pr = vl.dataProvider()

                    # add fields
                    pr.addAttributes([QgsField(k, QVariant.String) for k in osm_element.tags])
                    vl.updateFields()

                    # add a feature
                    fet = QgsFeature()
                    fet.setGeometry(geom)
                    fet.setAttributes(osm_element.tags.values())
                    pr.addFeatures([fet])
                    
                    QgsMapLayerRegistry.instance().addMapLayer(vl)

    def getInfo(self, xx, yy):
        self.__resultsTree.clear()
        self.__resultsTree.addTopLevelItem(QTreeWidgetItem([self.tr('Loading....')]))

        if self.worker:
            self.worker.gotData.disconnect(self.showData)
            self.worker.gotError.disconnect(self.showError)
            self.worker.quit()
            self.worker.deleteLater()

        worker = Worker(xx, yy)
        worker.gotData.connect(self.showData)
        worker.gotError.connect(self.showError)
        worker.start()

        self.worker = worker

    def showError(self, msg):
        self.__resultsTree.clear()
        self.__resultsTree.addTopLevelItem(QTreeWidgetItem([msg]))

    def showData(self, l1, l2):
        self.__resultsTree.clear()

        near = QTreeWidgetItem([self.tr('Nearby features')])
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
                        FeatureItemType
                    )
                    elementItem.setData(0, Qt.UserRole, osm_element)

                    for tag in sorted(osm_element.tags.items()):
                        elementItem.addChild(QTreeWidgetItem(tag, TagItemType))

                    self.__resultsTree.addTopLevelItem(elementItem)

                    # qApp.processEvents()
            except Exception as e:
                QgsMessageLog.logMessage(
                    self.tr('Element process error: %s. Element: %s.') % (unicode(e), unicode(element)),
                    self.tr('OSMInfo'),
                    QgsMessageLog.CRITICAL
                )
                

        isin = QTreeWidgetItem([self.tr('Is inside')])
        self.__resultsTree.addTopLevelItem(isin)
        self.__resultsTree.expandItem(isin)

        l2Sorted = sorted(
            l2,
            key=lambda element: QgsGeometry().fromRect(
                QgsRectangle(
                    element['bounds']['minlon'],
                    element['bounds']['minlat'],
                    element['bounds']['maxlon'],
                    element['bounds']['maxlat'])
            ).area()
        )

        for element in l2Sorted:
            try:
                osm_element = parseOsmElement(element)
                if osm_element is not None:
                    elementItem = QTreeWidgetItem(isin, [osm_element.title(self.qgisLocale)], FeatureItemType)
                    elementItem.setData(0, Qt.UserRole, osm_element)
                    for tag in sorted(osm_element.tags.items()):
                        elementItem.addChild(QTreeWidgetItem(tag, TagItemType))

                    self.__resultsTree.addTopLevelItem(elementItem)
                    # qApp.processEvents()
            except Exception as e:
                QgsMessageLog.logMessage(
                    self.tr('Element process error: %s. Element: %s.') % (unicode(e), unicode(element)),
                    self.tr('OSMInfo'),
                    QgsMessageLog.CRITICAL
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
            osm_element = item.data(0, Qt.UserRole)

            self.__rb.show_feature(osm_element.asQgisGeometry()[0])
