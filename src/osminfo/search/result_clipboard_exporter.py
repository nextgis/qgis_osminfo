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

import json
from typing import Dict, List, Optional, Sequence

from qgis.core import Qgis, QgsGeometry, QgsSettings
from qgis.PyQt.QtCore import QByteArray, QObject

from osminfo.osminfo_interface import OsmInfoInterface
from osminfo.search.result_selection import OsmResultSelectionItem
from osminfo.ui.utils import set_clipboard_data

COPY_FORMAT_ATTRIBUTES_ONLY = "AttributesOnly"
COPY_FORMAT_ATTRIBUTES_WITH_WKT = "AttributesWithWKT"
COPY_FORMAT_ATTRIBUTES_WITH_WKB = "AttributesWithWKB"
COPY_FORMAT_GEOJSON = "GeoJSON"


class OsmResultClipboardExporter(QObject):
    def __init__(self, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)

    def copy_to_clipboard(
        self,
        items: Sequence[OsmResultSelectionItem],
    ) -> bool:
        if len(items) == 0:
            return False

        copy_format = self._copy_format()
        if copy_format == COPY_FORMAT_GEOJSON:
            return self._copy_geojson(items)

        field_names = self._field_names(items)
        geometry_encoding = self._geometry_encoding(copy_format)
        if len(field_names) == 0 and geometry_encoding is None:
            self._show_message(
                self.tr("Selected features have no attributes to copy."),
            )
            return False

        return self._copy_tabular(items, field_names, geometry_encoding)

    def _copy_geojson(
        self,
        items: Sequence[OsmResultSelectionItem],
    ) -> bool:
        feature_collection = {
            "type": "FeatureCollection",
            "features": [self._geojson_feature(item) for item in items],
        }
        payload = json.dumps(feature_collection, ensure_ascii=False)
        set_clipboard_data(
            "application/geo+json",
            QByteArray(payload.encode("utf-8")),
            payload,
        )
        return True

    def _copy_tabular(
        self,
        items: Sequence[OsmResultSelectionItem],
        field_names: Sequence[str],
        geometry_encoding: Optional[str],
    ) -> bool:
        header_fields = []
        if geometry_encoding == COPY_FORMAT_ATTRIBUTES_WITH_WKT:
            header_fields.append("wkt_geom")
        elif geometry_encoding == COPY_FORMAT_ATTRIBUTES_WITH_WKB:
            header_fields.append("wkb_geom")

        header_fields.extend(field_names)

        rows = ["\t".join(header_fields)]
        for item in items:
            row_values = []
            if geometry_encoding is not None:
                row_values.append(
                    self._geometry_text(
                        item.element.qgs_geometry(),
                        geometry_encoding,
                    )
                )
            row_values.extend(
                self._tabular_value(item.element.tags.get(field_name))
                for field_name in field_names
            )
            rows.append("\t".join(row_values))

        payload = "\n".join(rows)
        set_clipboard_data(
            "text/plain",
            QByteArray(payload.encode("utf-8")),
            payload,
        )
        return True

    def _copy_format(self) -> str:
        copy_format = QgsSettings().value(
            "qgis/copyFeatureFormat",
            defaultValue=COPY_FORMAT_ATTRIBUTES_WITH_WKT,
        )
        if copy_format in (
            COPY_FORMAT_ATTRIBUTES_ONLY,
            COPY_FORMAT_ATTRIBUTES_WITH_WKT,
            COPY_FORMAT_ATTRIBUTES_WITH_WKB,
            COPY_FORMAT_GEOJSON,
        ):
            return str(copy_format)

        return COPY_FORMAT_ATTRIBUTES_WITH_WKT

    def _geometry_encoding(self, copy_format: str) -> Optional[str]:
        if copy_format == COPY_FORMAT_ATTRIBUTES_WITH_WKT:
            return COPY_FORMAT_ATTRIBUTES_WITH_WKT

        if copy_format == COPY_FORMAT_ATTRIBUTES_WITH_WKB:
            return COPY_FORMAT_ATTRIBUTES_WITH_WKB

        return None

    def _field_names(
        self,
        items: Sequence[OsmResultSelectionItem],
    ) -> List[str]:
        field_names: List[str] = []
        for item in items:
            for field_name in item.element.tags:
                if field_name in field_names:
                    continue

                field_names.append(field_name)

        return field_names

    def _geojson_feature(
        self,
        item: OsmResultSelectionItem,
    ) -> Dict[str, object]:
        geometry = item.element.qgs_geometry()
        geometry_object = None
        if geometry is not None:
            geometry_object = json.loads(geometry.asJson())

        return {
            "type": "Feature",
            "id": (f"{item.element.element_type.value}/{item.element.osm_id}"),
            "properties": dict(item.element.tags),
            "geometry": geometry_object,
        }

    def _geometry_text(
        self,
        geometry: Optional[QgsGeometry],
        geometry_encoding: str,
    ) -> str:
        if geometry is None:
            return ""

        if geometry_encoding == COPY_FORMAT_ATTRIBUTES_WITH_WKB:
            wkb_geometry = geometry.asWkb()
            if isinstance(wkb_geometry, QByteArray):
                wkb_geometry = wkb_geometry.data()
            return wkb_geometry.hex()

        return geometry.asWkt()

    def _tabular_value(self, value: Optional[str]) -> str:
        if value is None:
            return ""

        normalized_value = str(value)
        normalized_value = normalized_value.replace("\t", " ")
        normalized_value = normalized_value.replace("\r", " ")
        normalized_value = normalized_value.replace("\n", " ")
        return normalized_value

    def _show_message(self, message: str) -> None:
        notifier = OsmInfoInterface.instance().notifier
        notifier.display_message(message, level=Qgis.MessageLevel.Warning)
