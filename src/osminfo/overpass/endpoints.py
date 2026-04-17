# NextGIS OSMInfo Plugin
# Copyright (C) 2026  NextGIS
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or any
# later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License along
# with this program; if not, see <https://www.gnu.org/licenses/>.

from dataclasses import dataclass
from enum import Enum
from typing import Optional

from qgis.core import QgsApplication


@dataclass()
class OverpassEndpointInfo:
    service_id: str
    name: str
    data_coverage: str
    url: str
    project_url: Optional[str] = None
    overpass_turbo_url: Optional[str] = None
    contact: Optional[str] = None
    contact_url: Optional[str] = None
    usage_policy: Optional[str] = None
    note: Optional[str] = None


class OverpassEndpoint(Enum):
    # fmt: off
    MAIN = OverpassEndpointInfo(
        service_id="main",
        name=QgsApplication.translate(
            "OverpassEndpoint",
            "Main Overpass API instance"
        ),
        data_coverage=QgsApplication.translate(
            "OverpassEndpoint",
            "Global"
        ),
        url="https://overpass-api.de/api/interpreter",
        project_url="https://overpass-api.de/",
        usage_policy=QgsApplication.translate(
            "OverpassEndpoint",
            "You can safely assume that you don't disturb other users "
            "when you do less than 10,000 queries per day and "
            "download less than 1 GB data per day"
        ),
    )
    VK_MAPS = OverpassEndpointInfo(
        service_id="vk_maps",
        name=QgsApplication.translate(
            "OverpassEndpoint",
            "VK Maps Overpass API instance (Russia)"
        ),
        data_coverage=QgsApplication.translate(
            "OverpassEndpoint",
            "Global"
        ),
        url="https://maps.mail.ru/osm/tools/overpass/api/interpreter",
        overpass_turbo_url="https://maps.mail.ru/osm/tools/overpass/",
        usage_policy=QgsApplication.translate(
            "OverpassEndpoint",
            "Feel free to use our services in any project. There are "
            "currently no requests limitations and we will try to keep "
            "this approach in the future."
        ),
        note=QgsApplication.translate(
            "OverpassEndpoint",
            "Temporarily suspended from March 16, 2026"
        ),
    )
    PRIVATE_COFFEE = OverpassEndpointInfo(
        service_id="private_coffee",
        name=QgsApplication.translate(
            "OverpassEndpoint",
            "Private.coffee Overpass Instance"
        ),
        data_coverage=QgsApplication.translate(
            "OverpassEndpoint",
            "Global"
        ),
        url="https://overpass.private.coffee/api/interpreter",
        project_url="https://overpass.private.coffee/",
        overpass_turbo_url="https://turbo.overpass.private.coffee/",
        contact="support@private.coffee",
        contact_url="mailto:support@private.coffee",
        usage_policy=QgsApplication.translate(
            "OverpassEndpoint",
            "Feel free to use our service in any project, there is no rate "
            "limit in place. Please notify us in advance if you intend to use "
            "our service in a large scale project."
        ),
        note=QgsApplication.translate(
            "OverpassEndpoint",
            "Previously known as overpass.kumi.systems."
        ),
    )
    SWISS = OverpassEndpointInfo(
        service_id="swiss",
        name=QgsApplication.translate(
            "OverpassEndpoint",
            "Swiss Overpass API instance"
        ),
        data_coverage=QgsApplication.translate(
            "OverpassEndpoint",
            "Switzerland"
        ),
        url="https://overpass.osm.ch/api/interpreter",
        project_url="https://overpass.osm.ch/",
        usage_policy=QgsApplication.translate(
            "OverpassEndpoint",
            "Ask Datendelphin"
        ),
        contact="Datendelphin",
        contact_url="https://wiki.openstreetmap.org/wiki/User:Datendelphin",
    )
    ATOWNSEND_UK = OverpassEndpointInfo(
        service_id="atownsend_uk",
        name=QgsApplication.translate(
            "OverpassEndpoint",
            "Britain and Ireland Overpass Instance"
        ),
        url="https://overpass.atownsend.org.uk/api/interpreter",
        data_coverage=QgsApplication.translate(
            "OverpassEndpoint",
            "Britain and Ireland"
        ),
        project_url="https://overpass.atownsend.org.uk/",
        contact="SomeoneElse",
        contact_url="https://www.openstreetmap.org/user/SomeoneElse",
        usage_policy=QgsApplication.translate(
            "OverpassEndpoint",
            "See the project page for usage policy and privacy policy."
        ),
        note=QgsApplication.translate(
            "OverpassEndpoint",
            "IPv6 only. No metadata, no attic data."
        ),
    )
    MAPRVA = OverpassEndpointInfo(
        service_id="maprva",
        name=QgsApplication.translate(
            "OverpassEndpoint",
            "MapRVA Overpass server"
        ),
        url="https://overpass.maprva.org/api/interpreter",
        data_coverage=QgsApplication.translate(
            "OverpassEndpoint",
            "Virginia, USA"
        ),
        project_url="https://ultra.maprva.org/",
        contact="Jacobwhall",
        contact_url="https://wiki.openstreetmap.org/wiki/User:Jacobwhall",
        note=QgsApplication.translate(
            "OverpassEndpoint",
            "Run by Jacobwhall for MapRVA."
        ),
    )
    ETHIOPIA = OverpassEndpointInfo(
        service_id="ethiopia",
        name=QgsApplication.translate(
            "OverpassEndpoint",
            "Ethiopia Overpass Server"
        ),
        url="https://ethiopia.overpass.openplaceguide.org/api/interpreter",
        data_coverage=QgsApplication.translate(
            "OverpassEndpoint",
            "Ethiopia"
        ),
        project_url="https://openplaceguide.org/",
        contact="Alexm",
        contact_url="https://wiki.openstreetmap.org/wiki/User:Alexm",
        note=QgsApplication.translate(
            "OverpassEndpoint",
            "Run by Alexm for Bandira_Addis_Map / OpenPlaceGuide."
        ),
    )
    CUSTOM = OverpassEndpointInfo(
        service_id="custom",
        name=QgsApplication.translate(
            "OverpassEndpoint",
            "Custom Overpass API instance"
        ),
        url="",
        data_coverage=QgsApplication.translate(
            "OverpassEndpoint",
            "Unknown"
        ),
    )
    # fmt: on

    @classmethod
    def from_service_id(
        cls, service_id: Optional[str]
    ) -> Optional["OverpassEndpoint"]:
        if service_id is None:
            return None

        for endpoint in cls:
            if endpoint.value.service_id == service_id:
                return endpoint

        return None

    @classmethod
    def from_url(cls, url: Optional[str]) -> Optional["OverpassEndpoint"]:
        normalized_url = cls.normalize_url(url)
        if normalized_url is None:
            return None

        for endpoint in cls:
            endpoint_url = cls.normalize_url(endpoint.value.url)
            if endpoint_url == normalized_url:
                return endpoint

        return None

    @staticmethod
    def normalize_url(url: Optional[str]) -> Optional[str]:
        if url is None:
            return None

        normalized_url = url.strip().rstrip("/")
        if len(normalized_url) == 0:
            return None

        return normalized_url
