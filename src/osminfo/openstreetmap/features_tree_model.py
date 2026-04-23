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

from enum import Enum
from typing import Any, Dict, List, Optional, Set, Tuple

from qgis.core import QgsApplication
from qgis.PyQt.QtCore import QAbstractItemModel, QModelIndex, Qt
from qgis.PyQt.QtGui import (
    QBrush,
    QFont,
    QGuiApplication,
    QIcon,
    QMovie,
    QPalette,
)

from osminfo.openstreetmap.models import OsmElement, OsmResultTree, OsmTag
from osminfo.openstreetmap.tag2link import TagLink
from osminfo.ui.icon import qgis_icon

GEOMETRY_TYPE_ICONS = {
    "POINT": qgis_icon("mIconPointLayer.svg"),
    "LINESTRING": qgis_icon("mIconLineLayer.svg"),
    "POLYGON": qgis_icon("mIconPolygonLayer.svg"),
    "COLLECTION": qgis_icon("mIconGeometryCollectionLayer.svg"),
}


class FeatureTreeNodeType(Enum):
    ROOT = "root"
    GROUP = "group"
    FEATURE = "feature"
    TAG = "tag"
    WARNING = "warning"


class _FeatureTreeNode:
    def __init__(
        self,
        node_type: FeatureTreeNodeType,
        column_values: Tuple[str, str] = ("", ""),
        *,
        parent: Optional["_FeatureTreeNode"] = None,
        osm_element: Optional[OsmElement] = None,
        osm_tag: Optional[OsmTag] = None,
    ) -> None:
        self.node_type = node_type
        self.column_values = column_values
        self.parent = parent
        self.osm_element = osm_element
        self.osm_tag = osm_tag
        self.children: List[_FeatureTreeNode] = []

    def row(self) -> int:
        if self.parent is None:
            return 0

        return self.parent.children.index(self)


