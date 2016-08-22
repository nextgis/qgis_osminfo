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

from PyQt4.QtCore import pyqtSignal, QUrl, QByteArray, QEventLoop, QThread
from PyQt4.QtNetwork import QNetworkRequest, QNetworkReply
from qgis.core import QgsMessageLog, QgsNetworkAccessManager

from plugin_settings import PluginSettings


class Worker(QThread):

    gotData = pyqtSignal(list, list)
    gotError = pyqtSignal(unicode)

    def __init__(self, xx, yy):
        super(Worker, self).__init__()
        self.__xx = xx
        self.__yy = yy

    def run(self):
        xx = str(self.__xx)
        yy = str(self.__yy)

        if abs(float(xx)) > 180 or abs(float(yy)) > 90:
            QgsMessageLog.logMessage(
                self.tr('Worker: %s, %s are wrong coords!') % (xx, yy),
                self.tr('OSMInfo'),
                QgsMessageLog.INFO
            )

            self.gotError.emit(self.tr('Worker: %s, %s are wrong coords!') % (xx, yy))
            return

        url = 'http://overpass-api.de/api/interpreter'
        request = QNetworkRequest(QUrl(url))
        request.setHeader(QNetworkRequest.ContentTypeHeader, 'application/x-www-form-urlencoded');

        qnam = QgsNetworkAccessManager.instance()

        # around request
        dist = PluginSettings.distance_value()
        timeout = PluginSettings.timeout_value()

        request_data = '[timeout:%s][out:json];(node(around:%s,%s,%s);way(around:%s,%s,%s));out tags geom;relation(around:%s,%s,%s);' % (timeout, dist, yy, xx, dist, yy, xx, dist, yy, xx)
        reply1 = qnam.post(request, QByteArray(request_data))
        loop = QEventLoop()
        reply1.finished.connect(loop.quit)
        loop.exec_()
        if reply1.error() != QNetworkReply.NoError:
            reply1.deleteLater()
            self.gotError.emit(self.tr('Error getting data from the server'))
            return
        try:
            data = reply1.readAll()
            l1 = json.loads(str(data))['elements']
            reply1.deleteLater()
        except:
            self.gotError.emit(self.tr('Error parsing data'))
            return
        finally:
            reply1.deleteLater()


        request_data = '[timeout:%s][out:json];is_in(%s,%s)->.a;way(pivot.a);out tags geom;relation(pivot.a);out tags bb;' % (timeout, yy, xx)
        reply2 = qnam.post(request, QByteArray(request_data))
        loop = QEventLoop()
        reply2.finished.connect(loop.quit)
        loop.exec_()
        if reply2.error() != QNetworkReply.NoError:
            reply2.deleteLater()
            self.gotError.emit(self.tr('Error getting data from the server'))
            return
        try:
            data = reply2.readAll()
            l2 = json.loads(str(data))['elements']
        except:
            self.gotError.emit(self.tr('Error parsing data'))
            return
        finally:
            reply2.deleteLater()

        self.gotData.emit(l1, l2)
