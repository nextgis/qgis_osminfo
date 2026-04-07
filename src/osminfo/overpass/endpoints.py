from dataclasses import dataclass
from enum import Enum
from typing import Optional


@dataclass()
class OverpassEndpointInfo:
    service_id: str
    name: str
    url: str
    is_regional: bool


class OverpassEndpoint(Enum):
    MAIN = OverpassEndpointInfo(
        service_id="main",
        name="Main Overpass API instance",
        url="https://overpass-api.de/api/interpreter",
        is_regional=False,
    )
    VK_MAPS = OverpassEndpointInfo(
        service_id="vk_maps",
        name="VK Maps Overpass API instance (Russia)",
        url="https://maps.mail.ru/osm/tools/overpass/api/interpreter",
        is_regional=False,
    )
    PRIVATE_COFFEE = OverpassEndpointInfo(
        service_id="private_coffee",
        name="Private.coffee Overpass Instance",
        url="https://overpass.private.coffee/api/interpreter",
        is_regional=False,
    )
    SWISS = OverpassEndpointInfo(
        service_id="swiss",
        name="Swiss Overpass API instance",
        url="https://overpass.osm.ch/api/interpreter",
        is_regional=True,
    )
    ATOWNSEND_UK = OverpassEndpointInfo(
        service_id="atownsend_uk",
        name="Britain and Ireland Overpass Instance",
        url="https://overpass.atownsend.org.uk/api",
        is_regional=True,
    )
    MAPRVA = OverpassEndpointInfo(
        service_id="maprva",
        name="MapRVA Overpass server",
        url="https://overpass.maprva.org/api/interpreter",
        is_regional=True,
    )
    ETHIOPIA = OverpassEndpointInfo(
        service_id="ethiopia",
        name="Ethiopia Overpass Server",
        url="https://ethiopia.overpass.openplaceguide.org/api/interpreter",
        is_regional=True,
    )
    CUSTOM = OverpassEndpointInfo(
        service_id="custom",
        name="Custom Overpass API instance",
        url="",
        is_regional=False,
    )

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
