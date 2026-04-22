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

from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple, cast

from qgis.core import QgsPointXY
from qgis.PyQt.QtCore import (
    QItemSelectionModel,
    QObject,
    QPoint,
    Qt,
    QUrl,
    pyqtSlot,
)
from qgis.PyQt.QtGui import QDesktopServices
from qgis.PyQt.QtWidgets import QAction, QMainWindow
from qgis.utils import iface

from osminfo.core.constants import PLUGIN_NAME, POINT_PRECISION
from osminfo.core.exceptions import (
    OsmInfoQueryBuilderError,
    OsmInfoWizardFreeFormError,
)
from osminfo.core.logging import logger
from osminfo.core.utils import qgis_locale
from osminfo.nominatim.geocode_task import GeocodeTask
from osminfo.openstreetmap.features_parse_task import OverpassFeaturesParseTask
from osminfo.openstreetmap.features_tree_model import OsmFeaturesTreeModel
from osminfo.openstreetmap.models import OsmResultGroupType
from osminfo.osminfo_interface import OsmInfoInterface
from osminfo.overpass.endpoints import OverpassEndpoint
from osminfo.overpass.query_builder import (
    QueryBuilder,
    QueryContext,
    QueryPostprocessor,
)
from osminfo.overpass.query_task import OverpassQueryTask
from osminfo.search.identification.tool import OsmInfoMapTool
from osminfo.search.identification.tool_handler import OsmInfoToolHandler
from osminfo.search.request_feedback_tracker import (
    SearchRequestFeedbackTracker,
)
from osminfo.search.result_clipboard_exporter import (
    OsmResultClipboardExporter,
)
from osminfo.search.result_layer_exporter import OsmResultLayerExporter
from osminfo.search.result_selection import (
    OsmResultSelection,
    OsmResultSelectionItem,
)
from osminfo.search.results_context_menu import OsmResultsContextMenuBuilder
from osminfo.search.results_renderer import OsmResultsRenderer
from osminfo.search.ui.search_panel import OsmInfoSearchPanel
from osminfo.settings.osm_info_settings import OsmInfoSettings
from osminfo.ui.icon import plugin_icon

if TYPE_CHECKING:
    from qgis.gui import QgisInterface

    assert isinstance(iface, QgisInterface)


