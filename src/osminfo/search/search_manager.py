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

from typing import TYPE_CHECKING, Dict, List, Optional, Set, Tuple, cast

from qgis.core import (
    Qgis,
    QgsCoordinateReferenceSystem,
    QgsCoordinateTransform,
    QgsGeometry,
    QgsPointXY,
    QgsProject,
    QgsRectangle,
)
from qgis.gui import QgsMapMouseEvent, QgsMapTool
from qgis.PyQt.QtCore import (
    QItemSelectionModel,
    QModelIndex,
    QObject,
    QPoint,
    Qt,
    QUrl,
    pyqtSlot,
)
from qgis.PyQt.QtGui import QDesktopServices
from qgis.PyQt.QtWidgets import QAction, QMainWindow, QMenu
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
from osminfo.openstreetmap.geometry_load_task import OverpassGeometryLoadTask
from osminfo.openstreetmap.models import (
    OsmElement,
    OsmResultGroupType,
    OsmResultTree,
)
from osminfo.openstreetmap.raw_elements_subset import (
    RawElementsSubsetCollector,
)
from osminfo.osminfo_interface import OsmInfoInterface
from osminfo.overpass.endpoints import OverpassEndpoint
from osminfo.overpass.query_builder import (
    QueryBuilder,
    QueryContext,
    QueryPostprocessor,
)
from osminfo.overpass.query_task import OverpassQueryTask
from osminfo.search.identification.click_renderer import (
    OsmInfoClickRenderer,
)
from osminfo.search.identification.tool import OsmInfoMapTool
from osminfo.search.identification.tool_handler import OsmInfoToolHandler
from osminfo.search.request_feedback_tracker import (
    SearchRequestFeedbackTracker,
)
from osminfo.search.result_clipboard_exporter import (
    OsmResultClipboardExporter,
)
from osminfo.search.result_layer_exporter import OsmResultLayerExporter
from osminfo.search.result_layer_store import OsmResultLayerStore
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


MAX_GEOMETRY_AREA_SQ_KM = 10.0


