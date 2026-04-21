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
    Tuple,
    cast,
)

from qgis.core import (
    Qgis,
    QgsCoordinateReferenceSystem,
    QgsCoordinateTransform,
    QgsFeature,
    QgsField,
    QgsGeometry,
    QgsProject,
    QgsVectorLayer,
)
from qgis.PyQt.QtCore import QObject
from qgis.PyQt.QtWidgets import QMessageBox
from qgis.utils import iface

from osminfo.compat import FieldType, GeometryType, addMapLayer
from osminfo.logging import logger
from osminfo.osminfo_interface import OsmInfoInterface
from osminfo.search.result_selection import OsmResultSelectionItem

if TYPE_CHECKING:
    from qgis.gui import QgisInterface

    assert isinstance(iface, QgisInterface)


class AttributeMismatchMessageBox(QMessageBox):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)

        self.setIcon(QMessageBox.Icon.Question)
        self.setWindowTitle(self.tr("Attribute mismatch"))
        self.setInformativeText(self.tr("Add missing attributes?"))
        self.setText(
            self.tr(
                "The feature you are trying to add has attributes that are "
                "not present in the target layer."
            )
        )

        button = QMessageBox.StandardButton
        self.setStandardButtons(
            button.Yes | button.No | button.Cancel,
        )
        self.setDefaultButton(button.Yes)


