from dataclasses import dataclass
from enum import Enum


@dataclass()
class EndpointInfo:
    service_id: str
    name: str
    url: str
    is_regional: bool


class OverpassEndpoint(Enum):
    MAIN = EndpointInfo(
        service_id="main",
        name="Main Overpass API instance",
        url="https://overpass-api.de/api/interpreter",
        is_regional=False,
    )
    VK_MAPS = EndpointInfo(
        service_id="vk_maps",
        name="VK Maps Overpass API instance (Russia)",
        url="https://maps.mail.ru/osm/tools/overpass/api/interpreter",
        is_regional=False,
    )
    PRIVATE_COFFEE = EndpointInfo(
        service_id="private_coffee",
        name="Private.coffee Overpass Instance",
        url="https://overpass.private.coffee/api/interpreter",
        is_regional=False,
    )
    SWISS = EndpointInfo(
        service_id="swiss",
        name="Swiss Overpass API instance",
        url="https://overpass.osm.ch/api/interpreter",
        is_regional=True,
    )
    BRITAIN_IRELAND = EndpointInfo(
        service_id="atownsend_uk",
        name="Britain and Ireland Overpass Instance",
        url="https://overpass.atownsend.org.uk/api/",
        is_regional=True,
    )
    MAPRVA = EndpointInfo(
        service_id="maprva",
        name="MapRVA Overpass server",
        url="https://overpass.maprva.org/api/interpreter",
        is_regional=True,
    )
    ETHIOPIA = EndpointInfo(
        service_id="ethiopia",
        name="Ethiopia Overpass Server",
        url="https://ethiopia.overpass.openplaceguide.org/api/interpreter",
        is_regional=True,
    )
