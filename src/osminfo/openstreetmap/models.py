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

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, Optional, Tuple, Union

from qgis.core import QgsGeometry, QgsRectangle

from osminfo.core.compat import GeometryType
from osminfo.openstreetmap.tag2link import TagLink


class OsmElementType(str, Enum):
    NODE = "node"
    WAY = "way"
    RELATION = "relation"
    CLOSED_WAY = "closed_way"


class OsmGeometryType(Enum):
    POINT = GeometryType.Point
    LINESTRING = GeometryType.Line
    POLYGON = GeometryType.Polygon
    COLLECTION = 100000


class OsmResultGroupType(str, Enum):
    SEARCH = "search"
    NEARBY = "nearby"
    ENCLOSING = "enclosing"


@dataclass(frozen=True)
class OsmBounds:
    minlon: float
    minlat: float
    maxlon: float
    maxlat: float

    @property
    def area(self) -> float:
        return abs(self.maxlon - self.minlon) * abs(self.maxlat - self.minlat)

    def to_qgs_rectangle(self) -> QgsRectangle:
        return QgsRectangle(
            self.minlon,
            self.minlat,
            self.maxlon,
            self.maxlat,
        )


@dataclass
class OsmGeometryCollection:
    points: Optional[QgsGeometry] = None
    lines: Optional[QgsGeometry] = None
    polygons: Optional[QgsGeometry] = None

    def primary_geometry(self) -> Optional[QgsGeometry]:
        for geometry in (self.polygons, self.lines, self.points):
            if geometry is None:
                continue

            return QgsGeometry(geometry)

        return None

    def geometry_type(self) -> Optional["OsmGeometryType"]:
        geometries = [
            geometry
            for geometry in (self.points, self.lines, self.polygons)
            if geometry is not None
        ]
        if len(geometries) == 0:
            return None

        if len(geometries) > 1:
            return OsmGeometryType.COLLECTION

        return osm_geometry_type_from_qgs(geometries[0])


OsmGeometry = Union[QgsGeometry, OsmGeometryCollection]


@dataclass(frozen=True)
class OsmTag:
    key: str
    value: str
    links: Tuple[TagLink, ...] = tuple()

    @property
    def has_links(self) -> bool:
        return len(self.links) > 0


@dataclass(frozen=True)
class OsmRelationRef:
    relation_id: int
    role: Optional[str] = None
    relation_tags: Dict[str, str] = field(default_factory=dict)


@dataclass
class OsmElement:
    osm_id: int
    element_type: OsmElementType
    title: str = ""
    geometry: Optional[OsmGeometry] = None
    max_scale: Optional[float] = None
    tag_items: Tuple[OsmTag, ...] = tuple()
    tags: Dict[str, str] = field(default_factory=dict)
    bounds: Optional[OsmBounds] = None
    relation_refs: Tuple[OsmRelationRef, ...] = tuple()
    relation_role: Optional[str] = None
    is_relation_member: bool = False
    is_incomplete: bool = False

    @property
    def osm_url(self) -> str:
        return (
            "https://www.openstreetmap.org/"
            f"{self.element_type.value}/{self.osm_id}"
        )

    def qgs_geometry(self) -> Optional[QgsGeometry]:
        if self.geometry is None:
            return None

        if isinstance(self.geometry, QgsGeometry):
            return QgsGeometry(self.geometry)

        return self.geometry.primary_geometry()

    def geometry_type(self) -> Optional["OsmGeometryType"]:
        if self.geometry is None:
            return None

        if isinstance(self.geometry, QgsGeometry):
            return osm_geometry_type_from_qgs(self.geometry)

        return self.geometry.geometry_type()

    def bounding_box(self) -> Optional[QgsRectangle]:
        geometry = self.qgs_geometry()
        if geometry is not None:
            return geometry.boundingBox()

        if self.bounds is None:
            return None

        return self.bounds.to_qgs_rectangle()


@dataclass(frozen=True)
class OsmResultGroup:
    group_type: OsmResultGroupType
    title: str
    elements: Tuple[OsmElement, ...] = tuple()


@dataclass(frozen=True)
class OsmResultTree:
    groups: Tuple[OsmResultGroup, ...] = tuple()

    @property
    def is_empty(self) -> bool:
        return all(len(group.elements) == 0 for group in self.groups)


def osm_geometry_type_from_qgs(
    geometry: QgsGeometry,
) -> Optional[OsmGeometryType]:
    geometry_type = geometry.type()
    if geometry_type == GeometryType.Point:
        return OsmGeometryType.POINT

    if geometry_type == GeometryType.Line:
        return OsmGeometryType.LINESTRING

    if geometry_type == GeometryType.Polygon:
        return OsmGeometryType.POLYGON

    return None
