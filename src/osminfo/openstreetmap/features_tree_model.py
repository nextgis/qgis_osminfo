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
from typing import Any, List, Optional, Tuple

from qgis.core import QgsApplication
from qgis.PyQt.QtCore import QAbstractItemModel, QModelIndex, Qt
from qgis.PyQt.QtGui import QBrush, QFont, QPalette

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
        self.endResetModel()

    def set_result_tree(self, result_tree: OsmResultTree) -> None:
        self.beginResetModel()

        self._root.children = []
        for group in result_tree.groups:
            group_node = _FeatureTreeNode(
                FeatureTreeNodeType.GROUP,
                (group.title, ""),
                parent=self._root,
            )
            self._root.children.append(group_node)

            for element in group.elements:
                self._set_element(group_node, element)

        self.endResetModel()

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

        if node.osm_element is None:
            return None

        geometry_type = node.osm_element.geometry_type()
        if geometry_type is None:
            return qgis_icon("mIconGeometryCollectionLayer.svg")

        return GEOMETRY_TYPE_ICONS.get(
            geometry_type.name,
            qgis_icon("mIconGeometryCollectionLayer.svg"),
        )
