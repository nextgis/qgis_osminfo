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

from typing import Any, Callable, Optional, Sequence, Tuple

from qgis.core import QgsRectangle
from qgis.PyQt.QtCore import QByteArray, QObject, QUrl
from qgis.PyQt.QtGui import QDesktopServices
from qgis.PyQt.QtWidgets import QAction, QMenu, QWidget

from osminfo.core.constants import PLUGIN_NAME
from osminfo.openstreetmap.models import OsmElement
from osminfo.openstreetmap.tag2link import TagLink
from osminfo.search.result_clipboard_exporter import (
    OsmResultClipboardExporter,
)
from osminfo.search.result_layer_exporter import OsmResultLayerExporter
from osminfo.search.result_selection import (
    OsmResultSelection,
    OsmResultSelectionItem,
)
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

    def add_identified_results_menu(
        self,
        menu: QMenu,
        elements: Sequence[OsmElement],
        select_element_handler: Optional[Callable[[OsmElement], Any]] = None,
        hovered_element_handler: Optional[Callable[[OsmElement], Any]] = None,
        menu_destroyed_handler: Optional[Callable[[], Any]] = None,
    ) -> Optional[QMenu]:
        if len(elements) == 0:
            return None

        results_menu = QMenu(PLUGIN_NAME, menu)
        results_menu.setIcon(plugin_icon())
        if menu_destroyed_handler is not None:
            results_menu.destroyed.connect(lambda *_: menu_destroyed_handler())

        if len(elements) == 1:
            self._add_identified_element_actions(
                results_menu,
                elements[0],
                select_element_handler=select_element_handler,
            )
            return results_menu

        for element in elements:
            element_menu = results_menu.addMenu(
                self._element_menu_title(element)
            )
            assert element_menu is not None
            if hovered_element_handler is not None:
                element_menu.menuAction().hovered.connect(
                    lambda element=element: hovered_element_handler(element)
                )
            self._add_identified_element_actions(
                element_menu,
                element,
                select_element_handler=select_element_handler,
            )

        return results_menu

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

    def _add_identified_element_actions(
        self,
        menu: QMenu,
        element: OsmElement,
        select_element_handler: Optional[Callable[[OsmElement], None]] = None,
    ) -> None:
        item = OsmResultSelectionItem(element=element)
        if select_element_handler is not None:
            select_action = QAction(
                plugin_icon(),
                self.tr("Select feature in search panel"),
                menu,
            )
            select_action.triggered.connect(
                lambda checked=False, element=element: (
                    select_element_handler(element)
                )
            )
            menu.addAction(select_action)
            self._add_separator(menu)

        new_layer_action = QAction(
            qgis_icon("mActionCreateMemory.svg"),
            self.tr("Add feature to new temporary layer"),
            menu,
        )
        new_layer_action.triggered.connect(
            lambda checked=False, item=item: (
                self._layer_exporter.save_in_new_temporary_layers((item,))
            )
        )
        menu.addAction(new_layer_action)

        selected_layer_action = QAction(
            qgis_icon("mActionCreateMemory.svg"),
            self.tr("Add feature to active layer"),
            menu,
        )
        selected_layer_action.setEnabled(
            self._layer_exporter.can_save_in_selected_layer((item,))
        )
        selected_layer_action.triggered.connect(
            lambda checked=False, item=item: (
                self._layer_exporter.save_in_selected_layer((item,))
            )
        )
        menu.addAction(selected_layer_action)

        self._add_separator(menu)

        open_action = QAction(
            plugin_icon("osm_logo.svg"),
            self.tr("Open in OpenStreetMap"),
            menu,
        )
        open_action.triggered.connect(
            lambda checked=False, url=element.osm_url: self._open_url(url)
        )
        menu.addAction(open_action)

        copy_action = QAction(
            plugin_icon("osm_logo.svg"),
            self.tr("Copy OpenStreetMap URL"),
            menu,
        )
        copy_action.triggered.connect(
            lambda checked=False, url=element.osm_url: self._copy_link(url)
        )
        menu.addAction(copy_action)

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

    def _element_menu_title(self, element: OsmElement) -> str:
        if len(element.title) == 0:
            return f"{element.element_type.value} #{element.osm_id}"

        return element.title

    def _open_url(self, url: str) -> None:
        QDesktopServices.openUrl(QUrl(url))

    def _copy_link(self, link: str) -> None:
        data = QByteArray(link.encode("utf-8"))
        set_clipboard_data("text/plain", data, link)
