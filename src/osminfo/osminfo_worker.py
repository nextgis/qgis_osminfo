# ******************************************************************************
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
# ******************************************************************************

import html
import json
from typing import Any, List

from qgis.core import QgsNetworkAccessManager
from qgis.PyQt.QtCore import QThread, QUrl, pyqtSignal
from qgis.PyQt.QtNetwork import QNetworkReply, QNetworkRequest

from osminfo.logging import logger
from osminfo.settings import OsmInfoSettings


class Worker(QThread):
    gotData = pyqtSignal(list, list)
    gotError = pyqtSignal(str)
    finished = pyqtSignal()

    def __init__(self, xx, yy):
        super().__init__()
        self.__xx = xx
        self.__yy = yy

    def run(self):
        xx = str(self.__xx)
        yy = str(self.__yy)
        if abs(float(xx)) > 180 or abs(float(yy)) > 90:
            self.gotError.emit(
                self.tr("Worker: %s, %s are wrong coords!") % (xx, yy)
            )
            self.finished.emit()
            return

        settings = OsmInfoSettings()
        if not settings.fetch_nearby and not settings.fetch_enclosing:
            self.gotError.emit("No object category selected in settings")
            self.finished.emit()
            return

        try:
            nearby_elements = self.__fetch_nearby(settings)
            enclosing_elements = self.__fetch_enclosing(settings)
        except Exception as error:
            self.gotError.emit(str(error))
            self.finished.emit()
            return

        self.gotData.emit(nearby_elements, enclosing_elements)
        self.finished.emit()

    def __fetch_nearby(self, settings: OsmInfoSettings) -> List[Any]:
        if not settings.fetch_nearby:
            logger.debug("Skip fetching nearby features")
            return []

        distance = settings.distance
        query = f"""
            [out:json][timeout:{settings.timeout}];
            (
                node(around:{distance},{self.__yy},{self.__xx});
                way(around:{distance},{self.__yy},{self.__xx});
                relation(around:{distance},{self.__yy},{self.__xx});
            );
            out tags geom;
        """
        logger.debug(
            f"Fetch nearby features for {self.__yy}, {self.__xx}\n"
            f"{html.escape(query)}"
        )

        return self.__fetch_from_overpass(settings, query)

    def __fetch_enclosing(self, settings: OsmInfoSettings) -> List[Any]:
        if not settings.fetch_enclosing:
            logger.debug("Skip fetching enclosing features")
            return []

        # TODO is .b really needed there? Probably this is a bug in overpass
        query = f"""
            [out:json][timeout:{settings.timeout}];
            is_in({self.__yy},{self.__xx})->.a;
            way(pivot.a)->.b;
            .b out tags geom;
            .b <;
            out geom;
            relation(pivot.a);
            out geom;
        """
        logger.debug(
            f"Fetch enclosing features for {self.__yy}, {self.__xx}\n"
            f"{html.escape(query)}"
        )

        return self.__fetch_from_overpass(settings, query)

    def __fetch_from_overpass(
        self, settings: OsmInfoSettings, query: str
    ) -> List[Any]:
        request = QNetworkRequest(QUrl(settings.overpass_endpoint))
        request.setHeader(
            QNetworkRequest.ContentTypeHeader,
            "application/x-www-form-urlencoded",
        )

        qnam = QgsNetworkAccessManager.instance()
        reply_content = qnam.blockingPost(request, str.encode(query))
        if reply_content.error() != QNetworkReply.NetworkError.NoError:
            logger.error(reply_content.errorString())
            raise RuntimeError(self.tr("Error getting data from the server"))

        try:
            json_content = json.loads(reply_content.content().data())
        except Exception as error:
            logger.exception("Parsing data error")
            raise RuntimeError(self.tr("Parsing data error")) from error

        if json_content.get("remark") is not None:
            raise RuntimeError(json_content["remark"])

        elements = json_content.get("elements", [])
        logger.debug(f"Fetched {len(elements)} elements")
        return elements