class OsmFeaturesTreeModel(QAbstractItemModel):
    NODE_TYPE_ROLE = int(Qt.ItemDataRole.UserRole)
    OSM_ELEMENT_ROLE = int(Qt.ItemDataRole.UserRole) + 1
    TAG_LINKS_ROLE = int(Qt.ItemDataRole.UserRole) + 2
    IS_LOADING_ROLE = int(Qt.ItemDataRole.UserRole) + 3

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._root = _FeatureTreeNode(FeatureTreeNodeType.ROOT)
        self._section_font = QFont()
        self._section_font.setBold(True)
        self._tag_link_font = QFont()
        self._tag_link_font.setUnderline(True)
        self._tag_link_brush = QBrush(
            QgsApplication.palette().color(QPalette.ColorRole.Link)
        )
        self._feature_nodes: Dict[Tuple[str, int], _FeatureTreeNode] = {}
        self._loading_keys: Set[Tuple[str, int]] = set()
        self._loading_movie: Optional[QMovie] = None

    def columnCount(self, parent: Optional[QModelIndex] = None) -> int:  # noqa: N802
        del parent
        return 2

    def rowCount(self, parent: Optional[QModelIndex] = None) -> int:  # noqa: N802
        if parent is None:
            parent = QModelIndex()

        parent_node = self._node_from_index(parent)
        if parent.isValid() and parent.column() > 0:
            return 0

        return len(parent_node.children)

    def index(  # noqa: N802
        self,
        row: int,
        column: int,
        parent: Optional[QModelIndex] = None,
    ) -> QModelIndex:
        if parent is None:
            parent = QModelIndex()

        if not self.hasIndex(row, column, parent):
            return QModelIndex()

        parent_node = self._node_from_index(parent)
        if row < 0 or row >= len(parent_node.children):
            return QModelIndex()

        return self.createIndex(row, column, parent_node.children[row])

    def parent(self, child: QModelIndex) -> QModelIndex:  # noqa: N802  # pyright: ignore[reportIncompatibleMethodOverride]
        if not child.isValid():
            return QModelIndex()

        node = self._node_from_index(child)
        parent_node = node.parent
        if parent_node is None or parent_node is self._root:
            return QModelIndex()

        return self.createIndex(parent_node.row(), 0, parent_node)

    def data(
        self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole
    ):
        if not index.isValid():
            return None

        node = self._node_from_index(index)
        if role in (
            Qt.ItemDataRole.DisplayRole,
            Qt.ItemDataRole.EditRole,
        ):
            return node.column_values[index.column()]

        if role == Qt.ItemDataRole.DecorationRole and index.column() == 0:
            return self._icon_for_node(node)

        if role == Qt.ItemDataRole.FontRole:
            if node.node_type == FeatureTreeNodeType.GROUP:
                return self._section_font

            if (
                node.node_type
                in (FeatureTreeNodeType.TAG, FeatureTreeNodeType.WARNING)
                and node.osm_tag is not None
                and node.osm_tag.has_links
                and index.column() == 1
            ):
                return self._tag_link_font

        if role == Qt.ItemDataRole.ForegroundRole:
            if (
                node.node_type
                in (FeatureTreeNodeType.TAG, FeatureTreeNodeType.WARNING)
                and node.osm_tag is not None
                and node.osm_tag.has_links
                and index.column() == 1
            ):
                return self._tag_link_brush

        if role == Qt.ItemDataRole.ToolTipRole:
            if node.node_type == FeatureTreeNodeType.TAG:
                return self._tag_links_tooltip(index)

            if node.osm_element is not None and index.column() == 0:
                return node.osm_element.osm_url

        if role == self.NODE_TYPE_ROLE:
            return node.node_type.value

        if role == self.OSM_ELEMENT_ROLE:
            return self.osm_element_for_index(index)

        if role == self.TAG_LINKS_ROLE:
            return self.tag_links_for_index(index)

        if role == self.IS_LOADING_ROLE:
            return self._node_key(node) in self._loading_keys

        return None

    def headerData(
        self, section: int, orientation: Qt.Orientation, role: int = ...
    ) -> Any:
        if (
            orientation == Qt.Orientation.Horizontal
            and role == Qt.ItemDataRole.DisplayRole
        ):
            if section == 0:
                return self.tr("Feature/Key")

            if section == 1:
                return self.tr("Value")

        return None

    def flags(self, index: QModelIndex):
        if not index.isValid():
            return Qt.ItemFlag.NoItemFlags

        return Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable

    def clear(self) -> None:
        self.beginResetModel()
        self._root.children = []
        self._feature_nodes = {}
        self._loading_keys = set()
        if self._loading_movie is not None:
            self._loading_movie.stop()
        self.endResetModel()

    def set_result_tree(self, result_tree: OsmResultTree) -> None:
        self.beginResetModel()

        self._root.children = []
        self._feature_nodes = {}
        self._loading_keys = set()
        if self._loading_movie is not None:
            self._loading_movie.stop()
        for group in result_tree.groups:
            group_node = _FeatureTreeNode(
                FeatureTreeNodeType.GROUP,
                (f"{group.title} ({len(group.elements)})", ""),
                parent=self._root,
            )
            self._root.children.append(group_node)

            for element in group.elements:
                self._set_element(group_node, element)

        self.endResetModel()

    def set_element_loading(
        self,
        element_keys: Set[Tuple[str, int]],
        is_loading: bool,
    ) -> None:
        changed_keys: Set[Tuple[str, int]] = set()
        for element_key in element_keys:
            if is_loading:
                if element_key in self._loading_keys:
                    continue

                self._loading_keys.add(element_key)
                changed_keys.add(element_key)
                continue

            if element_key not in self._loading_keys:
                continue

            self._loading_keys.remove(element_key)
            changed_keys.add(element_key)

        if len(self._loading_keys) > 0:
            loading_movie = self._ensure_loading_movie()
            if (
                loading_movie is not None
                and loading_movie.isValid()
                and loading_movie.state() != QMovie.MovieState.Running
            ):
                loading_movie.start()
        elif (
            self._loading_movie is not None
            and self._loading_movie.state() != QMovie.MovieState.NotRunning
        ):
            self._loading_movie.stop()

        for element_key in changed_keys:
            self._emit_feature_data_changed(element_key)

    def _emit_feature_data_changed(self, element_key: Tuple[str, int]) -> None:
        node = self._feature_nodes.get(element_key)
        if node is None:
            return

        row = node.row()
        if row < 0:
            return

        parent_index = QModelIndex()
        if node.parent is not None and node.parent is not self._root:
            parent_index = self.createIndex(node.parent.row(), 0, node.parent)

        top_left = self.index(row, 0, parent_index)
        bottom_right = self.index(row, self.columnCount() - 1, parent_index)
        self.dataChanged.emit(top_left, bottom_right)

    def osm_element_for_index(
        self,
        index: QModelIndex,
    ) -> Optional[OsmElement]:
        if not index.isValid():
            return None

        node = self._node_from_index(index)
        while node is not None:
            if node.osm_element is not None:
                return node.osm_element

            node = node.parent

        return None

    def tag_links_for_index(self, index: QModelIndex) -> Tuple[TagLink, ...]:
        if not index.isValid():
            return tuple()

        node = self._node_from_index(index)
        if node.osm_tag is None:
            return tuple()

        return node.osm_tag.links

    def index_for_element(self, element: OsmElement) -> Optional[QModelIndex]:
        element_key = (element.element_type.value, element.osm_id)
        for group_row in range(self.rowCount()):
            group_index = self.index(group_row, 0)
            if not group_index.isValid():
                continue

            for row in range(self.rowCount(group_index)):
                feature_index = self.index(row, 0, group_index)
                if not feature_index.isValid():
                    continue

                model_element = self.osm_element_for_index(feature_index)
                if model_element is None:
                    continue

                model_key = (
                    model_element.element_type.value,
                    model_element.osm_id,
                )
                if model_key == element_key:
                    return feature_index

        return None

    def _set_element(
        self, group_node: _FeatureTreeNode, element: OsmElement
    ) -> None:
        feature_node = _FeatureTreeNode(
            FeatureTreeNodeType.FEATURE,
            (element.title, ""),
            parent=group_node,
            osm_element=element,
        )
        group_node.children.append(feature_node)
        self._feature_nodes[(element.element_type.value, element.osm_id)] = (
            feature_node
        )

        if element.is_incomplete:
            feature_node.children.append(
                _FeatureTreeNode(
                    FeatureTreeNodeType.WARNING,
                    (
                        self.tr("Attention"),
                        self.tr(
                            "incomplete geometry (e.g. some nodes missing)"
                        ),
                    ),
                    parent=feature_node,
                )
            )

        for tag in element.tag_items:
            feature_node.children.append(
                _FeatureTreeNode(
                    FeatureTreeNodeType.TAG,
                    (tag.key, tag.value),
                    parent=feature_node,
                    osm_tag=tag,
                )
            )

    def _node_from_index(self, index: QModelIndex) -> _FeatureTreeNode:
        if index.isValid():
            return index.internalPointer()

        return self._root

    def _tag_links_tooltip(self, index: QModelIndex) -> Optional[str]:
        tag_links = self.tag_links_for_index(index)
        if len(tag_links) == 0:
            return None

        if len(tag_links) == 1:
            return tag_links[0].url

        return "\n".join(tag_link.url for tag_link in tag_links)

    def _icon_for_node(self, node: _FeatureTreeNode):
        if node.node_type == FeatureTreeNodeType.WARNING:
            return qgis_icon("mIconWarning.svg")

        if node.node_type != FeatureTreeNodeType.FEATURE:
            return None

        node_key = self._node_key(node)
        if (
            node_key is not None
            and node_key in self._loading_keys
            and self._loading_movie is not None
            and self._loading_movie.isValid()
        ):
            current_pixmap = self._loading_movie.currentPixmap()
            if not current_pixmap.isNull():
                return QIcon(current_pixmap)

        if node.osm_element is None:
            return None

        geometry_type = node.osm_element.geometry_type()
        if geometry_type is None:
            return qgis_icon("mIconGeometryCollectionLayer.svg")

        return GEOMETRY_TYPE_ICONS.get(
            geometry_type.name,
            qgis_icon("mIconGeometryCollectionLayer.svg"),
        )

    def _node_key(
        self,
        node: _FeatureTreeNode,
    ) -> Optional[Tuple[str, int]]:
        if node.osm_element is None:
            return None

        return (node.osm_element.element_type.value, node.osm_element.osm_id)

    def _on_loading_frame_changed(self) -> None:
        for element_key in self._loading_keys:
            self._emit_feature_data_changed(element_key)

    def _ensure_loading_movie(self) -> Optional[QMovie]:
        if self._loading_movie is not None:
            return self._loading_movie

        if QGuiApplication.instance() is None:
            return None

        self._loading_movie = QMovie(":images/themes/default/mIconLoading.gif")
        self._loading_movie.frameChanged.connect(
            self._on_loading_frame_changed
        )
        return self._loading_movie
