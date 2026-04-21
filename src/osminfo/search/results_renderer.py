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

from typing import (
    TYPE_CHECKING,
    Any,
    Dict,
    List,
    Optional,
    Sequence,
    Set,
    Tuple,
    cast,
)

from qgis.core import (
    Qgis,
    QgsCentroidFillSymbolLayer,
    QgsCoordinateReferenceSystem,
    QgsCoordinateTransform,
    QgsFeature,
    QgsFillSymbol,
    QgsGeometry,
    QgsGeometryGeneratorSymbolLayer,
    QgsLineSymbol,
    QgsMapLayer,
    QgsMapLayerStore,
    QgsMarkerSymbol,
    QgsPointXY,
    QgsProject,
    QgsRectangle,
    QgsReferencedRectangle,
    QgsRuleBasedRenderer,
    QgsSimpleFillSymbolLayer,
    QgsSimpleLineSymbolLayer,
    QgsSimpleMarkerSymbolLayer,
    QgsSymbol,
    QgsVectorLayer,
)
from qgis.PyQt.QtCore import QObject, Qt, pyqtSlot
from qgis.PyQt.QtGui import QColor
from qgis.utils import iface

from osminfo.openstreetmap.models import (
    OsmElement,
    OsmElementType,
    OsmGeometryCollection,
    OsmGeometryType,
    OsmResultTree,
)

if TYPE_CHECKING:
    from qgis.gui import QgisInterface

    assert isinstance(iface, QgisInterface)

LAYER_DEFINITIONS = (
    (OsmGeometryType.POLYGON, "MultiPolygon", "OSMInfo polygons"),
    (OsmGeometryType.LINESTRING, "MultiLineString", "OSMInfo lines"),
    (OsmGeometryType.POINT, "MultiPoint", "OSMInfo points"),
)

RESULT_LAYER_PROPERTY = "osminfo_result_layer"
FIELD_RELATION = "relation_related"
FIELD_TAINTED = "is_tainted"
FIELD_ACTIVE = "is_active"
FIELD_MAX_SCALE = "max_scale"
MARKER_SIZE = 16.0