class OsmResultLayerExporter(QObject):
    def __init__(self, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)

    def save_in_new_temporary_layers(
        self,
        items: Sequence[OsmResultSelectionItem],
    ) -> None:
        geometry_items = self._geometry_items(items)
        if len(geometry_items) == 0:
            return

        grouped_items = self._group_items_for_new_layers(geometry_items)
        for layer_geometry_name, layer_items in grouped_items.items():
            layer = QgsVectorLayer(
                f"{layer_geometry_name}?crs=EPSG:4326",
                self._new_layer_name(),
                "memory",
            )
            if not layer.isValid():
                self._show_message(
                    self.tr("Failed to create a temporary layer"),
                )
                continue

            if not self._populate_new_layer(layer, layer_items):
                continue

            addMapLayer(layer)

    def save_in_selected_layer(
        self,
        items: Sequence[OsmResultSelectionItem],
    ) -> None:
        layer = self._selected_vector_layer()
        if layer is None:
            return

        geometry_items = self._geometry_items(items)
        if len(geometry_items) == 0:
            return

        if not self._can_store_items(layer, geometry_items):
            self._show_message(
                self.tr("Selected layer cannot store the selected features"),
            )
            return

        self._append_to_existing_layer(layer, geometry_items)

    def can_save_in_selected_layer(
        self,
        items: Sequence[OsmResultSelectionItem],
    ) -> bool:
        layer = self._selected_vector_layer()
        if layer is None:
            return False

        geometry_items = self._geometry_items(items)
        if len(geometry_items) == 0:
            return False

        return self._can_store_items(layer, geometry_items)

    def _geometry_items(
        self,
        items: Sequence[OsmResultSelectionItem],
    ) -> Tuple[OsmResultSelectionItem, ...]:
        return tuple(
            item for item in items if item.element.qgs_geometry() is not None
        )

    def _group_items_for_new_layers(
        self,
        items: Sequence[OsmResultSelectionItem],
    ) -> Dict[str, List[OsmResultSelectionItem]]:
        grouped_items: Dict[str, List[OsmResultSelectionItem]] = {}
        for item in items:
            geometry = item.element.qgs_geometry()
            if geometry is None:
                continue

            layer_geometry_name = self._layer_geometry_name(geometry)
            if layer_geometry_name is None:
                continue

            grouped_items.setdefault(layer_geometry_name, []).append(item)

        return grouped_items

    def _populate_new_layer(
        self,
        layer: QgsVectorLayer,
        items: Sequence[OsmResultSelectionItem],
    ) -> bool:
        provider = cast(Any, layer.dataProvider())
        field_names = self._field_names(items)
        if len(field_names) > 0:
            provider.addAttributes(
                [
                    QgsField(field_name, FieldType.QString)
                    for field_name in field_names
                ]
            )
            layer.updateFields()

        features = self._build_features(layer, items)
        if len(features) == 0:
            self._show_message(self.tr("Selected features have no geometry"))
            return False

        provider.addFeatures(features)
        layer.updateExtents()
        layer.triggerRepaint()
        return True

    def _append_to_existing_layer(
        self,
        layer: QgsVectorLayer,
        items: Sequence[OsmResultSelectionItem],
    ) -> bool:
        if not self._ensure_existing_layer_fields(layer, items):
            return False

        features = self._build_features(layer, items)
        if len(features) == 0:
            self._show_message(self.tr("Selected features have no geometry"))
            return False

        was_editable = layer.isEditable()
        if not was_editable and not layer.startEditing():
            self._show_message(
                self.tr("Failed to start editing the selected layer"),
            )
            return False

        command_started = False
        layer.beginEditCommand(self.tr("Add OSM features"))
        command_started = True
        try:
            for feature in features:
                if not layer.addFeature(feature):
                    logger.error(
                        "Failed to add a feature to the selected layer"
                    )
                    self._show_message(
                        self.tr("Failed to add features to the selected layer")
                    )
                    return False

            layer.endEditCommand()
            command_started = False
            layer.updateExtents()
            layer.triggerRepaint()

            if was_editable:
                return True

            if not layer.commitChanges(stopEditing=True):
                commit_errors = "; ".join(layer.commitErrors())
                logger.error(
                    "Failed to commit features to the selected layer: %s",
                    commit_errors or "unknown error",
                )
                if layer.isEditable():
                    layer.rollBack()
                self._show_message(
                    self.tr("Failed to save changes to the selected layer")
                )
                return False
        except Exception:
            logger.exception("Failed to add features to the existing layer.")
            if command_started:
                cast(Any, layer).destroyEditCommand()

            if not was_editable and layer.isEditable():
                layer.rollBack()

            self._show_message(
                self.tr("Failed to add features to the selected layer")
            )
            return False

        return True

    def _ensure_existing_layer_fields(
        self,
        layer: QgsVectorLayer,
        items: Sequence[OsmResultSelectionItem],
    ) -> bool:
        field_names = self._field_names(items)
        missing_fields = [
            field_name
            for field_name in field_names
            if field_name not in layer.fields().names()
        ]
        if len(missing_fields) == 0:
            return True

        message_box = AttributeMismatchMessageBox()
        result_button = message_box.exec()

        button = QMessageBox.StandardButton
        if result_button == button.Cancel:
            return False

        if result_button == button.No:
            return True

        provider = cast(Any, layer.dataProvider())
        provider.addAttributes(
            [
                QgsField(field_name, FieldType.QString)
                for field_name in missing_fields
            ]
        )
        layer.updateFields()
        return True

    def _build_features(
        self,
        layer: QgsVectorLayer,
        items: Sequence[OsmResultSelectionItem],
    ) -> List[QgsFeature]:
        layer_field_names = layer.fields().names()
        features: List[QgsFeature] = []
        for item in items:
            geometry = item.element.qgs_geometry()
            if geometry is None:
                continue

            feature = QgsFeature(layer.fields())
            feature_geometry = QgsGeometry(geometry)
            self._transform_geometry(feature_geometry, layer)
            feature.setGeometry(feature_geometry)
            feature.setAttributes(
                [
                    item.element.tags.get(field_name)
                    for field_name in layer_field_names
                ]
            )
            features.append(feature)

        return features

    def _transform_geometry(
        self,
        geometry: QgsGeometry,
        layer: QgsVectorLayer,
    ) -> None:
        if layer.crs().authid() == "EPSG:4326":
            return

        transform = QgsCoordinateTransform(
            QgsCoordinateReferenceSystem.fromEpsgId(4326),
            layer.crs(),
            QgsProject.instance(),
        )
        geometry.transform(transform)

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

    def _selected_vector_layer(self) -> Optional[QgsVectorLayer]:
        layers = iface.layerTreeView().selectedLayers()
        if len(layers) != 1:
            return None

        selected_layer = layers[0]
        if not isinstance(selected_layer, QgsVectorLayer):
            return None

        return selected_layer

    def _can_store_items(
        self,
        layer: QgsVectorLayer,
        items: Sequence[OsmResultSelectionItem],
    ) -> bool:
        for item in items:
            geometry = item.element.qgs_geometry()
            if geometry is None:
                return False

            if layer.geometryType() != geometry.type():
                return False

        return True

    def _layer_geometry_name(
        self,
        geometry: QgsGeometry,
    ) -> Optional[str]:
        if geometry.type() == GeometryType.Point:
            return "MultiPoint" if geometry.isMultipart() else "Point"

        if geometry.type() == GeometryType.Line:
            return (
                "MultiLineString" if geometry.isMultipart() else "LineString"
            )

        if geometry.type() == GeometryType.Polygon:
            return "MultiPolygon" if geometry.isMultipart() else "Polygon"

        return None

    def _new_layer_name(self) -> str:
        return self.tr("OpenStreetMap Features")

    def _show_message(self, message: str) -> None:
        notifier = OsmInfoInterface.instance().notifier
        notifier.display_message(message, level=Qgis.MessageLevel.Warning)
