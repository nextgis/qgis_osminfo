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
from urllib.parse import urlparse

from qgis.core import QgsSettings
from qgis.PyQt.QtCore import QSettings

from osminfo.overpass.endpoints import OverpassEndpoint


class OsmInfoSettings:
    """Convenience class for working with plugin settings"""

    COMPANY_NAME = "NextGIS"
    PRODUCT = "OSMInfo"

    __is_updated: ClassVar[bool] = False

    __settings: QgsSettings

    def __init__(self) -> None:
        self.__settings = QgsSettings()
        self.__update_settings()

    @property
    def did_last_launch_fail(self) -> bool:
        value = self.__settings.value(
            f"{self.COMPANY_NAME}/{self.PRODUCT}/other/didLastLaunchFail",
            defaultValue=False,
            type=bool,
        )
        return value

    @did_last_launch_fail.setter
    def did_last_launch_fail(self, value: bool) -> None:
        self.__settings.setValue(
            f"{self.COMPANY_NAME}/{self.PRODUCT}/other/didLastLaunchFail",
            value,
        )

    @property
    def last_used_version(self) -> str:
        value = self.__settings.value(
            f"{self.COMPANY_NAME}/{self.PRODUCT}/other/lastUsedVersion",
            defaultValue=None,
        )
        if value is not None:
            return str(value)

        if self.__settings.contains(
            f"{self.COMPANY_NAME}/{self.PRODUCT}/distance"
        ):
            return "1.0.0"

        return "0.0.0"

    @last_used_version.setter
    def last_used_version(self, version: str) -> None:
        self.__settings.setValue(
            f"{self.COMPANY_NAME}/{self.PRODUCT}/other/lastUsedVersion",
            version,
        )

    @property
    def default_overpass_endpoint(self) -> str:
        return OverpassEndpoint.MAIN.value.service_id

    @property
    def overpass_endpoint(self) -> str:
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
    def custom_endpoint(self) -> str:
        return self.__settings.value(
            f"{self.COMPANY_NAME}/{self.PRODUCT}/customEndpoint",
            defaultValue="",
            type=str,
        )

    @custom_endpoint.setter
    def custom_endpoint(self, endpoint: str) -> None:
        self.__settings.setValue(
            f"{self.COMPANY_NAME}/{self.PRODUCT}/customEndpoint",
            endpoint,
        )

    @property
    def overpass_url(self) -> str:
        return self.resolve_overpass_url(
            self.overpass_endpoint,
            self.custom_endpoint,
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
            defaultValue=60,
            type=int,
        )

    @timeout.setter
    def timeout(self, timeout: int) -> None:
        self.__settings.setValue(
            f"{self.COMPANY_NAME}/{self.PRODUCT}/timeout", timeout
        )

    @property
    def is_timeout_enabled(self) -> bool:
        return self.__settings.value(
            f"{self.COMPANY_NAME}/{self.PRODUCT}/timeoutEnabled",
            defaultValue=False,
            type=bool,
        )

    @is_timeout_enabled.setter
    def is_timeout_enabled(self, value: bool) -> None:
        self.__settings.setValue(
            f"{self.COMPANY_NAME}/{self.PRODUCT}/timeoutEnabled", value
        )

    @property
    def max_size_megabytes(self) -> int:
        return self.__settings.value(
            f"{self.COMPANY_NAME}/{self.PRODUCT}/maxSizeMegabytes",
            defaultValue=512,
            type=int,
        )

    @max_size_megabytes.setter
    def max_size_megabytes(self, value: int) -> None:
        self.__settings.setValue(
            f"{self.COMPANY_NAME}/{self.PRODUCT}/maxSizeMegabytes", value
        )

    @property
    def is_max_size_enabled(self) -> bool:
        return self.__settings.value(
            f"{self.COMPANY_NAME}/{self.PRODUCT}/maxSizeEnabled",
            defaultValue=False,
            type=bool,
        )

    @is_max_size_enabled.setter
    def is_max_size_enabled(self, value: bool) -> None:
        self.__settings.setValue(
            f"{self.COMPANY_NAME}/{self.PRODUCT}/maxSizeEnabled", value
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
    def fetch_enclosing(self) -> bool:
        result = self.__settings.value(
            f"{self.COMPANY_NAME}/{self.PRODUCT}/fetchEnclosing",
            defaultValue=True,
            type=bool,
        )
        return result

    @fetch_enclosing.setter
    def fetch_enclosing(self, value: bool) -> None:
        self.__settings.setValue(
            f"{self.COMPANY_NAME}/{self.PRODUCT}/fetchEnclosing", value
        )

    @property
    def show_all_found_features(self) -> bool:
        result = self.__settings.value(
            f"{self.COMPANY_NAME}/{self.PRODUCT}/renderer/showAllFoundFeatures",
            defaultValue=False,
            type=bool,
        )
        return result

    @show_all_found_features.setter
    def show_all_found_features(self, value: bool) -> None:
        self.__settings.setValue(
            f"{self.COMPANY_NAME}/{self.PRODUCT}/renderer/showAllFoundFeatures",
            value,
        )

    @property
    def show_small_features_as_points(self) -> bool:
        result = self.__settings.value(
            (
                f"{self.COMPANY_NAME}/{self.PRODUCT}/renderer"
                "/showSmallFeaturesAsPoints"
            ),
            defaultValue=True,
            type=bool,
        )
        return result

    @show_small_features_as_points.setter
    def show_small_features_as_points(self, value: bool) -> None:
        self.__settings.setValue(
            (
                f"{self.COMPANY_NAME}/{self.PRODUCT}/renderer"
                "/showSmallFeaturesAsPoints"
            ),
            value,
        )

    @classmethod
    def __update_settings(cls):
        if cls.__is_updated:
            return

        qgs_settings = QgsSettings()
        cls.__migrate_from_qsettings(qgs_settings)
        cls.__rename_settings(qgs_settings)
        cls.__migrate_overpass_endpoint(qgs_settings)

        cls.__is_updated = True

    @classmethod
    def __migrate_from_qsettings(cls, qgs_settings: QgsSettings):
        """Migrate from QSettings to QgsSettings"""

        old_settings = QSettings(cls.COMPANY_NAME, cls.PRODUCT)
        if platform.system() != "Darwin" and len(old_settings.allKeys()) == 0:
            return

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
            # qgs_settings.setValue(
            #     f"{cls.COMPANY_NAME}/{cls.PRODUCT}/timeoutEnabled", True
            # )
            old_settings.remove("timeout")

    @classmethod
    def __rename_settings(cls, qgs_settings: QgsSettings):
        fetch_surrounding = qgs_settings.value(
            f"{cls.COMPANY_NAME}/{cls.PRODUCT}/fetchSurrounding"
        )
        if fetch_surrounding is not None:
            qgs_settings.setValue(
                f"{cls.COMPANY_NAME}/{cls.PRODUCT}/fetchEnclosing",
                fetch_surrounding,
            )

    @classmethod
    def __migrate_overpass_endpoint(cls, qgs_settings: QgsSettings) -> None:
        endpoint_key = f"{cls.COMPANY_NAME}/{cls.PRODUCT}/overpassEndoint"
        custom_endpoint_key = (
            f"{cls.COMPANY_NAME}/{cls.PRODUCT}/customEndpoint"
        )
        stored_endpoint = qgs_settings.value(endpoint_key, type=str)
        if stored_endpoint is None:
            return

        if OverpassEndpoint.from_service_id(stored_endpoint) is not None:
            return

        matched_endpoint = OverpassEndpoint.from_url(stored_endpoint)
        if matched_endpoint is not None:
            qgs_settings.setValue(
                endpoint_key,
                matched_endpoint.value.service_id,
            )
            return

        normalized_url = OverpassEndpoint.normalize_url(stored_endpoint)
        if normalized_url is None:
            return

        parsed_url = urlparse(normalized_url)
        if not parsed_url.scheme or not parsed_url.netloc:
            qgs_settings.remove(endpoint_key)
            return

        qgs_settings.setValue(
            endpoint_key,
            OverpassEndpoint.CUSTOM.value.service_id,
        )
        qgs_settings.setValue(custom_endpoint_key, normalized_url)

    @classmethod
    def resolve_overpass_url(
        cls,
        service_id: Optional[str],
        custom_endpoint: Optional[str],
    ) -> str:
        endpoint = OverpassEndpoint.from_service_id(service_id)
        if endpoint is None:
            endpoint = OverpassEndpoint.MAIN

        if endpoint == OverpassEndpoint.CUSTOM:
            return OverpassEndpoint.normalize_url(custom_endpoint) or ""

        return endpoint.value.url