class OsmInfoSearchManager(QObject):
    _plugin: OsmInfoInterface
    _tool_action: Optional[QAction]
    _identify_tool: Optional[OsmInfoMapTool]
    _panel_action: Optional[QAction]
    _search_panel: Optional[OsmInfoSearchPanel]
    _tool_handler: Optional[OsmInfoToolHandler]
    _results_model: Optional[OsmFeaturesTreeModel]
    _result_renderer: Optional[OsmResultsRenderer]
    _clipboard_exporter: Optional[OsmResultClipboardExporter]
    _layer_exporter: Optional[OsmResultLayerExporter]
    _results_menu_builder: Optional[OsmResultsContextMenuBuilder]
    _active_query_task: Optional[OverpassQueryTask]
    _active_geocode_task: Optional[GeocodeTask]
    _active_parse_task: Optional[OverpassFeaturesParseTask]
    _active_query_kind: Optional[str]
    _pending_repaired_search: Optional[str]

    def __init__(self, parent: OsmInfoInterface) -> None:
        super().__init__(parent)

        self._plugin = parent
        self._tool_action = None
        self._identify_tool = None
        self._panel_action = None
        self._search_panel = None
        self._tool_handler = None
        self._results_model = None
        self._result_renderer = None
        self._clipboard_exporter = None
        self._layer_exporter = None
        self._results_menu_builder = None
        self._active_query_task = None
        self._active_geocode_task = None
        self._active_parse_task = None
        self._active_query_kind = None
        self._pending_repaired_search = None
        self._active_endpoint = ""
        self._pending_queries: List[Tuple[str, str, Optional[int]]] = []
        self._staged_queries: List[str] = []
        self._staged_query_kinds: List[str] = []
        self._staged_timeout_seconds: Optional[int] = None
        self._query_context: Optional[QueryContext] = None
        self._query_results: Dict[str, List[dict]] = {
            "nearby": [],
            "enclosing": [],
            "search": [],
        }
        self._is_loading = False
        self._request_feedback_tracker = SearchRequestFeedbackTracker()

    def load(self) -> None:
        self._load_search_panel()
        self._load_tool()

    def unload(self) -> None:
        self._unload_tool()
        self._unload_search_panel()

    def _load_search_panel(self) -> None:
        if self._search_panel is not None:
            return

        settings = OsmInfoSettings()
        main_window = cast(QMainWindow, iface.mainWindow())
        self._search_panel = OsmInfoSearchPanel(PLUGIN_NAME, main_window)
        self._search_panel.search.connect(self._search_by_string)
        self._search_panel.cancel.connect(self._cancel)
        self._search_panel.clear_results.connect(self._clear_results)
        self._search_panel.all_features_visibility_changed.connect(
            self._on_show_all_found_features_toggled
        )
        self._search_panel.small_features_as_points_changed.connect(
            self._on_show_small_features_as_points_toggled
        )

        self._results_model = OsmFeaturesTreeModel(self._search_panel)
        self._search_panel.results_view.setModel(self._results_model)
        self._search_panel.results_view.activated.connect(
            self._on_result_activated
        )
        self._search_panel.results_view.customContextMenuRequested.connect(
            self._open_results_menu
        )
        self._search_panel.results_view.fix_wizard_query.connect(
            self._apply_repaired_search
        )
        self._search_panel.results_view.selectionModel().selectionChanged.connect(
            self._on_result_selection_changed
        )

        self._result_renderer = OsmResultsRenderer(self)
        self._result_renderer.set_show_all_features(
            settings.show_all_found_features
        )
        self._result_renderer.set_centroid_rendering_enabled(
            settings.show_small_features_as_points
        )
        self._clipboard_exporter = OsmResultClipboardExporter(self)
        self._layer_exporter = OsmResultLayerExporter(self)
        self._results_menu_builder = OsmResultsContextMenuBuilder(
            self,
            clipboard_exporter=self._clipboard_exporter,
            layer_exporter=self._layer_exporter,
            result_renderer=self._result_renderer,
        )

        self._panel_action = QAction(
            self.tr("Show/Hide {} Panel").format(PLUGIN_NAME), self
        )
        self._panel_action.setIcon(plugin_icon())
        self._search_panel.setToggleVisibilityAction(self._panel_action)
        self._search_panel.set_show_all_found_features(
            settings.show_all_found_features
        )
        self._search_panel.set_show_small_features_as_points(
            settings.show_small_features_as_points
        )

        # This action is used in the panel list in QGIS, so we set the icon for it as well
        self._search_panel.toggleViewAction().setIcon(plugin_icon())

        iface.addPluginToWebMenu(PLUGIN_NAME, self._panel_action)
        iface.addWebToolBarIcon(self._panel_action)

        if not main_window.restoreDockWidget(self._search_panel):
            main_window.addDockWidget(
                Qt.DockWidgetArea.RightDockWidgetArea,
                self._search_panel,
            )

    def _unload_search_panel(self) -> None:
        self._cancel_active_task()
        if self._result_renderer is not None:
            self._result_renderer.unload()
            self._result_renderer = None

        self._clipboard_exporter = None
        self._layer_exporter = None
        self._results_menu_builder = None
        self._results_model = None

        if self._search_panel is not None:
            main_window = cast(QMainWindow, iface.mainWindow())
            main_window.removeDockWidget(self._search_panel)
            self._search_panel.close()
            self._search_panel.deleteLater()
            self._search_panel = None

        if self._panel_action is not None:
            iface.removePluginWebMenu(PLUGIN_NAME, self._panel_action)
            iface.removeToolBarIcon(self._panel_action)
            self._panel_action.deleteLater()
            self._panel_action = None

    def _load_tool(self) -> None:
        if self._tool_handler is not None:
            return

        self._tool_action = QAction(
            self.tr("Identify OpenStreetMap Features"),
            self,
        )
        self._tool_action.setIcon(plugin_icon("mActionIdentify.svg"))
        iface.addPluginToWebMenu(PLUGIN_NAME, self._tool_action)
        iface.addWebToolBarIcon(self._tool_action)

        self._identify_tool = OsmInfoMapTool(iface.mapCanvas())
        self._identify_tool.identify_point.connect(self._on_identify_point)

        self._tool_handler = OsmInfoToolHandler(
            self._identify_tool,
            self._tool_action,
        )
        iface.registerMapToolHandler(self._tool_handler)

    def _unload_tool(self) -> None:
        if self._tool_handler is not None:
            iface.unregisterMapToolHandler(self._tool_handler)
            self._tool_handler = None

        if self._identify_tool is not None:
            if iface.mapCanvas().mapTool() == self._identify_tool:
                iface.mapCanvas().unsetMapTool(self._identify_tool)

            self._identify_tool.deleteLater()
            self._identify_tool = None

        if self._tool_action is not None:
            iface.removePluginWebMenu(PLUGIN_NAME, self._tool_action)
            iface.removeToolBarIcon(self._tool_action)
            self._tool_action.deleteLater()
            self._tool_action = None

    @pyqtSlot(QgsPointXY)
    def _on_identify_point(self, point: QgsPointXY) -> None:
        assert self._search_panel is not None
        search_text = point.toString(POINT_PRECISION)
        self._search_panel.set_search_text(search_text)
        self._search_panel.setUserVisible(True)
        self._search_by_string(search_text)

    @pyqtSlot(str)
    def _search_by_string(self, search_text: str) -> None:
        if not search_text.strip() or self._is_loading:
            return

        self._pending_repaired_search = None
        settings = OsmInfoSettings()
        query_builder = QueryBuilder(settings)

        try:
            queries = query_builder.build_for_string(search_text)
        except OsmInfoQueryBuilderError as error:
            self._request_feedback_tracker.reset_regional_empty_results()
            repaired_search = query_builder.repair_search(search_text)
            if repaired_search is not None and repaired_search != search_text:
                self._show_repairable_error(
                    self._repairable_error_title(error),
                    repaired_search,
                    additional_info=self._repairable_error_details(error),
                )
                return

            self._show_error(error.user_message)
            return

        is_coordinate_search = query_builder.last_strategy_name == "coords"
        if is_coordinate_search:
            query_kinds = self._coordinate_query_kinds(settings)
            timeout_seconds = self._query_timeout_seconds(settings)
        else:
            query_kinds = ["search"] * len(queries)
            timeout_seconds = self._query_timeout_seconds(settings)
            assert self._search_panel is not None
            self._search_panel.save_current_search()

        self._run_queries(
            settings.overpass_url,
            query_kinds,
            queries,
            timeout_seconds,
            is_coordinate_search,
        )

    @pyqtSlot()
    def _cancel(self) -> None:
        if not self._is_loading:
            return

        self._cancel_active_task()
        if self._results_model is not None:
            self._results_model.clear()

        if self._result_renderer is not None:
            self._result_renderer.clear()

        if self._search_panel is not None:
            self._search_panel.results_view.set_default_message()

    @pyqtSlot()
    def _clear_results(self) -> None:
        self._cancel_active_task()
        if self._results_model is not None:
            self._results_model.clear()

        if self._result_renderer is not None:
            self._result_renderer.clear()

        if self._search_panel is not None:
            self._search_panel.results_view.set_default_message()

    @pyqtSlot()
    def _apply_repaired_search(self) -> None:
        if self._search_panel is None:
            return

        if self._pending_repaired_search is None:
            return

        self._search_panel.set_search_text(self._pending_repaired_search)
        self._search_panel.results_view.set_default_message()
        self._pending_repaired_search = None

    def _run_queries(
        self,
        endpoint: str,
        query_kinds: List[str],
        queries: List[str],
        timeout_seconds: Optional[int],
        is_coordinate_search: bool,
    ) -> None:
        self._cancel_active_task()
        if self._results_model is not None:
            self._results_model.clear()
        if self._result_renderer is not None:
            self._result_renderer.clear()
        self._search_panel.results_view.set_fetching_message()

        if len(endpoint) == 0:
            self._show_error(self.tr("Custom Overpass API URL is not set"))
            return

        map_canvas = iface.mapCanvas()
        if map_canvas is None:
            self._show_error(self.tr("Failed to read current map extent."))
            return

        try:
            query_context = QueryContext.from_map_canvas(map_canvas)
            geocoding_data = QueryPostprocessor.extract_geocoding_data(queries)
        except OsmInfoQueryBuilderError as error:
            self._show_error(error.user_message)
            return

        if geocoding_data.has_requests():
            self._active_endpoint = endpoint
            self._staged_queries = list(queries)
            self._staged_query_kinds = list(query_kinds)
            self._staged_timeout_seconds = timeout_seconds
            self._query_context = query_context
            self._query_results = {
                "nearby": [],
                "enclosing": [],
                "search": [],
            }
            self._start_loading()
            self._start_geocode_task(
                geocoding_data.id_queries,
                geocoding_data.area_queries,
                geocoding_data.bbox_queries,
                geocoding_data.coordinate_queries,
            )
            return

        try:
            processed_queries = QueryPostprocessor().process(
                queries,
                query_context,
            )
        except OsmInfoQueryBuilderError as error:
            self._show_error(error.user_message)
            return

        if len(processed_queries) == 0 or len(query_kinds) != len(
            processed_queries
        ):
            self._show_error(self.tr("Failed to build Overpass query"))
            return

        self._active_endpoint = endpoint
        self._pending_queries = [
            (query_kind, query, timeout_seconds)
            for query_kind, query in zip(query_kinds, processed_queries)
        ]
        self._query_results = {
            "nearby": [],
            "enclosing": [],
            "search": [],
        }
        self._start_loading()
        self._start_next_query()

    def _start_geocode_task(
        self,
        id_queries: Tuple[str, ...],
        area_queries: Tuple[str, ...],
        bbox_queries: Tuple[str, ...],
        coordinate_queries: Tuple[str, ...],
    ) -> None:
        if self._query_context is None:
            self._show_error(self.tr("Failed to read current map extent."))
            return

        task = GeocodeTask(
            self._query_context,
            id_queries,
            area_queries,
            bbox_queries,
            coordinate_queries,
        )
        task.taskCompleted.connect(self._on_geocode_task_completed)
        task.taskTerminated.connect(self._on_geocode_task_terminated)
        self._active_geocode_task = task
        self._plugin.task_manager.addTask(task)

    def _coordinate_query_kinds(
        self,
        settings: OsmInfoSettings,
    ) -> List[str]:
        query_kinds: List[str] = []
        if settings.fetch_nearby:
            query_kinds.append("nearby")

        if settings.fetch_enclosing:
            query_kinds.append("enclosing")

        return query_kinds

    def _query_timeout_seconds(
        self,
        settings: OsmInfoSettings,
    ) -> Optional[int]:
        if not settings.is_timeout_enabled:
            return None

        return settings.timeout

    def _start_loading(self) -> None:
        if self._is_loading:
            return

        self._is_loading = True
        if self._search_panel is not None:
            self._search_panel.set_loading_state(True)

        if self._identify_tool is not None:
            self._identify_tool.is_loading = True

    def _finish_loading(self) -> None:
        if not self._is_loading:
            return

        self._is_loading = False
        if self._search_panel is not None:
            self._search_panel.set_loading_state(False)

        if self._identify_tool is not None:
            self._identify_tool.is_loading = False

    def _cancel_active_task(self) -> None:
        if self._active_query_task is not None:
            self._active_query_task.cancel()

        if self._active_geocode_task is not None:
            self._active_geocode_task.cancel()

        if self._active_parse_task is not None:
            self._active_parse_task.cancel()

        self._finish_loading()
        self._reset_query_state()

    def _reset_query_state(self) -> None:
        self._active_query_task = None
        self._active_geocode_task = None
        self._active_parse_task = None
        self._active_query_kind = None
        self._pending_repaired_search = None
        self._active_endpoint = ""
        self._pending_queries = []
        self._staged_queries = []
        self._staged_query_kinds = []
        self._staged_timeout_seconds = None
        self._query_context = None
        self._query_results = {
            "nearby": [],
            "enclosing": [],
            "search": [],
        }

    def _start_next_query(self) -> None:
        if len(self._pending_queries) == 0:
            self._start_parse_task()
            return

        query_kind, query, timeout_seconds = self._pending_queries.pop(0)
        task = OverpassQueryTask(
            self._active_endpoint,
            query,
            timeout_seconds=timeout_seconds,
        )
        task.taskCompleted.connect(self._on_query_task_completed)
        task.taskTerminated.connect(self._on_query_task_terminated)

        self._active_query_task = task
        self._active_query_kind = query_kind
        self._plugin.task_manager.addTask(task)

    def _start_parse_task(self) -> None:
        if self._search_panel is not None:
            self._search_panel.results_view.set_reading_message()

        titles = {
            OsmResultGroupType.SEARCH: self.tr("Search results"),
            OsmResultGroupType.NEARBY: self.tr("Nearby features"),
            OsmResultGroupType.ENCLOSING: self.tr("Is inside"),
        }
        task = OverpassFeaturesParseTask(
            locale_name=qgis_locale(),
            nearby_elements=self._query_results["nearby"],
            enclosing_elements=self._query_results["enclosing"],
            search_elements=self._query_results["search"],
            titles=titles,
        )
        task.taskCompleted.connect(self._on_parse_task_completed)
        task.taskTerminated.connect(self._on_parse_task_terminated)
        self._active_parse_task = task
        self._plugin.task_manager.addTask(task)

    @pyqtSlot()
    def _on_geocode_task_completed(self) -> None:
        sender = self.sender()
        if sender is not self._active_geocode_task:
            return

        query_context = self._active_geocode_task.query_context
        staged_queries = list(self._staged_queries)
        staged_query_kinds = list(self._staged_query_kinds)
        timeout_seconds = self._staged_timeout_seconds
        endpoint = self._active_endpoint

        self._active_geocode_task = None
        self._staged_queries = []
        self._staged_query_kinds = []
        self._staged_timeout_seconds = None
        self._query_context = query_context

        try:
            processed_queries = QueryPostprocessor().process(
                staged_queries,
                query_context,
            )
        except OsmInfoQueryBuilderError as error:
            self._show_error(error.user_message)
            return

        if len(processed_queries) == 0 or len(staged_query_kinds) != len(
            processed_queries
        ):
            self._show_error(self.tr("Failed to build Overpass query"))
            return

        self._active_endpoint = endpoint
        self._pending_queries = [
            (query_kind, query, timeout_seconds)
            for query_kind, query in zip(
                staged_query_kinds,
                processed_queries,
            )
        ]
        self._start_next_query()

    @pyqtSlot()
    def _on_geocode_task_terminated(self) -> None:
        sender = self.sender()
        if sender is not self._active_geocode_task:
            return

        error = self._active_geocode_task.error
        self._request_feedback_tracker.reset_regional_empty_results()
        self._finish_loading()
        self._reset_query_state()
        if error is not None:
            self._show_error(error.user_message)

    @pyqtSlot()
    def _on_query_task_completed(self) -> None:
        sender = self.sender()
        if (
            sender is not self._active_query_task
            or self._active_query_kind is None
        ):
            return

        self._request_feedback_tracker.record_overpass_success()
        self._query_results[self._active_query_kind].extend(
            self._active_query_task.elements
        )
        self._active_query_task = None
        self._active_query_kind = None
        self._start_next_query()

    @pyqtSlot()
    def _on_query_task_terminated(self) -> None:
        sender = self.sender()
        if sender is not self._active_query_task:
            return

        error = self._active_query_task.error
        should_show_overpass_hint = (
            error is not None
            and self._request_feedback_tracker.record_overpass_failure()
        )

        self._finish_loading()
        self._reset_query_state()
        if error is not None:
            if should_show_overpass_hint:
                self._show_overpass_error(error.user_message)
                return

            self._show_error(error.user_message)

    @pyqtSlot()
    def _on_parse_task_completed(self) -> None:
        sender = self.sender()
        if sender is not self._active_parse_task:
            return

        result_tree = self._active_parse_task.result_tree
        active_endpoint = self._active_endpoint
        self._active_parse_task = None
        self._finish_loading()
        self._reset_query_state()

        if self._results_model is None:
            return

        if result_tree.is_empty:
            self._request_feedback_tracker.record_overpass_success()
            self._result_renderer.clear()
            self._results_model.clear()
            should_show_hint = (
                self._request_feedback_tracker.record_regional_empty_result(
                    is_empty=True,
                    is_regional_endpoint=self._is_regional_overpass_endpoint(
                        active_endpoint
                    ),
                )
            )
            if should_show_hint:
                self._search_panel.results_view.set_regional_not_found_message()
                return

            self._search_panel.results_view.set_not_found_message()
            return

        self._request_feedback_tracker.record_overpass_success()
        self._request_feedback_tracker.reset_regional_empty_results()
        self._results_model.set_result_tree(result_tree)
        if self._result_renderer is not None:
            self._result_renderer.set_result_tree(result_tree)

        if self._search_panel is not None:
            self._search_panel.results_view.clear_message()
            self._search_panel.results_view.show_root_level()

    @pyqtSlot()
    def _on_parse_task_terminated(self) -> None:
        sender = self.sender()
        if sender is not self._active_parse_task:
            return

        error = self._active_parse_task.error
        self._request_feedback_tracker.reset_regional_empty_results()
        self._finish_loading()
        self._reset_query_state()
        if error is not None:
            self._show_error(error.user_message)

    @pyqtSlot()
    def _on_result_selection_changed(self) -> None:
        if self._search_panel is None or self._result_renderer is None:
            return

        if self._results_model is None:
            return

        selection_model = self._search_panel.results_view.selectionModel()
        selected_indexes = selection_model.selectedRows(0)
        selected_elements = {}
        for selected_index in selected_indexes:
            osm_element = self._results_model.osm_element_for_index(
                selected_index
            )
            if osm_element is None:
                continue

            selected_elements[
                (osm_element.element_type.value, osm_element.osm_id)
            ] = osm_element

        self._result_renderer.set_active_elements(
            tuple(selected_elements.values())
        )

    @pyqtSlot(bool)
    def _on_show_all_found_features_toggled(self, enabled: bool) -> None:
        settings = OsmInfoSettings()
        settings.show_all_found_features = enabled

        if self._result_renderer is None:
            return

        self._result_renderer.set_show_all_features(enabled)

    @pyqtSlot(bool)
    def _on_show_small_features_as_points_toggled(
        self,
        enabled: bool,
    ) -> None:
        settings = OsmInfoSettings()
        settings.show_small_features_as_points = enabled

        if self._result_renderer is None:
            return

        self._result_renderer.set_centroid_rendering_enabled(enabled)

    @pyqtSlot()
    def _on_result_activated(self) -> None:
        if self._search_panel is None or self._results_model is None:
            return

        current_index = self._search_panel.results_view.currentIndex()
        if not current_index.isValid():
            return

        tag_links = self._results_model.tag_links_for_index(current_index)
        if len(tag_links) == 0:
            return

        self._open_url(tag_links[0].url)

    @pyqtSlot(QPoint)
    def _open_results_menu(self, position: QPoint) -> None:
        if self._search_panel is None or self._results_menu_builder is None:
            return

        selection = self._result_selection_for_context_menu(position)
        if selection is None:
            return

        menu = self._results_menu_builder.build_menu(
            self._search_panel.results_view,
            selection,
        )
        if menu is None:
            return

        menu.exec(
            self._search_panel.results_view.viewport().mapToGlobal(position)
        )

    def _result_selection_for_context_menu(
        self,
        position: QPoint,
    ) -> Optional[OsmResultSelection]:
        if self._search_panel is None or self._results_model is None:
            return None

        results_view = self._search_panel.results_view
        clicked_index = results_view.indexAt(position)
        if not clicked_index.isValid():
            return None

        clicked_row_index = clicked_index.sibling(clicked_index.row(), 0)
        selection_model = results_view.selectionModel()
        if not selection_model.isRowSelected(
            clicked_row_index.row(),
            clicked_row_index.parent(),
        ):
            selection_flag = cast(
                Any,
                getattr(
                    QItemSelectionModel,
                    "SelectionFlag",
                    QItemSelectionModel,
                ),
            )
            selection_model.select(
                clicked_row_index,
                selection_flag.ClearAndSelect | selection_flag.Rows,
            )
            results_view.setCurrentIndex(clicked_row_index)

        return self._current_result_selection(clicked_row_index)

    def _current_result_selection(
        self,
        clicked_index,
    ) -> Optional[OsmResultSelection]:
        if self._search_panel is None or self._results_model is None:
            return None

        selection_model = self._search_panel.results_view.selectionModel()
        selected_indexes = selection_model.selectedRows(0)
        selected_items_by_key: Dict[
            Tuple[str, int], OsmResultSelectionItem
        ] = {}
        for selected_index in selected_indexes:
            osm_element = self._results_model.osm_element_for_index(
                selected_index
            )
            if osm_element is None:
                continue

            item_key = (osm_element.element_type.value, osm_element.osm_id)
            if item_key in selected_items_by_key:
                continue

            selected_items_by_key[item_key] = OsmResultSelectionItem(
                element=osm_element,
            )

        clicked_element = self._results_model.osm_element_for_index(
            clicked_index
        )
        clicked_item: Optional[OsmResultSelectionItem] = None
        if clicked_element is not None:
            clicked_item = OsmResultSelectionItem(
                element=clicked_element,
            )

        selection = OsmResultSelection(
            items=tuple(selected_items_by_key.values()),
            clicked_item=clicked_item,
            clicked_tag_links=self._results_model.tag_links_for_index(
                clicked_index
            ),
            selected_row_count=len(selected_indexes),
        )
        if not selection.has_elements:
            return None

        return selection

    def _show_error(self, message: str) -> None:
        logger.error(message)
        if self._results_model is not None:
            self._results_model.clear()
        if self._result_renderer is not None:
            self._result_renderer.clear()
        self._search_panel.results_view.set_error_message(message)
        self._finish_loading()
        self._reset_query_state()

    def _show_overpass_error(self, message: str) -> None:
        logger.error(message)
        if self._results_model is not None:
            self._results_model.clear()
        if self._result_renderer is not None:
            self._result_renderer.clear()
        self._search_panel.results_view.set_overpass_error_message(message)
        self._finish_loading()
        self._reset_query_state()

    def _show_repairable_error(
        self,
        message: str,
        repaired_search: str,
        additional_info: Optional[str] = None,
    ) -> None:
        logger.error(message)
        if self._results_model is not None:
            self._results_model.clear()
        if self._result_renderer is not None:
            self._result_renderer.clear()
        self._pending_repaired_search = repaired_search
        self._search_panel.results_view.set_repairable_error_message(
            message,
            repaired_search,
            additional_info=additional_info,
        )
        self._finish_loading()

    def _repairable_error_title(
        self,
        error: OsmInfoQueryBuilderError,
    ) -> str:
        if isinstance(error, OsmInfoWizardFreeFormError):
            return self.tr("Unknown preset")

        return error.user_message

    def _repairable_error_details(
        self,
        error: OsmInfoQueryBuilderError,
    ) -> Optional[str]:
        if not isinstance(error, OsmInfoWizardFreeFormError):
            return None

        if error.search_term is None:
            return None

        return self.tr('The term "{search_term}" was not recognized.').format(
            search_term=error.search_term
        )

    def _is_regional_overpass_endpoint(self, endpoint_url: str) -> bool:
        endpoint = OverpassEndpoint.from_url(endpoint_url)
        if endpoint is None:
            return False

        return not endpoint.value.is_global

    def _open_url(self, url: str) -> None:
        QDesktopServices.openUrl(QUrl(url))