class OsmResultsRenderer(QObject):
    def __init__(self, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self._layers: Dict[OsmGeometryType, QgsVectorLayer] = {}
        self._elements: Dict[Tuple[OsmElementType, int], OsmElement] = {}
        self._active_keys: Set[Tuple[OsmElementType, int]] = set()
        self._feature_ids_by_element: Dict[
            Tuple[OsmElementType, int],
            List[Tuple[OsmGeometryType, int]],
        ] = {}
        self._is_centroid_rendering_enabled = True
        self._layer_store = QgsMapLayerStore(self)
        self._is_updating = False

        map_canvas = iface.mapCanvas()
        map_canvas.layersChanged.connect(self._on_layers_changed)

    def unload(self) -> None:
        map_canvas = iface.mapCanvas()
        map_canvas.layersChanged.disconnect(self._on_layers_changed)

        self.clear()

    def clear(self) -> None:
        self._elements = {}
        self._active_keys = set()
        self._feature_ids_by_element = {}
        self._remove_layers()

    def set_centroid_rendering_enabled(self, enabled: bool) -> None:
        if self._is_centroid_rendering_enabled == enabled:
            return

        self._is_centroid_rendering_enabled = enabled
        if len(self._layers) == 0:
            return

        self._refresh_renderers()

    def set_result_tree(self, result_tree: OsmResultTree) -> None:
        self._elements = {}
        for group in result_tree.groups:
            for element in group.elements:
                self._elements[self._element_key(element)] = element

        self._active_keys = set()
        if len(self._elements) == 0:
            self._remove_layers()
            return

        self._ensure_layers()
        self._refresh_layers()

    def set_active_elements(
        self,
        elements: Sequence[OsmElement],
    ) -> None:
        active_keys = {self._element_key(element) for element in elements}
        if active_keys == self._active_keys:
            return

        previous_active_keys = self._active_keys
        self._active_keys = active_keys
        if len(self._layers) == 0:
            return

        self._update_active_features(previous_active_keys)

    def zoom_to_bbox(self, bbox: QgsRectangle) -> None:
        if bbox.width() <= 0 and bbox.height() <= 0:
            self._center_to_point(bbox.center())
            return

        map_canvas = iface.mapCanvas()
        srs_wgs84 = QgsCoordinateReferenceSystem.fromEpsgId(4326)
        map_canvas.setReferencedExtent(QgsReferencedRectangle(bbox, srs_wgs84))
        map_canvas.refresh()

    def _center_to_point(self, point: QgsPointXY) -> None:
        map_canvas = iface.mapCanvas()
        transform = QgsCoordinateTransform(
            QgsCoordinateReferenceSystem.fromEpsgId(4326),
            map_canvas.mapSettings().destinationCrs(),
            QgsProject.instance(),
        )
        canvas_point = transform.transform(point)
        new_extent = QgsRectangle(map_canvas.extent())
        new_extent.scale(1, canvas_point)
        map_canvas.setExtent(new_extent)
        map_canvas.refresh()

    @pyqtSlot()
    def _on_layers_changed(self) -> None:
        if self._is_updating or len(self._layers) == 0:
            return

        self._apply_canvas_layers()

    def _ensure_layers(self) -> None:
        if len(self._layers) > 0:
            return

        for geometry_type, geometry_name, layer_name in LAYER_DEFINITIONS:
            layer = QgsVectorLayer(
                (
                    f"{geometry_name}?crs=EPSG:4326"
                    f"&field={FIELD_RELATION}:integer"
                    f"&field={FIELD_TAINTED}:integer"
                    f"&field={FIELD_ACTIVE}:integer"
                    f"&field={FIELD_MAX_SCALE}:double"
                ),
                layer_name,
                "memory",
            )
            layer.setCustomProperty(RESULT_LAYER_PROPERTY, 1)
            layer.setCustomProperty("skipMemoryLayersCheck", 1)
            layer.setReadOnly(True)
            layer.setRenderer(self._create_renderer(geometry_type))
            self._layer_store.addMapLayer(layer)
            self._layers[geometry_type] = layer

        self._apply_canvas_layers()

    def _refresh_renderers(self) -> None:
        for geometry_type, layer in self._layers.items():
            layer.setRenderer(self._create_renderer(geometry_type))
            layer.triggerRepaint()

        iface.mapCanvas().refresh()

    def _remove_layers(self) -> None:
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
        self._layers = {}
        self._feature_ids_by_element = {}

    def _apply_canvas_layers(self) -> None:
        map_canvas = iface.mapCanvas()
        self._is_updating = True
        try:
            map_canvas.setLayers(
                self._ordered_layers() + self._base_canvas_layers()
            )
        finally:
            self._is_updating = False
        map_canvas.refresh()

    def _base_canvas_layers(self) -> List[QgsMapLayer]:
        return [
            layer
            for layer in iface.mapCanvas().layers()
            if not self._is_result_layer(layer)
        ]

    def _ordered_layers(self) -> List[QgsVectorLayer]:
        return [
            self._layers[geometry_type]
            for geometry_type, _, _ in reversed(LAYER_DEFINITIONS)
            if geometry_type in self._layers
        ]

    def _is_result_layer(self, layer: QgsMapLayer) -> bool:
        return bool(layer.customProperty(RESULT_LAYER_PROPERTY, 0))

    def _refresh_layers(self) -> None:
        if len(self._layers) == 0:
            return

        feature_entries_by_layer: Dict[
            OsmGeometryType,
            List[Tuple[Tuple[OsmElementType, int], QgsFeature]],
        ] = {
            OsmGeometryType.POINT: [],
            OsmGeometryType.LINESTRING: [],
            OsmGeometryType.POLYGON: [],
        }
        self._feature_ids_by_element = {}

        for element in self._elements.values():
            element_key = self._element_key(element)
            for geometry_type, geometry, max_scale in self._display_parts(
                element
            ):
                layer = self._layers[geometry_type]
                feature = QgsFeature(layer.fields())
                feature.setGeometry(
                    self._to_layer_geometry(geometry, geometry_type)
                )
                feature.setAttributes(
                    [
                        int(
                            element.is_relation_member
                            or element.element_type.value == "relation"
                        ),
                        int(element.is_incomplete),
                        int(element_key in self._active_keys),
                        max_scale,
                    ]
                )
                feature_entries_by_layer[geometry_type].append(
                    (element_key, feature)
                )

        for geometry_type, layer in self._layers.items():
            provider = layer.dataProvider()
            existing_ids = list(layer.allFeatureIds())
            if len(existing_ids) > 0:
                provider.deleteFeatures(existing_ids)

            layer_entries = feature_entries_by_layer[geometry_type]
            layer_entries.sort(
                key=lambda entry: self._feature_sort_key(
                    geometry_type,
                    entry[1].geometry(),
                ),
                reverse=True,
            )
            layer_features = [feature for _, feature in layer_entries]
            if len(layer_features) > 0:
                provider.addFeatures(layer_features)
                self._remember_feature_ids(geometry_type, layer, layer_entries)

            layer.updateExtents()
            layer.triggerRepaint()

        map_canvas = iface.mapCanvas()
        if map_canvas is not None:
            map_canvas.refresh()

    def _update_active_features(
        self,
        previous_active_keys: Set[Tuple[OsmElementType, int]],
    ) -> None:
        if len(self._feature_ids_by_element) == 0:
            self._refresh_layers()
            return

        changed_keys = previous_active_keys ^ self._active_keys
        if len(changed_keys) == 0:
            return

        changed_attributes_by_layer: Dict[
            OsmGeometryType,
            Dict[int, Dict[int, int]],
        ] = {}

        for element_key in changed_keys:
            feature_refs = self._feature_ids_by_element.get(element_key)
            if feature_refs is None:
                element = self._elements.get(element_key)
                if (
                    element is not None
                    and len(self._display_parts(element)) > 0
                ):
                    self._refresh_layers()
                    return

                continue

            active_value = int(element_key in self._active_keys)
            for geometry_type, feature_id in feature_refs:
                layer = self._layers.get(geometry_type)
                if layer is None:
                    continue

                field_index = layer.fields().indexOf(FIELD_ACTIVE)
                if field_index < 0:
                    continue

                changed_attributes_by_layer.setdefault(geometry_type, {})[
                    feature_id
                ] = {field_index: active_value}

        for (
            geometry_type,
            changed_attributes,
        ) in changed_attributes_by_layer.items():
            layer = self._layers[geometry_type]
            layer.dataProvider().changeAttributeValues(changed_attributes)
            layer.triggerRepaint()

        map_canvas = iface.mapCanvas()
        map_canvas.refresh()

    def _remember_feature_ids(
        self,
        geometry_type: OsmGeometryType,
        layer: QgsVectorLayer,
        layer_entries: List[Tuple[Tuple[OsmElementType, int], QgsFeature]],
    ) -> None:
        added_features = sorted(
            cast(Any, layer.getFeatures()),
            key=lambda feature: feature.id(),
        )
        if len(added_features) != len(layer_entries):
            return

        for (element_key, _), feature in zip(layer_entries, added_features):
            self._feature_ids_by_element.setdefault(element_key, []).append(
                (geometry_type, feature.id())
            )

    def _display_parts(
        self,
        element: OsmElement,
    ) -> Tuple[Tuple[OsmGeometryType, QgsGeometry, Optional[float]], ...]:
        if element.geometry is None:
            return tuple()

        if isinstance(element.geometry, QgsGeometry):
            return self._single_geometry_parts(element)

        if isinstance(element.geometry, OsmGeometryCollection):
            return self._collection_parts(element)

        return tuple()

    def _single_geometry_parts(
        self,
        element: OsmElement,
    ) -> Tuple[Tuple[OsmGeometryType, QgsGeometry, Optional[float]], ...]:
        assert isinstance(element.geometry, QgsGeometry)

        geometry_type = element.geometry_type()
        if geometry_type is None:
            return tuple()

        return (
            (
                geometry_type,
                QgsGeometry(element.geometry),
                self._feature_max_scale(geometry_type, element.max_scale),
            ),
        )

    def _collection_parts(
        self,
        element: OsmElement,
    ) -> Tuple[Tuple[OsmGeometryType, QgsGeometry, Optional[float]], ...]:
        assert isinstance(element.geometry, OsmGeometryCollection)

        parts: List[Tuple[OsmGeometryType, QgsGeometry, Optional[float]]] = []
        has_points = element.geometry.points is not None
        if element.geometry.points is not None:
            parts.append(
                (
                    OsmGeometryType.POINT,
                    QgsGeometry(element.geometry.points),
                    None,
                )
            )

        if element.geometry.lines is not None:
            parts.append(
                (
                    OsmGeometryType.LINESTRING,
                    QgsGeometry(element.geometry.lines),
                    self._feature_max_scale(
                        OsmGeometryType.LINESTRING,
                        None if has_points else element.max_scale,
                    ),
                )
            )

        if element.geometry.polygons is not None:
            parts.append(
                (
                    OsmGeometryType.POLYGON,
                    QgsGeometry(element.geometry.polygons),
                    self._feature_max_scale(
                        OsmGeometryType.POLYGON,
                        None if has_points else element.max_scale,
                    ),
                )
            )

        return tuple(parts)

    def _feature_max_scale(
        self,
        geometry_type: OsmGeometryType,
        max_scale: Optional[float],
    ) -> Optional[float]:
        if geometry_type == OsmGeometryType.POINT:
            return None

        return max_scale

    def _to_layer_geometry(
        self,
        geometry: QgsGeometry,
        geometry_type: OsmGeometryType,
    ) -> QgsGeometry:
        if geometry_type == OsmGeometryType.POINT:
            if geometry.isMultipart():
                return QgsGeometry.fromMultiPointXY(geometry.asMultiPoint())

            return QgsGeometry.fromMultiPointXY([geometry.asPoint()])

        if geometry_type == OsmGeometryType.LINESTRING:
            if geometry.isMultipart():
                return QgsGeometry.fromMultiPolylineXY(
                    geometry.asMultiPolyline()
                )

            return QgsGeometry.fromMultiPolylineXY([geometry.asPolyline()])

        if geometry.isMultipart():
            return QgsGeometry.fromMultiPolygonXY(geometry.asMultiPolygon())

        return QgsGeometry.fromMultiPolygonXY([geometry.asPolygon()])

    def _feature_sort_key(
        self,
        geometry_type: OsmGeometryType,
        geometry: QgsGeometry,
    ) -> float:
        if geometry_type == OsmGeometryType.POLYGON:
            return geometry.area()

        if geometry_type == OsmGeometryType.LINESTRING:
            return geometry.length()

        return 0.0

    def _element_key(self, element: OsmElement) -> Tuple[OsmElementType, int]:
        return (element.element_type, element.osm_id)

    def _create_renderer(
        self,
        geometry_type: OsmGeometryType,
    ) -> QgsRuleBasedRenderer:
        renderer = QgsRuleBasedRenderer(
            self._symbol_for_geometry(geometry_type)
        )
        root_rule = renderer.rootRule()
        for child_rule in list(root_rule.children()):
            root_rule.removeChild(child_rule)

        rule_variants = self._rule_variants()

        if (
            geometry_type != OsmGeometryType.POINT
            and self._is_centroid_rendering_enabled
        ):
            for symbol_kwargs, base_filter in rule_variants:
                self._add_rule(
                    root_rule,
                    self._symbol_for_geometry(geometry_type, **symbol_kwargs),
                    self._compose_filter(
                        base_filter,
                        self._normal_geometry_filter(),
                    ),
                )
                self._add_rule(
                    root_rule,
                    self._symbol_for_geometry(
                        geometry_type,
                        centroid=True,
                        **symbol_kwargs,
                    ),
                    self._compose_filter(
                        base_filter,
                        self._centroid_geometry_filter(),
                    ),
                )
            return renderer

        for symbol_kwargs, base_filter in rule_variants:
            self._add_rule(
                root_rule,
                self._symbol_for_geometry(geometry_type, **symbol_kwargs),
                base_filter,
            )

        return renderer

    def _rule_variants(self):
        return (
            (
                dict(active=True),
                f'"{FIELD_ACTIVE}" = 1',
            ),
            (
                dict(relation_related=True, tainted=True),
                (
                    f'"{FIELD_ACTIVE}" = 0 AND "{FIELD_RELATION}" = 1 '
                    f'AND "{FIELD_TAINTED}" = 1'
                ),
            ),
            (
                dict(relation_related=True),
                (
                    f'"{FIELD_ACTIVE}" = 0 AND "{FIELD_RELATION}" = 1 '
                    f'AND "{FIELD_TAINTED}" = 0'
                ),
            ),
            (
                dict(tainted=True),
                (
                    f'"{FIELD_ACTIVE}" = 0 AND "{FIELD_RELATION}" = 0 '
                    f'AND "{FIELD_TAINTED}" = 1'
                ),
            ),
            (
                {},
                (
                    f'"{FIELD_ACTIVE}" = 0 AND "{FIELD_RELATION}" = 0 '
                    f'AND "{FIELD_TAINTED}" = 0'
                ),
            ),
        )

    def _normal_geometry_filter(self) -> str:
        return (
            f'"{FIELD_MAX_SCALE}" IS NULL OR @map_scale <= "{FIELD_MAX_SCALE}"'
        )

    def _centroid_geometry_filter(self) -> str:
        return (
            f'"{FIELD_MAX_SCALE}" IS NOT NULL '
            f'AND @map_scale > "{FIELD_MAX_SCALE}"'
        )

    def _compose_filter(
        self,
        base_filter: Optional[str],
        scale_filter: str,
    ) -> str:
        if base_filter is None:
            return scale_filter

        return f"({base_filter}) AND ({scale_filter})"

    def _add_rule(
        self,
        root_rule,
        symbol,
        filter_expression: Optional[str],
    ):
        rule = QgsRuleBasedRenderer.Rule(symbol)
        if filter_expression is not None:
            rule.setFilterExpression(filter_expression)
        root_rule.appendChild(rule)
        return rule

    def _symbol_for_geometry(
        self,
        geometry_type: OsmGeometryType,
        *,
        relation_related: bool = False,
        tainted: bool = False,
        active: bool = False,
        centroid: bool = False,
    ):
        if centroid:
            symbol = self._centroid_symbol(
                geometry_type,
                active=active,
                relation_related=relation_related,
            )

        elif geometry_type == OsmGeometryType.POINT:
            symbol = self._point_symbol(
                geometry_type,
                relation_related=relation_related,
                active=active,
            )

        elif geometry_type == OsmGeometryType.LINESTRING:
            symbol = self._line_symbol(
                geometry_type,
                relation_related=relation_related,
                tainted=tainted,
                active=active,
            )

        else:
            symbol = self._polygon_symbol(
                geometry_type,
                relation_related=relation_related,
                tainted=tainted,
                active=active,
            )

        return symbol

    def _point_symbol(
        self,
        geometry_type: OsmGeometryType,
        *,
        relation_related: bool,
        active: bool,
    ):
        outline_color = self._outline_color(
            geometry_type,
            active,
            relation_related,
        )
        return self._marker_symbol(
            outline_color,
            self._fill_color(active, False),
            size=MARKER_SIZE,
            outline_width=2,
        )

    def _line_symbol(
        self,
        geometry_type: OsmGeometryType,
        *,
        relation_related: bool,
        tainted: bool,
        active: bool,
    ):
        symbol = QgsLineSymbol()
        symbol.deleteSymbolLayer(0)
        layer = QgsSimpleLineSymbolLayer()
        line_color = self._outline_color(
            geometry_type,
            active,
            relation_related,
        )
        layer.setColor(line_color)
        layer.setWidth(5.0)
        layer.setWidthUnit(Qgis.RenderUnit.Pixels)

        if tainted:
            layer.setPenStyle(Qt.PenStyle.CustomDashLine)
            layer.setUseCustomDashPattern(True)
            layer.setCustomDashVector([5.0, 8.0])
            layer.setCustomDashPatternUnit(Qgis.RenderUnit.Pixels)
        symbol.appendSymbolLayer(layer)

        return symbol

    def _polygon_symbol(
        self,
        geometry_type: OsmGeometryType,
        *,
        relation_related: bool,
        tainted: bool,
        active: bool,
    ):
        symbol = QgsFillSymbol()
        symbol.deleteSymbolLayer(0)
        layer = QgsSimpleFillSymbolLayer()
        layer.setStrokeColor(
            self._outline_color(
                geometry_type,
                active,
                relation_related,
            )
        )
        layer.setStrokeWidth(2.0)
        layer.setStrokeWidthUnit(Qgis.RenderUnit.Pixels)
        layer.setFillColor(self._fill_color(active, False))
        if tainted:
            layer.setStrokeStyle(Qt.PenStyle.DashLine)
        symbol.appendSymbolLayer(layer)

        return symbol

    def _centroid_symbol(
        self,
        geometry_type: OsmGeometryType,
        *,
        active: bool,
        relation_related: bool,
    ) -> QgsSymbol:
        if geometry_type == OsmGeometryType.LINESTRING:
            return self._line_centroid_symbol(
                geometry_type,
                active=active,
                relation_related=relation_related,
            )

        return self._polygon_centroid_symbol(
            geometry_type,
            active=active,
            relation_related=relation_related,
        )

    def _line_centroid_symbol(
        self,
        geometry_type: OsmGeometryType,
        *,
        active: bool,
        relation_related: bool,
    ) -> QgsSymbol:
        symbol = QgsLineSymbol()
        symbol.deleteSymbolLayer(0)
        geometry_layer = cast(
            QgsGeometryGeneratorSymbolLayer,
            QgsGeometryGeneratorSymbolLayer.create({}),
        )
        geometry_layer.setSymbolType(Qgis.SymbolType.Marker)
        geometry_layer.setGeometryExpression("centroid($geometry)")
        geometry_layer.setSubSymbol(
            self._marker_symbol(
                self._outline_color(
                    geometry_type,
                    active,
                    relation_related,
                ),
                self._fill_color(active, True),
                size=MARKER_SIZE,
                outline_width=2.0,
            )
        )
        symbol.appendSymbolLayer(geometry_layer)
        return symbol

    def _polygon_centroid_symbol(
        self,
        geometry_type: OsmGeometryType,
        *,
        active: bool,
        relation_related: bool,
    ) -> QgsSymbol:
        symbol = QgsFillSymbol()
        symbol.deleteSymbolLayer(0)
        centroid_layer = cast(
            QgsCentroidFillSymbolLayer,
            QgsCentroidFillSymbolLayer.create({}),
        )
        centroid_layer.setPointOnAllParts(True)
        centroid_layer.setPointOnSurface(False)
        centroid_layer.setClipOnCurrentPartOnly(False)
        centroid_layer.setClipPoints(False)
        centroid_layer.setSubSymbol(
            self._marker_symbol(
                self._outline_color(
                    geometry_type,
                    active,
                    relation_related,
                ),
                self._fill_color(active, True),
                size=MARKER_SIZE,
                outline_width=2.0,
            )
        )
        symbol.appendSymbolLayer(centroid_layer)
        return symbol

    def _marker_symbol(
        self,
        outline_color: QColor,
        fill_color: QColor,
        *,
        size: float,
        outline_width: float,
    ) -> QgsMarkerSymbol:
        symbol = QgsMarkerSymbol.createSimple(
            {
                "name": "circle",
                "size": str(size),
                "outline_width": str(outline_width),
                "outline_color": self._color_string(outline_color),
                "color": self._color_string(fill_color),
            }
        )
        assert symbol is not None
        marker_layer = cast(
            QgsSimpleMarkerSymbolLayer,
            symbol.symbolLayer(0),
        )
        marker_layer.setSizeUnit(Qgis.RenderUnit.Pixels)
        marker_layer.setStrokeWidthUnit(Qgis.RenderUnit.Pixels)
        return symbol

    def _color_string(self, color: QColor) -> str:
        return color.name(QColor.NameFormat.HexArgb)

    def _outline_color(
        self,
        geometry_type: OsmGeometryType,
        active: bool,
        relation_related: bool,
    ) -> QColor:
        if active:
            color = QColor("#f50")
        elif relation_related:
            color = QColor("#d0f")
        else:
            color = QColor("#03f")

        alpha = 0.7
        if geometry_type == OsmGeometryType.LINESTRING:
            alpha = 0.6

        color.setAlphaF(alpha)
        return color

    def _fill_color(self, active: bool, centroid: bool) -> QColor:
        if active:
            color = QColor("#f50")
        elif centroid:
            color = QColor("#f22")
        else:
            color = QColor("#fc0")

        color.setAlphaF(0.3)
        return color
