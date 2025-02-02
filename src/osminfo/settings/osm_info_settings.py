"""
/***************************************************************************
 Common Plugins settings

 NextGIS
                             -------------------
        begin                : 2014-10-31
        git sha              : $Format:%H$
        copyright            : (C) 2014 by NextGIS
        email                : info@nextgis.com
 ***************************************************************************/

/***************************************************************************
 *                                                                         *
 *   This program is free software; you can redistribute it and/or modify  *
 *   it under the terms of the GNU General Public License as published by  *
 *   the Free Software Foundation; either version 2 of the License, or     *
 *   (at your option) any later version.                                   *
 *                                                                         *
 ***************************************************************************/
"""

import platform
from typing import ClassVar, Optional

from qgis.core import QgsSettings
from qgis.PyQt.QtCore import QSettings


class OsmInfoSettings:
    """Convenience class for working with plugin settings"""

    COMPANY_NAME = "NextGIS"
    PRODUCT = "OSMInfo"

    __is_migrated_from_qsettings: ClassVar[bool] = False

    __settings: QgsSettings

    def __init__(self) -> None:
        self.__settings = QgsSettings()
        self.__migrate_from_qsettings()

    @property
    def default_overpass_endpoint(self) -> Optional[str]:
        return "https://overpass-api.de/api/interpreter"

    @property
    def overpass_endpoint(self) -> Optional[str]:
        return self.__settings.value(
            f"{self.COMPANY_NAME}/{self.PRODUCT}/overpassEndoint",
            defaultValue=self.default_overpass_endpoint,
            type=str,
        )

    @overpass_endpoint.setter
    def overpass_endpoint(self, endpoint: str) -> None:
        self.__settings.setValue(
            f"{self.COMPANY_NAME}/{self.PRODUCT}/overpassEndoint", endpoint
        )

    @property
    def distance(self) -> int:
        return self.__settings.value(
            f"{self.COMPANY_NAME}/{self.PRODUCT}/distance",
            defaultValue=20,
            type=int,
        )

    @distance.setter
    def distance(self, distance: int) -> None:
        self.__settings.setValue(
            f"{self.COMPANY_NAME}/{self.PRODUCT}/distance", distance
        )

    @property
    def timeout(self) -> int:
        return self.__settings.value(
            f"{self.COMPANY_NAME}/{self.PRODUCT}/timeout",
            defaultValue=30,
            type=int,
        )

    @timeout.setter
    def timeout(self, timeout: int) -> None:
        self.__settings.setValue(
            f"{self.COMPANY_NAME}/{self.PRODUCT}/timeout", timeout
        )

    @property
    def is_debug_enabled(self) -> bool:
        result = self.__settings.value(
            f"{self.COMPANY_NAME}/{self.PRODUCT}/debugEnabled",
            defaultValue=False,
            type=bool,
        )
        return result

    @is_debug_enabled.setter
    def is_debug_enabled(self, value: bool) -> None:
        self.__settings.setValue(
            f"{self.COMPANY_NAME}/{self.PRODUCT}/debugEnabled", value
        )

    @property
    def fetch_nearby(self) -> bool:
        result = self.__settings.value(
            f"{self.COMPANY_NAME}/{self.PRODUCT}/fetchNearby",
            defaultValue=True,
            type=bool,
        )
        return result

    @fetch_nearby.setter
    def fetch_nearby(self, value: bool) -> None:
        self.__settings.setValue(
            f"{self.COMPANY_NAME}/{self.PRODUCT}/fetchNearby", value
        )

    @property
    def fetch_surrounding(self) -> bool:
        result = self.__settings.value(
            f"{self.COMPANY_NAME}/{self.PRODUCT}/fetchSurrounding",
            defaultValue=True,
            type=bool,
        )
        return result

    @fetch_surrounding.setter
    def fetch_surrounding(self, value: bool) -> None:
        self.__settings.setValue(
            f"{self.COMPANY_NAME}/{self.PRODUCT}/fetchSurrounding", value
        )

    @classmethod
    def __migrate_from_qsettings(cls):
        """Migrate from QSettings to QgsSettings"""
        if cls.__is_migrated_from_qsettings:
            return

        old_settings = QSettings(cls.COMPANY_NAME, cls.PRODUCT)
        if platform.system() != "Darwin" and len(old_settings.allKeys()) == 0:
            cls.__is_migrated_from_qsettings = True
            return

        qgs_settings = QgsSettings()

        old_distance = old_settings.value("distance")
        if old_distance is not None:
            qgs_settings.setValue(
                f"{cls.COMPANY_NAME}/{cls.PRODUCT}/distance", old_distance
            )
            old_settings.remove("distance")

        old_timeout = old_settings.value("timeout")
        if old_timeout is not None:
            qgs_settings.setValue(
                f"{cls.COMPANY_NAME}/{cls.PRODUCT}/timeout", old_timeout
            )
            old_settings.remove("timeout")

        cls.__is_migrated_from_qsettings = True
