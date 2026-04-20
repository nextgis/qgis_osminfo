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
from typing import Optional, Tuple

from qgis.core import QgsRectangle

from osminfo.openstreetmap.models import OsmElement
from osminfo.openstreetmap.tag2link import TagLink


@dataclass(frozen=True)
class OsmResultSelectionItem:
    element: OsmElement


@dataclass(frozen=True)
class OsmResultSelection:
    items: Tuple[OsmResultSelectionItem, ...] = tuple()
    clicked_item: Optional[OsmResultSelectionItem] = None
    clicked_tag_links: Tuple[TagLink, ...] = tuple()
    selected_row_count: int = 0

    @property
    def has_elements(self) -> bool:
        return len(self.items) > 0

    @property
    def has_multiple_elements(self) -> bool:
        return len(self.items) > 1

    @property
    def geometry_items(self) -> Tuple[OsmResultSelectionItem, ...]:
        return tuple(
            item
            for item in self.items
            if item.element.qgs_geometry() is not None
        )

    @property
    def single_element(self) -> Optional[OsmElement]:
        if len(self.items) != 1:
            return None

        return self.items[0].element

    @property
    def combined_bbox(self) -> Optional[QgsRectangle]:
        combined_bbox: Optional[QgsRectangle] = None
        for item in self.items:
            bbox = item.element.bounding_box()
            if bbox is None:
                continue

            if combined_bbox is None:
                combined_bbox = QgsRectangle(bbox)
                continue

            combined_bbox.combineExtentWith(bbox)

        return combined_bbox