class OsmInfoSearchManager(QObject):
    _plugin: OsmInfoInterface
    _tool_action: Optional[QAction]
    _identify_tool: Optional[OsmInfoMapTool]
    _click_renderer: Optional[OsmInfoClickRenderer]
    _panel_action: Optional[QAction]
    _search_panel: Optional[OsmInfoSearchPanel]
    _tool_handler: Optional[OsmInfoToolHandler]
    _results_model: Optional[OsmFeaturesTreeModel]
    _result_layer_store: Optional[OsmResultLayerStore]
    _result_renderer: Optional[OsmResultsRenderer]
    _clipboard_exporter: Optional[OsmResultClipboardExporter]
    _layer_exporter: Optional[OsmResultLayerExporter]
    _results_menu_builder: Optional[OsmResultsContextMenuBuilder]
    _active_query_task: Optional[OverpassQueryTask]
    _active_geocode_task: Optional[GeocodeTask]
    _active_parse_task: Optional[OverpassFeaturesParseTask]
    _active_geometry_task: Optional[OverpassGeometryLoadTask]
    _raw_elements_subset_collector: Optional[RawElementsSubsetCollector]
    _active_query_kind: Optional[str]
    _pending_repaired_search: Optional[str]

    def __init__(self, parent: OsmInfoInterface) -> None:
        super().__init__(parent)

        self._plugin = parent
        self._tool_action = None
        self._identify_tool = None
        self._click_renderer = None
        self._panel_action = None
        self._search_panel = None
        self._tool_handler = None
        self._results_model = None
        self._result_layer_store = None
        self._result_renderer = None
        self._clipboard_exporter = None
        self._layer_exporter = None
        self._results_menu_builder = None
        self._active_query_task = None
        self._active_geocode_task = None
        self._active_parse_task = None
        self._active_geometry_task = None
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
        self._result_tree: Optional[OsmResultTree] = None
        self._raw_elements_subset_collector = None
        self._active_geometry_keys: Set[Tuple[str, int]] = set()
        self._queued_geometry_batches: List[Tuple[Tuple[str, int], ...]] = []
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
        self._search_panel.results_view.clear_selection.connect(
            self._clear_result_selection
        )
        self._search_panel.results_view.selectionModel().selectionChanged.connect(
            self._on_result_selection_changed
        )

        self._result_layer_store = OsmResultLayerStore(self)
        self._result_renderer = OsmResultsRenderer(
            self._result_layer_store,
            self,
        )
        self._result_renderer.set_show_all_features(
            settings.show_all_found_features
        )
        self._result_renderer.set_centroid_rendering_enabled(
            settings.show_small_features_as_points
        )
        map_canvas = iface.mapCanvas()
        assert map_canvas is not None
        self._click_renderer = OsmInfoClickRenderer(map_canvas, self)
        self._search_panel.visibility_changed.connect(
            self._on_visibility_changed
        )
        self._clipboard_exporter = OsmResultClipboardExporter(self)
        self._layer_exporter = OsmResultLayerExporter(self)
        self._results_menu_builder = OsmResultsContextMenuBuilder(
            self,
            clipboard_exporter=self._clipboard_exporter,
            layer_exporter=self._layer_exporter,
            result_renderer=self._result_renderer,
        )
        map_canvas.contextMenuAboutToShow.connect(
            self._on_map_canvas_context_menu_about_to_show
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

        self._result_renderer.set_visible(self._search_panel.isVisible())
        self._click_renderer.set_visible(self._search_panel.isVisible())

    def _unload_search_panel(self) -> None:
        self._cancel_active_task()
        map_canvas = iface.mapCanvas()
        map_canvas.contextMenuAboutToShow.disconnect(
            self._on_map_canvas_context_menu_about_to_show
        )

        if self._result_renderer is not None:
            self._result_renderer.unload()
            self._result_renderer = None

        if self._result_layer_store is not None:
            self._result_layer_store.unload()
            self._result_layer_store = None

        if self._click_renderer is not None:
            self._click_renderer.clear()
            self._click_renderer.deleteLater()
            self._click_renderer = None

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
        self._search_panel.set_map_tool_action(self._tool_action)

        self._identify_tool = OsmInfoMapTool(iface.mapCanvas())
        self._identify_tool.identify_point.connect(self._on_identify_point)
        self._identify_tool.toggle_selection.connect(
            self._on_append_identified_results
        )
        self._identify_tool.clear_selection.connect(
            self._clear_result_selection
        )

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

    @pyqtSlot(QPoint)
    def _on_append_identified_results(self, position: QPoint) -> None:
        elements = self._identify_result_elements_at_position(position)
        if len(elements) == 0:
            return

        self._toggle_result_element(elements[0])

    @pyqtSlot()
    def _clear_result_selection(self) -> None:
        if self._search_panel is None:
            return

        selection_model = self._search_panel.results_view.selectionModel()
        selection_model.clearSelection()
        selection_model.setCurrentIndex(
            QModelIndex(),
            QItemSelectionModel.SelectionFlag.NoUpdate,
        )

        if self._result_renderer is not None:
            self._result_renderer.set_active_elements(tuple())

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
            self._clear_click_renderer()
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
            coordinate_point = QueryBuilder.parse_coordinates(search_text)
            if coordinate_point is not None:
                self._show_search_point(coordinate_point)
            query_kinds = self._coordinate_query_kinds(settings)
            timeout_seconds = self._query_timeout_seconds(settings)
        else:
            self._clear_click_renderer()
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

        self._clear_click_renderer()

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

    def _show_search_point(self, point: QgsPointXY) -> None:
        if self._click_renderer is None:
            return

        map_canvas = iface.mapCanvas()
        if map_canvas is None:
            return

        transform = QgsCoordinateTransform(
            QgsCoordinateReferenceSystem.fromEpsgId(4326),
            map_canvas.mapSettings().destinationCrs(),
            QgsProject.instance(),
        )
        canvas_point = transform.transform(point)
        self._click_renderer.start_point_animation(canvas_point)

    def _clear_click_renderer(self) -> None:
        if self._click_renderer is None:
            return

        self._click_renderer.clear()

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

        if self._active_geometry_task is not None:
            self._active_geometry_task.cancel()

        self._finish_loading()
        self._clear_loaded_results()
        self._reset_query_state()

    def _clear_loaded_results(self) -> None:
        if self._results_model is not None:
            self._results_model.set_element_loading(
                self._active_geometry_keys | self._queued_geometry_key_set(),
                False,
            )

        self._active_geometry_task = None
        self._active_geometry_keys = set()
        self._queued_geometry_batches = []
        self._result_tree = None
        self._raw_elements_subset_collector = None

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
            geometry_area_limit_sq_km=self._initial_geometry_area_limit(),
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
        raw_elements_subset_collector = (
            self._active_parse_task.raw_elements_subset_collector
        )
        active_endpoint = self._active_endpoint
        self._active_parse_task = None
        self._finish_loading()
        self._reset_query_state()

        if self._results_model is None:
            return

        if result_tree.is_empty:
            self._clear_loaded_results()
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
        self._result_tree = result_tree
        self._raw_elements_subset_collector = raw_elements_subset_collector
        self._results_model.set_result_tree(result_tree)
        if self._result_renderer is not None:
            self._result_renderer.set_result_tree(result_tree)

        if self._search_panel is not None:
            self._search_panel.results_view.clear_message()
            self._search_panel.results_view.show_root_level()
            self._select_first_result()

        if OsmInfoSettings().show_all_found_features:
            self._request_geometry_for_all_results()

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

        selected_elements = self._selected_result_elements()
        self._request_geometry_for_elements(selected_elements)
        self._result_renderer.set_active_elements(selected_elements)

    def _select_first_result(self) -> None:
        if self._search_panel is None or self._results_model is None:
            return

        first_result_index = self._first_result_index()
        if first_result_index is None:
            return

        results_view = self._search_panel.results_view
        selection_model = results_view.selectionModel()
        selection_flag = QItemSelectionModel.SelectionFlag
        selection_model.select(
            first_result_index,
            selection_flag.ClearAndSelect | selection_flag.Rows,
        )
        results_view.setCurrentIndex(first_result_index)
        results_view.scrollTo(first_result_index)

    def _first_result_index(self):
        if self._results_model is None:
            return None

        for group_row in range(self._results_model.rowCount()):
            group_index = self._results_model.index(group_row, 0)
            if not group_index.isValid():
                continue

            if self._results_model.rowCount(group_index) == 0:
                continue

            feature_index = self._results_model.index(0, 0, group_index)
            if feature_index.isValid():
                return feature_index

        return None

    @pyqtSlot(bool)
    def _on_show_all_found_features_toggled(self, enabled: bool) -> None:
        settings = OsmInfoSettings()
        settings.show_all_found_features = enabled

        if self._result_renderer is None:
            return

        self._result_renderer.set_show_all_features(enabled)
        if enabled:
            self._request_geometry_for_all_results()

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

    def _on_map_canvas_context_menu_about_to_show(
        self,
        menu: QMenu,
        event: QgsMapMouseEvent,
    ) -> None:
        if (
            self._result_layer_store is None
            or self._result_renderer is None
            or self._results_menu_builder is None
        ):
            return

        search_geometry = self._context_menu_search_geometry(event)
        if search_geometry is None:
            return

        hits = self._result_layer_store.identify(search_geometry)
        if len(hits) == 0:
            return

        elements = self._result_renderer.elements_for_hits(hits)
        if len(elements) == 0:
            return

        selection = self._selection_for_map_context_menu_elements(elements)
        if selection is None:
            return

        results_menu = self._results_menu_builder.build_menu(menu, selection)
        if results_menu is None:
            return

        results_menu.setTitle(PLUGIN_NAME)
        results_menu.setIcon(plugin_icon())
        first_action = menu.actions()[0] if len(menu.actions()) > 0 else None
        menu.insertMenu(first_action, results_menu)

    def _context_menu_search_geometry(
        self,
        event: QgsMapMouseEvent,
    ) -> Optional[QgsGeometry]:
        return self._search_geometry_for_canvas_position(event.pos())

    def _search_geometry_for_canvas_position(
        self,
        position: QPoint,
    ) -> Optional[QgsGeometry]:
        map_canvas = iface.mapCanvas()
        if map_canvas is None:
            return None

        point = map_canvas.getCoordinateTransform().toMapCoordinates(position)
        search_radius = QgsMapTool.searchRadiusMU(map_canvas)
        search_rect = QgsRectangle(
            point.x() - search_radius,
            point.y() - search_radius,
            point.x() + search_radius,
            point.y() + search_radius,
        )
        return QgsGeometry.fromRect(search_rect)

    def _identify_result_elements_at_position(
        self,
        position: QPoint,
    ) -> Tuple[OsmElement, ...]:
        if self._result_layer_store is None or self._result_renderer is None:
            return tuple()

        search_geometry = self._search_geometry_for_canvas_position(position)
        if search_geometry is None:
            return tuple()

        hits = self._result_layer_store.identify(search_geometry)
        if len(hits) == 0:
            return tuple()

        return self._result_renderer.elements_for_hits(hits)

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
            selection_flag = QItemSelectionModel.SelectionFlag
            selection_model.select(
                clicked_row_index,
                selection_flag.ClearAndSelect | selection_flag.Rows,
            )
            results_view.setCurrentIndex(clicked_row_index)

        selected_indexes = selection_model.selectedRows(0)
        return self._selection_from_indexes(
            selected_indexes, clicked_row_index
        )

    def _selection_from_indexes(
        self,
        selected_indexes,
        clicked_index=None,
    ) -> Optional[OsmResultSelection]:
        if self._search_panel is None or self._results_model is None:
            return None

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

        clicked_item: Optional[OsmResultSelectionItem] = None
        clicked_tag_links = tuple()
        if clicked_index is not None:
            clicked_element = self._results_model.osm_element_for_index(
                clicked_index
            )
            if clicked_element is not None:
                clicked_item = OsmResultSelectionItem(
                    element=clicked_element,
                )

            clicked_tag_links = self._results_model.tag_links_for_index(
                clicked_index
            )

        selection = OsmResultSelection(
            items=tuple(selected_items_by_key.values()),
            clicked_item=clicked_item,
            clicked_tag_links=clicked_tag_links,
            selected_row_count=len(selected_indexes),
        )
        if not selection.has_elements:
            return None

        return selection

    def _selection_for_map_context_menu_elements(
        self,
        elements: Tuple[OsmElement, ...],
    ) -> Optional[OsmResultSelection]:
        current_selection = self._current_selected_result_selection()
        if self._should_use_current_selection_for_map_menu(
            current_selection,
            elements,
        ):
            return current_selection

        is_selected = self._select_result_elements(elements)
        if not is_selected:
            return None

        return self._current_selected_result_selection()

    def _current_selected_result_selection(
        self,
    ) -> Optional[OsmResultSelection]:
        if self._search_panel is None or self._results_model is None:
            return None

        selection_model = self._search_panel.results_view.selectionModel()
        return self._selection_from_indexes(selection_model.selectedRows(0))

    def _should_use_current_selection_for_map_menu(
        self,
        selection: Optional[OsmResultSelection],
        elements: Tuple[OsmElement, ...],
    ) -> bool:
        if selection is None or not selection.has_multiple_elements:
            return False

        selected_keys = {
            (item.element.element_type.value, item.element.osm_id)
            for item in selection.items
        }
        element_keys = {
            (element.element_type.value, element.osm_id)
            for element in elements
        }
        return len(selected_keys & element_keys) > 0

    def _select_result_element(
        self,
        element: OsmElement,
        clear_selection: bool = True,
    ) -> bool:
        if self._search_panel is None or self._results_model is None:
            return False

        result_index = self._results_model.index_for_element(element)
        if result_index is None:
            return False

        selection_model = self._search_panel.results_view.selectionModel()
        selection_flag = QItemSelectionModel.SelectionFlag
        selection_mode = selection_flag.Select | selection_flag.Rows
        if clear_selection:
            selection_mode |= selection_flag.ClearAndSelect

        selection_model.select(result_index, selection_mode)
        selection_model.setCurrentIndex(
            result_index,
            selection_flag.NoUpdate,
        )
        self._search_panel.results_view.scrollTo(result_index)
        self._search_panel.setUserVisible(True)
        return True

    def _select_result_elements(
        self,
        elements: Tuple[OsmElement, ...],
    ) -> bool:
        if self._search_panel is None or self._results_model is None:
            return False

        selection_model = self._search_panel.results_view.selectionModel()
        selection_flag = QItemSelectionModel.SelectionFlag
        current_index = QModelIndex()
        has_selected_elements = False
        selected_keys = set()

        for element in elements:
            element_key = (element.element_type.value, element.osm_id)
            if element_key in selected_keys:
                continue

            result_index = self._results_model.index_for_element(element)
            if result_index is None:
                continue

            selection_mode = selection_flag.Select | selection_flag.Rows
            if not has_selected_elements:
                selection_mode |= selection_flag.ClearAndSelect

            selection_model.select(result_index, selection_mode)
            current_index = result_index
            has_selected_elements = True
            selected_keys.add(element_key)

        if not has_selected_elements:
            return False

        selection_model.setCurrentIndex(
            current_index,
            selection_flag.NoUpdate,
        )
        self._search_panel.results_view.scrollTo(current_index)
        self._search_panel.setUserVisible(True)
        return True

    def _toggle_result_element(self, element: OsmElement) -> bool:
        if self._search_panel is None or self._results_model is None:
            return False

        result_index = self._results_model.index_for_element(element)
        if result_index is None:
            return False

        selection_model = self._search_panel.results_view.selectionModel()
        selection_flag = QItemSelectionModel.SelectionFlag
        is_selected = selection_model.isRowSelected(
            result_index.row(),
            result_index.parent(),
        )
        if not is_selected:
            return self._select_result_element(element, clear_selection=False)

        selection_model.select(
            result_index,
            selection_flag.Deselect | selection_flag.Rows,
        )

        selected_indexes = selection_model.selectedRows(0)
        current_index = (
            selected_indexes[-1]
            if len(selected_indexes) > 0
            else QModelIndex()
        )
        selection_model.setCurrentIndex(
            current_index,
            selection_flag.NoUpdate,
        )
        self._search_panel.setUserVisible(True)
        return True

    def _show_error(self, message: str) -> None:
        logger.error(message)
        self._clear_loaded_results()
        if self._results_model is not None:
            self._results_model.clear()
        if self._result_renderer is not None:
            self._result_renderer.clear()
        self._search_panel.results_view.set_error_message(message)
        self._finish_loading()
        self._reset_query_state()

    def _show_overpass_error(self, message: str) -> None:
        logger.error(message)
        self._clear_loaded_results()
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
        self._clear_loaded_results()
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

    def _on_visibility_changed(self, visible: bool) -> None:
        if self._result_renderer is not None:
            self._result_renderer.set_visible(visible)

        if self._click_renderer is not None:
            self._click_renderer.set_visible(visible)

    def _open_url(self, url: str) -> None:
        QDesktopServices.openUrl(QUrl(url))

    def _selected_result_elements(self) -> Tuple[OsmElement, ...]:
        if self._search_panel is None or self._results_model is None:
            return tuple()

        selection_model = self._search_panel.results_view.selectionModel()
        selected_indexes = selection_model.selectedRows(0)
        selected_elements: Dict[Tuple[str, int], OsmElement] = {}
        for selected_index in selected_indexes:
            osm_element = self._results_model.osm_element_for_index(
                selected_index
            )
            if osm_element is None:
                continue

            selected_elements[self._element_key(osm_element)] = osm_element

        return tuple(selected_elements.values())

    def _request_geometry_for_all_results(self) -> None:
        if self._result_tree is None:
            return

        self._request_geometry_for_elements(
            tuple(
                element
                for group in self._result_tree.groups
                for element in group.elements
            )
        )

    def _request_geometry_for_elements(
        self,
        elements: Tuple[OsmElement, ...],
    ) -> None:
        if self._raw_elements_subset_collector is None:
            return

        if self._raw_elements_subset_collector.is_empty():
            return

        requested_keys = self._requestable_geometry_keys(elements)
        if len(requested_keys) == 0:
            return

        if self._active_geometry_task is not None:
            if self._results_model is not None:
                self._results_model.set_element_loading(
                    set(requested_keys),
                    True,
                )
            self._queued_geometry_batches.append(requested_keys)
            return

        self._start_geometry_task(set(requested_keys))

    def _can_load_geometry(self, element: OsmElement) -> bool:
        return (
            element.geometry is None
            and element.is_geometry_deferred
            and element.raw_element is not None
        )

    def _element_key(self, element: OsmElement) -> Tuple[str, int]:
        return (element.element_type.value, element.osm_id)

    def _start_geometry_task(self, element_keys: Set[Tuple[str, int]]) -> None:
        if len(element_keys) == 0:
            return

        raw_elements = self._raw_elements_for_geometry_task(element_keys)
        if len(raw_elements) == 0:
            return

        task = OverpassGeometryLoadTask(
            qgis_locale(),
            raw_elements,
            element_keys,
        )
        task.taskCompleted.connect(self._on_geometry_task_completed)
        task.taskTerminated.connect(self._on_geometry_task_terminated)
        self._active_geometry_task = task
        self._active_geometry_keys = set(element_keys)
        if self._results_model is not None:
            self._results_model.set_element_loading(element_keys, True)
        self._plugin.task_manager.addTask(task)

    @pyqtSlot()
    def _on_geometry_task_completed(self) -> None:
        sender = self.sender()
        if sender is not self._active_geometry_task:
            return

        loaded_elements = self._active_geometry_task.parsed_elements
        loaded_keys = set(self._active_geometry_keys)
        self._active_geometry_task = None
        self._active_geometry_keys = set()
        if self._results_model is not None:
            self._results_model.set_element_loading(loaded_keys, False)

        self._apply_loaded_geometries(loaded_elements, loaded_keys)
        self._refresh_loaded_geometries()
        self._start_next_geometry_task()

    @pyqtSlot()
    def _on_geometry_task_terminated(self) -> None:
        sender = self.sender()
        if sender is not self._active_geometry_task:
            return

        error = self._active_geometry_task.error
        loaded_keys = set(self._active_geometry_keys)
        self._active_geometry_task = None
        self._active_geometry_keys = set()
        if self._results_model is not None:
            self._results_model.set_element_loading(loaded_keys, False)

        if error is not None:
            logger.error(error.user_message)
            self._plugin.notifier.display_message(
                error.user_message,
                level=Qgis.MessageLevel.Warning,
            )

        self._start_next_geometry_task()

    def _start_next_geometry_task(self) -> None:
        if self._active_geometry_task is not None:
            return

        while len(self._queued_geometry_batches) > 0:
            queued_batch = self._queued_geometry_batches.pop(0)
            filtered_batch = tuple(
                element_key
                for element_key in queued_batch
                if self._is_geometry_request_still_needed(element_key)
            )
            dropped_keys = set(queued_batch) - set(filtered_batch)
            if self._results_model is not None and len(dropped_keys) > 0:
                self._results_model.set_element_loading(dropped_keys, False)
            if len(filtered_batch) == 0:
                continue

            self._start_geometry_task(set(filtered_batch))
            return

    def _apply_loaded_geometries(
        self,
        loaded_elements: Dict[Tuple[str, int], OsmElement],
        requested_keys: Set[Tuple[str, int]],
    ) -> None:
        if self._result_tree is None:
            return

        elements_by_key = {
            self._element_key(element): element
            for group in self._result_tree.groups
            for element in group.elements
        }
        for element_key in requested_keys:
            current_element = elements_by_key.get(element_key)
            if current_element is None:
                continue

            loaded_element = loaded_elements.get(element_key)
            if loaded_element is None:
                current_element.is_geometry_deferred = False
                current_element.raw_element = None
                continue

            current_element.geometry = loaded_element.geometry
            current_element.display_geometry_type = (
                loaded_element.display_geometry_type
            )
            current_element.max_scale = loaded_element.max_scale
            current_element.bounds = loaded_element.bounds
            current_element.is_incomplete = loaded_element.is_incomplete
            current_element.is_geometry_deferred = (
                loaded_element.is_geometry_deferred
            )
            if (
                loaded_element.geometry is None
                and not loaded_element.is_geometry_deferred
            ):
                current_element.raw_element = None

    def _refresh_loaded_geometries(self) -> None:
        if self._result_tree is None or self._result_renderer is None:
            return

        self._result_renderer.set_result_tree(self._result_tree)
        self._result_renderer.set_active_elements(
            self._selected_result_elements()
        )

    def _initial_geometry_area_limit(self) -> Optional[float]:
        settings = OsmInfoSettings()
        if settings.show_all_found_features:
            return None

        return MAX_GEOMETRY_AREA_SQ_KM

    def _requestable_geometry_keys(
        self,
        elements: Tuple[OsmElement, ...],
    ) -> Tuple[Tuple[str, int], ...]:
        queued_keys = self._queued_geometry_key_set()
        requestable_keys: List[Tuple[str, int]] = []
        for element in elements:
            if not self._can_load_geometry(element):
                continue

            element_key = self._element_key(element)
            if element_key in self._active_geometry_keys:
                continue

            if element_key in queued_keys:
                continue

            requestable_keys.append(element_key)

        return tuple(requestable_keys)

    def _queued_geometry_key_set(self) -> Set[Tuple[str, int]]:
        return {
            element_key
            for batch in self._queued_geometry_batches
            for element_key in batch
        }

    def _is_geometry_request_still_needed(
        self,
        element_key: Tuple[str, int],
    ) -> bool:
        if self._result_tree is None:
            return False

        for group in self._result_tree.groups:
            for element in group.elements:
                if self._element_key(element) != element_key:
                    continue

                return self._can_load_geometry(element)

        return False

    def _raw_elements_for_geometry_task(
        self,
        element_keys: Set[Tuple[str, int]],
    ) -> Tuple[dict, ...]:
        requested_raw_elements: List[dict] = []
        for element_key in element_keys:
            raw_element = self._raw_element_for_geometry_key(element_key)
            if raw_element is None:
                continue

            requested_raw_elements.append(raw_element)

        if len(requested_raw_elements) == 0:
            return tuple()

        if self._raw_elements_subset_collector is None:
            return tuple()

        return self._raw_elements_subset_collector.collect_geometry_subset(
            requested_raw_elements
        )

    def _raw_element_for_geometry_key(
        self,
        element_key: Tuple[str, int],
    ) -> Optional[dict]:
        if self._raw_elements_subset_collector is None:
            return None

        return self._raw_elements_subset_collector.raw_element_for_key(
            element_key
        )
