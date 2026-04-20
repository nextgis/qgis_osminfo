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

from typing import Optional, Tuple

from qgis.core import QgsRectangle
from qgis.PyQt.QtCore import QByteArray, QObject, QUrl
from qgis.PyQt.QtGui import QDesktopServices
from qgis.PyQt.QtWidgets import QAction, QMenu, QWidget

from osminfo.openstreetmap.tag2link import TagLink
from osminfo.search.result_clipboard_exporter import (
    OsmResultClipboardExporter,
)
from osminfo.search.result_layer_exporter import OsmResultLayerExporter
from osminfo.search.result_selection import OsmResultSelection
from osminfo.search.results_renderer import OsmResultsRenderer
from osminfo.ui.icon import material_icon, plugin_icon, qgis_icon
from osminfo.ui.utils import set_clipboard_data


class OsmResultsContextMenuBuilder(QObject):
    def __init__(
        self,
        parent: Optional[QObject] = None,
        *,
        clipboard_exporter: OsmResultClipboardExporter,
        layer_exporter: OsmResultLayerExporter,
        result_renderer: OsmResultsRenderer,
    ) -> None:
        super().__init__(parent)
        self._clipboard_exporter = clipboard_exporter
        self._layer_exporter = layer_exporter
        self._result_renderer = result_renderer

    def build_menu(
        self,
        parent: QWidget,
        selection: OsmResultSelection,
    ) -> Optional[QMenu]:
        if not selection.has_elements:
            return None

        menu = QMenu(parent)
        self._add_tag_link_actions(menu, selection)
        self._add_zoom_action(menu, selection)
        self._add_copy_action(menu, selection)
        self._add_save_actions(menu, selection)
        self._add_osm_actions(menu, selection)

        if len(menu.actions()) == 0:
            return None

        return menu

    def _add_zoom_action(
        self,
        menu: QMenu,
        selection: OsmResultSelection,
    ) -> None:
        if self._result_renderer is None:
            return

        bbox = selection.combined_bbox
        if bbox is None:
            return

        action = QAction(
            plugin_icon("zoom2feature.png"),
            self._zoom_action_text(selection),
            menu,
        )
        action.triggered.connect(
            lambda checked=False, bbox=bbox: (
                self._result_renderer.zoom_to_bbox(QgsRectangle(bbox))
            )
        )
        menu.addAction(action)

    def _add_copy_action(
        self,
        menu: QMenu,
        selection: OsmResultSelection,
    ) -> None:
        if not selection.has_elements:
            return

        action = QAction(
            qgis_icon("mActionEditCopy.svg"),
            self._copy_action_text(selection),
            menu,
        )
        action.triggered.connect(
            lambda checked=False, items=selection.items: (
                self._clipboard_exporter.copy_to_clipboard(items)
            )
        )
        menu.addAction(action)

    def _add_save_actions(
        self,
        menu: QMenu,
        selection: OsmResultSelection,
    ) -> None:
        geometry_items = selection.geometry_items
        if len(geometry_items) == 0:
            return

        new_layer_action = QAction(
            qgis_icon("mActionCreateMemory.svg"),
            self._save_new_layer_text(selection),
            menu,
        )
        new_layer_action.triggered.connect(
            lambda checked=False, items=geometry_items: (
                self._layer_exporter.save_in_new_temporary_layers(items)
            )
        )
        menu.addAction(new_layer_action)

        selected_layer_action = QAction(
            qgis_icon("mActionCreateMemory.svg"),
            self._save_selected_layer_text(selection),
            menu,
        )
        selected_layer_action.setEnabled(
            self._layer_exporter.can_save_in_selected_layer(geometry_items)
        )
        selected_layer_action.triggered.connect(
            lambda checked=False, items=geometry_items: (
                self._layer_exporter.save_in_selected_layer(items)
            )
        )
        menu.addAction(selected_layer_action)

    def _add_osm_actions(
        self,
        menu: QMenu,
        selection: OsmResultSelection,
    ) -> None:
        single_element = selection.single_element
        if single_element is None:
            if not selection.has_multiple_elements:
                return

            self._add_separator(menu)
            disabled_open_action = QAction(
                plugin_icon("osm_logo.svg"),
                self.tr("Open in OpenStreetMap"),
                menu,
            )
            disabled_open_action.setEnabled(False)
            menu.addAction(disabled_open_action)

            disabled_copy_action = QAction(
                plugin_icon("osm_logo.svg"),
                self.tr("Copy OpenStreetMap URL"),
                menu,
            )
            disabled_copy_action.setEnabled(False)
            menu.addAction(disabled_copy_action)
            return

        self._add_separator(menu)
        open_action = QAction(
            plugin_icon("osm_logo.svg"),
            self.tr("Open in OpenStreetMap"),
            menu,
        )
        open_action.triggered.connect(
            lambda checked=False, url=single_element.osm_url: self._open_url(
                url
            )
        )
        menu.addAction(open_action)

        copy_action = QAction(
            plugin_icon("osm_logo.svg"),
            self.tr("Copy OpenStreetMap URL"),
            menu,
        )
        copy_action.triggered.connect(
            lambda checked=False, url=single_element.osm_url: self._copy_link(
                url
            )
        )
        menu.addAction(copy_action)

    def _add_tag_link_actions(
        self,
        menu: QMenu,
        selection: OsmResultSelection,
    ) -> None:
        if selection.selected_row_count != 1:
            return

        if len(selection.clicked_tag_links) == 0:
            return

        self._add_separator(menu)
        self._populate_tag_link_menu(menu, selection.clicked_tag_links)

    def _populate_tag_link_menu(
        self,
        menu: QMenu,
        tag_links: Tuple[TagLink, ...],
    ) -> None:
        if len(tag_links) == 1:
            tag_link = tag_links[0]
            open_link_action = QAction(self.tr("Open tag link"), menu)
            open_link_action.setIcon(material_icon("open_in_new"))
            open_link_action.triggered.connect(
                lambda checked=False, url=tag_link.url: self._open_url(url)
            )
            menu.addAction(open_link_action)

            copy_link_action = QAction(self.tr("Copy tag link"), menu)
            copy_link_action.setIcon(material_icon("link"))
            copy_link_action.triggered.connect(
                lambda checked=False, url=tag_link.url: self._copy_link(url)
            )
            menu.addAction(copy_link_action)
            return

        open_links_menu = menu.addMenu(self.tr("Open tag links"))
        copy_links_menu = menu.addMenu(self.tr("Copy tag links"))
        open_links_menu.setIcon(material_icon("open_in_new"))
        copy_links_menu.setIcon(material_icon("link"))

        for tag_link in tag_links:
            open_action = QAction(tag_link.title, open_links_menu)
            open_action.triggered.connect(
                lambda checked=False, url=tag_link.url: self._open_url(url)
            )
            open_links_menu.addAction(open_action)

            copy_action = QAction(tag_link.title, copy_links_menu)
            copy_action.triggered.connect(
                lambda checked=False, url=tag_link.url: self._copy_link(url)
            )
            copy_links_menu.addAction(copy_action)

    def _zoom_action_text(self, selection: OsmResultSelection) -> str:
        if selection.has_multiple_elements:
            return self.tr("Zoom to selected features")

        return self.tr("Zoom to feature")

    def _save_new_layer_text(self, selection: OsmResultSelection) -> str:
        if selection.has_multiple_elements:
            return self.tr("Save features in new temporary layers")

        return self.tr("Save feature in new temporary layer")

    def _copy_action_text(self, selection: OsmResultSelection) -> str:
        if selection.has_multiple_elements:
            return self.tr("Copy features to clipboard")

        return self.tr("Copy feature to clipboard")

    def _save_selected_layer_text(
        self,
        selection: OsmResultSelection,
    ) -> str:
        if selection.has_multiple_elements:
            return self.tr("Save features in selected layer")

        return self.tr("Save feature in selected layer")

    def _add_separator(self, menu: QMenu) -> None:
        if len(menu.actions()) > 0 and not menu.actions()[-1].isSeparator():
            menu.addSeparator()

    def _open_url(self, url: str) -> None:
        QDesktopServices.openUrl(QUrl(url))

    def _copy_link(self, link: str) -> None:
        data = QByteArray(link.encode("utf-8"))
        set_clipboard_data("text/plain", data, link)
