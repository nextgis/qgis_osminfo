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


class ResultsDialog(QDockWidget):
    def __init__(self, title, parent=None):
        QDockWidget.__init__(self, title, parent)

        self.__mainWidget = QWidget()

        self.__layout = QVBoxLayout(self.__mainWidget)

        self.__resultsTree = QTreeWidget(self)
        self.__resultsTree.setMinimumSize(395, 395)
        self.__resultsTree.setColumnCount(2)
        self.__resultsTree.setHeaderLabels(['Feature/Key', 'Value'])
        self.__layout.addWidget(self.__resultsTree)
        self.__resultsTree.clear()

        self.setWidget(self.__mainWidget)

    def getInfo(self, xx, yy):
        self.__resultsTree.clear()
        self.__resultsTree.addTopLevelItem(QTreeWidgetItem(["Loading...."]))

        worker = Worker(xx, yy)
        thread = QThread(self)
        worker.moveToThread(thread)
        worker.getData.connect(self.showData)
        thread.started.connect(worker.run)
        thread.start()

        self.thread = thread
        self.worker = worker

    def showData(self, l1, l2):
        self.__resultsTree.clear()

        near = QTreeWidgetItem(['Nearby features'])
        self.__resultsTree.addTopLevelItem(near)
        self.__resultsTree.expandItem(near)
        self.__resultsTree.header().setResizeMode(QHeaderView.ResizeToContents)
        self.__resultsTree.header().setStretchLastSection(False)

        index = 1

        for element in l1:
            # print element
            try:
                elementTags = element[u'tags']
                elementTitle = elementTags.get(u'name', str(index))
                elementItem = QTreeWidgetItem(near, [elementTitle])
                for tag in sorted(elementTags.items()):
                    elementItem.addChild(QTreeWidgetItem(tag))

                self.__resultsTree.addTopLevelItem(elementItem)
                self.__resultsTree.expandItem(elementItem)
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
                elementItem = QTreeWidgetItem(isin, [elementTitle])
                for tag in sorted(elementTags.items()):
                    elementItem.addChild(QTreeWidgetItem(tag))

                self.__resultsTree.addTopLevelItem(elementItem)
                index += 1
            except Exception as e:
                print e
