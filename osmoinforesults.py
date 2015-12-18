# -*- coding: utf-8 -*-
#******************************************************************************
#
# OSMInfo
# ---------------------------------------------------------
# This plugin takes coordinates of a mouse click and gets information about all 
# objects from this point from OSM using Overpass API.
#
# Copyright (C) 2013 Maxim Dubinin (sim@gis-lab.info), NextGIS (info@nextgis.org)
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


class ResultsDialog(QDialog):
    def __init__(self, title, elements, parent=None):
        QDialog.__init__(self, parent)

        self.setWindowTitle(title)

        self.__layout = QVBoxLayout(self)

        self.__resultsTree = QTreeWidget(self)
        self.__resultsTree.setColumnCount(2)
        self.__resultsTree.setHeaderLabels(["", ""])
        self.__layout.addWidget(self.__resultsTree)

        self.__resultsTree.clear()

        index = 1
        for element in elements:
            # print element
            try:
                elementTags = element[u'tags']

                elementTitle = elementTags.get(u'name', str(index))
                
                elementItem = QTreeWidgetItem([elementTitle])

                for tag in elementTags.items():
                    elementItem.addChild(QTreeWidgetItem(tag))

                self.__resultsTree.addTopLevelItem(elementItem)

                index += 1
            except Exception as e:
                print e
