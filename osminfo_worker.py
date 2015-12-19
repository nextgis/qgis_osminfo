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
from qgis.gui import *

import requests
from osminforesults import ResultsDialog

class ResultsTree(QtCore.QObject):

    progressChanged = QtCore.pyqtSignal(int)

    def __init__(self, iface, point):

    def run(self):
        xx = str(point.x()) 
        yy = str(point.y())

        url = 'http://overpass-api.de/api/interpreter'

        #around request
        dist = 20
        request = '[timeout:30][out:json];(node(around:%s,%s,%s);way(around:%s,%s,%s));out tags geom;relation(around:%s,%s,%s);'%(dist,yy,xx,dist,yy,xx,dist,yy,xx)

        #QMessageBox.warning(self.iface.mainWindow(),'Query',request)
        rr = requests.post(url, data = request)
        l1 = rr.json()['elements']
           
        #is_in request
        request = '[timeout:30][out:json];is_in(%s,%s)->.a;way(pivot.a);out tags geom;relation(pivot.a);out tags bb;'%(yy,xx)

        rr = requests.post(url, data = request)
        l2 = rr.json()['elements']

        dlg = ResultsDialog('Query results', l1, l2, self.iface.mainWindow())
        dlg.finished.connect(self.clearCanvas)
        dlg.exec_()

