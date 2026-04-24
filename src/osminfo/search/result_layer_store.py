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
from typing import (
    TYPE_CHECKING,
    Dict,
    Iterable,
    List,
    Optional,
    Set,
    Tuple,
    cast,
)

from qgis.core import (
    QgsCoordinateTransform,
    QgsFeature,
    QgsFeatureRequest,
    QgsGeometry,
    QgsMapLayer,
    QgsMapLayerStore,
    QgsProject,
    QgsVectorLayer,
)
from qgis.PyQt.QtCore import QObject, pyqtSlot
from qgis.utils import iface

from osminfo.core.compat import FeatureRequestFlag, GeometryType
from osminfo.openstreetmap.models import OsmElementType, OsmGeometryType

if TYPE_CHECKING:
    from qgis.gui import QgisInterface

    assert isinstance(iface, QgisInterface)

FIELD_OSM_TYPE = "osm_type"
FIELD_OSM_ID = "osm_id"
FIELD_RELATION = "relation_related"
FIELD_TAINTED = "is_tainted"
FIELD_ACTIVE = "is_active"
FIELD_MAX_SCALE = "max_scale"
RESULT_LAYER_PROPERTY = "osminfo_result_layer"


@dataclass(frozen=True)
class OsmResultLayerHit:
    element_type: OsmElementType
    osm_id: int


@dataclass(frozen=True)
class OsmResultLayerDefinition:
    geometry_type: OsmGeometryType
    geometry_name: str
    layer_name: str

    def create_layer(self) -> QgsVectorLayer:
        layer = QgsVectorLayer(
            (
                f"{self.geometry_name}?crs=EPSG:4326"
                f"&field={FIELD_OSM_TYPE}:string"
                f"&field={FIELD_OSM_ID}:long"
                f"&field={FIELD_RELATION}:integer"
                f"&field={FIELD_TAINTED}:integer"
                f"&field={FIELD_ACTIVE}:integer"
                f"&field={FIELD_MAX_SCALE}:double"
            ),
            self.layer_name,
            "memory",
        )
        layer.setCustomProperty(RESULT_LAYER_PROPERTY, 1)
        layer.setCustomProperty("skipMemoryLayersCheck", 1)
        layer.setReadOnly(True)
        return layer


class OsmPointResultLayerDefinition(OsmResultLayerDefinition):
    def __init__(self) -> None:
        super().__init__(
            geometry_type=OsmGeometryType.POINT,
            geometry_name="MultiPoint",
            layer_name="OSMInfo points",
        )


class OsmLineResultLayerDefinition(OsmResultLayerDefinition):
    def __init__(self) -> None:
        super().__init__(
            geometry_type=OsmGeometryType.LINESTRING,
            geometry_name="MultiLineString",
            layer_name="OSMInfo lines",
        )


class OsmPolygonResultLayerDefinition(OsmResultLayerDefinition):
    def __init__(self) -> None:
        super().__init__(
            geometry_type=OsmGeometryType.POLYGON,
            geometry_name="MultiPolygon",
            layer_name="OSMInfo polygons",
        )


LAYER_DEFINITIONS = (
    OsmPolygonResultLayerDefinition(),
    OsmLineResultLayerDefinition(),
    OsmPointResultLayerDefinition(),
)


