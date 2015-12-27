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

from PyQt4.QtCore import *
from PyQt4.QtGui import *

from qgis.core import *

from osminfo_worker import Worker
from rb_result_renderer import RubberBandResultRenderer

FeatureItemType = 1001
TagItemType = 1002

class ResultsDialog(QDockWidget):
    def __init__(self, title, result_render, parent=None):
        self.__rb = result_render
        QDockWidget.__init__(self, title, parent)
        self.__mainWidget = QWidget()

        self.__layout = QVBoxLayout(self.__mainWidget)

        self.__resultsTree = QTreeWidget(self)
        self.__resultsTree.setMinimumSize(350, 250)
        self.__resultsTree.setColumnCount(2)
        self.__resultsTree.setHeaderLabels(['Feature/Key', 'Value'])
        self.__resultsTree.header().setResizeMode(QHeaderView.ResizeToContents)
        self.__resultsTree.header().setStretchLastSection(False)
        self.__resultsTree.itemClicked.connect(self.itemClicked)
        self.__layout.addWidget(self.__resultsTree)
        self.__resultsTree.clear()

        self.setWidget(self.__mainWidget)

    def getInfo(self, xx, yy):
        self.__resultsTree.clear()
        self.__resultsTree.addTopLevelItem(QTreeWidgetItem(["Loading...."]))

        worker = Worker(xx, yy)
        thread = QThread(self)
        worker.moveToThread(thread)
        worker.gotData.connect(self.showData)
        worker.gotError.connect(self.showError)
        thread.started.connect(worker.run)
        thread.start()

        self.thread = thread
        self.worker = worker

    def showError(self, msg):
        self.__resultsTree.clear()
        self.__resultsTree.addTopLevelItem(QTreeWidgetItem([msg]))

    def showData(self, l1, l2):
        self.__resultsTree.clear()

        near = QTreeWidgetItem(['Nearby features'])
        self.__resultsTree.addTopLevelItem(near)
        self.__resultsTree.expandItem(near)

        index = 1

        for element in l1:
            # print element
            try:
                elementTags = element[u'tags']
                elementTitle = elementTags.get(u'name')
                if not elementTitle:
                    if 'building' in elementTags.keys():
                        if 'addr:street' in elementTags.keys() and 'addr:housenumber' in elementTags.keys():
                            elementTitle = elementTags['addr:street'] + ', ' + elementTags['addr:housenumber']
                        else:
                            elementTitle = 'building'
                    elif 'highway' in elementTags.keys():
                        elementTitle = 'highway:' + elementTags['highway']
                    elif 'amenity' in elementTags.keys():
                        elementTitle = elementTags['amenity']
                    else:
                        elementTitle = elementTags[0]
                elementItem = QTreeWidgetItem(near, [elementTitle], FeatureItemType)
                elementItem.setData(0, Qt.UserRole, element)
                for tag in sorted(elementTags.items()):
                    elementItem.addChild(QTreeWidgetItem(tag, TagItemType))

                self.__resultsTree.addTopLevelItem(elementItem)
                #self.__resultsTree.expandItem(elementItem)
                index += 1
            except Exception as e:
                print e

        isin = QTreeWidgetItem(['Is inside'])
        self.__resultsTree.addTopLevelItem(isin)
        self.__resultsTree.expandItem(isin)

        for element in l2:
            # print element
            try:
                elementTags = element[u'tags']
                elementTitle = elementTags.get(u'name', str(index))
                elementItem = QTreeWidgetItem(isin, [elementTitle], FeatureItemType)
                elementItem.setData(0, Qt.UserRole, element)
                for tag in sorted(elementTags.items()):
                    elementItem.addChild(QTreeWidgetItem(tag, TagItemType))

                self.__resultsTree.addTopLevelItem(elementItem)
                index += 1
            except Exception as e:
                print e

    def itemClicked(self, item, column):
        # clear old highlights
        self.__rb.clear_feature()
        # set new
        if item.type() == TagItemType:
            item = item.parent()
        if item and item.type() == FeatureItemType:
            element = item.data(0, Qt.UserRole)
            if element:
                if element['type'] == 'node':
                    geom = QgsGeometry.fromPoint(QgsPoint(element['lon'], element['lat']))
                if element['type'] == 'way':
                    geom = QgsGeometry.fromPolyline([QgsPoint(g['lon'], g['lat']) for g in element['geometry'] if g!='null'])
                if element['type'] == 'relation':
                    return
                self.__rb.show_feature(geom)