class OsmResultLayerStore(QObject):
    def __init__(self, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self._layers: Dict[OsmGeometryType, QgsVectorLayer] = {}
        self._layer_store = QgsMapLayerStore(self)
        self._is_updating = False
        self._is_visible = True
        self._show_all_features = True
        self._is_centroid_rendering_enabled = True

        map_canvas = iface.mapCanvas()
        map_canvas.layersChanged.connect(self._on_layers_changed)

    @property
    def layers(self) -> Dict[OsmGeometryType, QgsVectorLayer]:
        return self._layers

    def unload(self) -> None:
        map_canvas = iface.mapCanvas()
        map_canvas.layersChanged.disconnect(self._on_layers_changed)

        self.clear()

    def clear(self) -> None:
        self.remove_layers()

    def set_visible(self, visible: bool) -> None:
        if self._is_visible == visible:
            return

        self._is_visible = visible
        if len(self._layers) == 0:
            return

        self._apply_canvas_layers()

    def set_show_all_features(self, enabled: bool) -> None:
        self._show_all_features = enabled

    def set_centroid_rendering_enabled(self, enabled: bool) -> None:
        self._is_centroid_rendering_enabled = enabled

    def ensure_layers(self) -> Dict[OsmGeometryType, QgsVectorLayer]:
        if len(self._layers) > 0:
            return self._layers

        for definition in reversed(LAYER_DEFINITIONS):
            layer = definition.create_layer()
            self._layer_store.addMapLayer(layer)
            self._layers[definition.geometry_type] = layer

        self._apply_canvas_layers()
        return self._layers

    def remove_layers(self) -> None:
        if len(self._layers) == 0:
            return

        map_canvas = iface.mapCanvas()
        self._is_updating = True
        try:
            map_canvas.setLayers(self._base_canvas_layers())
        finally:
            self._is_updating = False
        map_canvas.refresh()

        self._layer_store.removeAllMapLayers()
        self._layers.clear()

    def identify(
        self,
        search_geometry: QgsGeometry,
    ) -> Tuple[OsmResultLayerHit, ...]:
        if len(self._layers) == 0 or not self._is_visible:
            return tuple()

        if search_geometry.isEmpty():
            return tuple()

        map_canvas = iface.mapCanvas()
        map_layers = tuple(map_canvas.layers())
        map_scale = self._current_map_scale()
        identified_hits: List[OsmResultLayerHit] = []
        seen_hits: Set[OsmResultLayerHit] = set()

        for layer in self.ordered_layers():
            if layer not in map_layers:
                continue

            layer_search_geometry = self._to_layer_geometry(
                layer,
                search_geometry,
            )
            if (
                layer_search_geometry is None
                or layer_search_geometry.isEmpty()
            ):
                continue

            feature_request = QgsFeatureRequest()
            feature_request.setFilterRect(layer_search_geometry.boundingBox())
            feature_request.setFlags(FeatureRequestFlag.ExactIntersect)

            for feature in cast(
                Iterable[QgsFeature], layer.getFeatures(feature_request)
            ):
                if not self._is_feature_displayed(
                    layer,
                    feature,
                    layer_search_geometry,
                    map_scale,
                ):
                    continue

                hit = self._feature_hit(feature)
                if hit is None or hit in seen_hits:
                    continue

                seen_hits.add(hit)
                identified_hits.append(hit)

        return tuple(identified_hits)

    def ordered_layers(self) -> Tuple[QgsVectorLayer, ...]:
        ordered_layers: List[QgsVectorLayer] = []
        for definition in reversed(LAYER_DEFINITIONS):
            layer = self._layers.get(definition.geometry_type)
            if layer is None:
                continue

            ordered_layers.append(layer)

        return tuple(ordered_layers)

    def is_result_layer(self, layer: QgsMapLayer) -> bool:
        return bool(layer.customProperty(RESULT_LAYER_PROPERTY, 0))

    @pyqtSlot()
    def _on_layers_changed(self) -> None:
        if self._is_updating or len(self._layers) == 0:
            return

        self._apply_canvas_layers()

    def _apply_canvas_layers(self) -> None:
        map_canvas = iface.mapCanvas()
        self._is_updating = True
        try:
            canvas_layers: List[QgsMapLayer] = self._base_canvas_layers()
            if self._is_visible:
                canvas_layers = list(self.ordered_layers()) + canvas_layers

            map_canvas.setLayers(canvas_layers)
        finally:
            self._is_updating = False
        map_canvas.refresh()

    def _base_canvas_layers(self) -> List[QgsMapLayer]:
        return [
            layer
            for layer in iface.mapCanvas().layers()
            if not self.is_result_layer(layer)
        ]

    def _to_layer_geometry(
        self,
        layer: QgsVectorLayer,
        geometry: QgsGeometry,
    ) -> Optional[QgsGeometry]:
        map_canvas = iface.mapCanvas()
        layer_geometry = QgsGeometry(geometry)
        if layer.crs() == map_canvas.mapSettings().destinationCrs():
            return layer_geometry

        transform = QgsCoordinateTransform(
            map_canvas.mapSettings().destinationCrs(),
            layer.crs(),
            QgsProject.instance(),
        )
        layer_geometry.transform(transform)
        return layer_geometry

    def _is_feature_displayed(
        self,
        layer: QgsVectorLayer,
        feature: QgsFeature,
        layer_search_geometry: QgsGeometry,
        map_scale: Optional[float],
    ) -> bool:
        display_geometry = self._display_geometry(layer, feature, map_scale)
        if display_geometry is None or display_geometry.isEmpty():
            return False

        if not display_geometry.intersects(layer_search_geometry):
            return False

        if self._show_all_features:
            return True

        return bool(int(feature.attribute(FIELD_ACTIVE) or 0))

    def _display_geometry(
        self,
        layer: QgsVectorLayer,
        feature: QgsFeature,
        map_scale: Optional[float],
    ) -> Optional[QgsGeometry]:
        geometry = feature.geometry()
        if geometry is None or geometry.isEmpty():
            return None

        if self._uses_centroid_geometry(layer, feature, map_scale):
            centroid_geometry = geometry.centroid()
            if (
                centroid_geometry is not None
                and not centroid_geometry.isEmpty()
            ):
                return centroid_geometry

        return geometry

    def _uses_centroid_geometry(
        self,
        layer: QgsVectorLayer,
        feature: QgsFeature,
        map_scale: Optional[float],
    ) -> bool:
        if not self._is_centroid_rendering_enabled:
            return False

        if layer.geometryType() == GeometryType.Point:
            return False

        max_scale_value = feature.attribute(FIELD_MAX_SCALE)
        if max_scale_value is None:
            return False

        try:
            max_scale = float(max_scale_value)
        except (TypeError, ValueError):
            return False

        if map_scale is None:
            return True

        return map_scale > max_scale

    def _current_map_scale(self) -> Optional[float]:
        map_canvas = iface.mapCanvas()
        extent = map_canvas.extent()
        if extent.isNull() or extent.isEmpty():
            return None

        map_scale = map_canvas.scale()
        if map_scale <= 0:
            return None

        return map_scale

    def _feature_hit(
        self,
        feature: QgsFeature,
    ) -> Optional[OsmResultLayerHit]:
        raw_element_type = feature.attribute(FIELD_OSM_TYPE)
        raw_osm_id = feature.attribute(FIELD_OSM_ID)
        if raw_element_type is None or raw_osm_id is None:
            return None

        try:
            return OsmResultLayerHit(
                element_type=OsmElementType(str(raw_element_type)),
                osm_id=int(raw_osm_id),
            )
        except (TypeError, ValueError):
            return None
