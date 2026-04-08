from pathlib import Path
from typing import List, Optional

from qgis.core import Qgis, QgsApplication
from qgis.gui import (
    QgsOptionsPageWidget,
    QgsOptionsWidgetFactory,
)
from qgis.PyQt import uic
from qgis.PyQt.QtCore import Qt, QUrl, pyqtSlot
from qgis.PyQt.QtGui import QDesktopServices
from qgis.PyQt.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from osminfo.logging import logger, update_logging_level
from osminfo.overpass.endpoints import OverpassEndpoint
from osminfo.overpass.healthcheck_task import (
    HealthCheckStatus,
    HealthCheckTask,
)
from osminfo.settings.osm_info_settings import OsmInfoSettings
from osminfo.ui.icon import material_icon, plugin_icon
from osminfo.ui.loading_tool_button import LoadingToolButton


class OsmInfoOptionsPageWidget(QgsOptionsPageWidget):
    widget: QWidget

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.__init__ui()
        self.__init__settings()
        self._task = None

    def __del__(self):
        self._finish_task()

    def apply(self) -> None:
        self._apply_settings()
        self._finish_task()

    def cancel(self) -> None:
        self._finish_task()

    def __init__ui(self) -> None:
        self._load_ui()

        for endpoint in OverpassEndpoint:
            self._widget.endpoint_combobox.addItem(
                endpoint.value.name,
                endpoint.value.service_id,
            )

        self._widget.endpoint_combobox.currentIndexChanged.connect(
            self._on_endpoint_changed
        )

        self.check_endpoint_button = LoadingToolButton(
            ":images/themes/default/mIconLoading.gif",
            material_icon("stethoscope"),
            None,
            self._widget,
        )
        self.check_endpoint_button.setToolTip(
            self.tr("Check connection to the selected Overpass API instance")
        )
        self.check_endpoint_button.clicked.connect(self._check_endpoint)
        self.check_endpoint_button.setFixedSize(
            self._widget.endpoint_combobox.sizeHint().height(),
            self._widget.endpoint_combobox.sizeHint().height(),
        )
        self._widget.endpoint_layout.addWidget(self.check_endpoint_button)

        wiki_button = QToolButton(self._widget)
        wiki_button.setIcon(plugin_icon("osm_logo.svg"))
        wiki_button.setToolTip(
            self.tr("Open OSM Wiki page with Overpass API instances list")
        )
        wiki_button.clicked.connect(self._open_osm_wiki)
        wiki_button.setFixedSize(
            self._widget.endpoint_combobox.sizeHint().height(),
            self._widget.endpoint_combobox.sizeHint().height(),
        )
        self._widget.endpoint_layout.addWidget(wiki_button)

        self._widget.custom_endpoint_lineedit.setPlaceholderText(
            OverpassEndpoint.MAIN.value.url
        )

        layout = QHBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setMargin(0)  # type: ignore
        self.setLayout(layout)
        layout.addWidget(self._widget)

    def _load_ui(self) -> None:
        plugin_path = Path(__file__).parents[1]
        widget: Optional[QWidget] = None
        try:
            widget = uic.loadUi(
                str(plugin_path / "ui" / "osm_info_settings_page_base.ui")
            )  # type: ignore
        except FileNotFoundError as error:
            message = self.tr("An error occured while settings UI loading")
            logger.exception(message)
            raise RuntimeError(message) from error
        if widget is None:
            message = self.tr("An error occured in settings UI")
            logger.error(message)
            raise RuntimeError(message)

        self._widget = widget
        self._widget.setParent(self)

    def __init__settings(self) -> None:
        settings = OsmInfoSettings()
        current_index = self._widget.endpoint_combobox.findData(
            settings.overpass_endpoint
        )
        if current_index < 0:
            current_index = self._widget.endpoint_combobox.findData(
                OverpassEndpoint.MAIN.value.service_id
            )

        self._widget.endpoint_combobox.setCurrentIndex(current_index)
        self._widget.custom_endpoint_lineedit.setText(settings.custom_endpoint)
        self._update_custom_endpoint_widget_visibility()
        self._widget.nearby_checkbox.setChecked(settings.fetch_nearby)
        self._widget.enclosing_checkbox.setChecked(settings.fetch_enclosing)
        self._widget.timeout_spinbox.setValue(settings.timeout)
        self._widget.distance_spinbox.setValue(settings.distance)
        self._widget.debug_checkbox.setChecked(settings.is_debug_enabled)

    def _apply_settings(self):
        settings = OsmInfoSettings()
        settings.overpass_endpoint = self._selected_service_id()
        settings.custom_endpoint = (
            self._widget.custom_endpoint_lineedit.text().strip()
        )
        settings.fetch_enclosing = self._widget.enclosing_checkbox.isChecked()
        settings.fetch_nearby = self._widget.nearby_checkbox.isChecked()
        settings.timeout = self._widget.timeout_spinbox.value()
        settings.distance = self._widget.distance_spinbox.value()

        old_debug_enabled = settings.is_debug_enabled
        new_debug_enabled = self._widget.debug_checkbox.isChecked()
        settings.is_debug_enabled = new_debug_enabled
        if old_debug_enabled != new_debug_enabled:
            debug_state = "enabled" if new_debug_enabled else "disabled"
            update_logging_level()
            logger.info(f"Debug messages are now {debug_state}")

    @pyqtSlot()
    def _check_endpoint(self) -> None:
        self._widget.message_bar.clearWidgets()

        if self._task is not None and self._task.status() not in (
            HealthCheckTask.TaskStatus.Complete,
            HealthCheckTask.TaskStatus.Terminated,
        ):
            return

        overpass_url = self._selected_overpass_url()
        if len(overpass_url) == 0:
            self._widget.message_bar.pushMessage(
                self.tr("Connection failed"),
                self.tr("Please enter a custom Overpass API URL."),
                level=Qgis.MessageLevel.Critical,
            )
            return

        self.check_endpoint_button.start()
        self._set_endpoint_controls_enabled(False)

        self._task = HealthCheckTask(overpass_url)
        self._task.taskCompleted.connect(self._check_endpoint_finished)
        self._task.taskTerminated.connect(self._check_endpoint_finished)
        QgsApplication.taskManager().addTask(self._task)

    @pyqtSlot()
    def _check_endpoint_finished(self) -> None:
        self.check_endpoint_button.stop()
        self._set_endpoint_controls_enabled(True)

        if self._task is None:
            return

        if self._task.check_status == HealthCheckStatus.SUCCESS:
            self._widget.message_bar.pushMessage(
                self.tr("Connection successful"),
                self.tr(
                    "Successfully connected to the Overpass API instance."
                ),
                level=Qgis.MessageLevel.Success,
            )
        elif self._task.check_status == HealthCheckStatus.WARNING:
            self._widget.message_bar.pushMessage(
                self.tr("Connection check completed with warnings"),
                self.tr(
                    "Connected to the Overpass API instance, but some issues were detected. Please check the log for details."
                ),
                level=Qgis.MessageLevel.Warning,
            )
        elif self._task.check_status == HealthCheckStatus.FAILURE:
            self._widget.message_bar.pushMessage(
                self.tr("Connection failed"),
                self.tr(
                    "Failed to connect to the Overpass API instance. Please check the log for details."
                ),
                level=Qgis.MessageLevel.Critical,
            )

        self._finish_task()

    @pyqtSlot(int)
    def _on_endpoint_changed(self, _: int) -> None:
        self._update_custom_endpoint_widget_visibility()

    def _update_custom_endpoint_widget_visibility(self) -> None:
        is_custom_endpoint = (
            self._selected_service_id()
            == OverpassEndpoint.CUSTOM.value.service_id
        )
        self._widget.custom_endpoint_widget.setVisible(is_custom_endpoint)

    def _selected_service_id(self) -> str:
        current_data = self._widget.endpoint_combobox.currentData()
        if isinstance(current_data, str) and len(current_data) > 0:
            return current_data

        return OverpassEndpoint.MAIN.value.service_id

    def _selected_overpass_url(self) -> str:
        return OsmInfoSettings.resolve_overpass_url(
            self._selected_service_id(),
            self._widget.custom_endpoint_lineedit.text(),
        )

    def _set_endpoint_controls_enabled(self, is_enabled: bool) -> None:
        self._widget.endpoint_combobox.setEnabled(is_enabled)
        self._widget.custom_endpoint_lineedit.setEnabled(is_enabled)

    @pyqtSlot()
    def _open_osm_wiki(self) -> None:
        QDesktopServices.openUrl(
            QUrl(
                "https://wiki.openstreetmap.org/wiki/Overpass_API#Public_Overpass_API_instances"
            )
        )

    def _finish_task(self) -> None:
        if self._task is not None and self._task.status() not in (
            HealthCheckTask.TaskStatus.Complete,
            HealthCheckTask.TaskStatus.Terminated,
        ):
            self._task.cancel()

        self._task = None


class OsmInfoOptionsErrorPageWidget(QgsOptionsPageWidget):
    widget: QWidget

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.widget = QLabel(self.tr("Settings dialog was crashed"), self)
        self.widget.setAlignment(Qt.AlignmentFlag.AlignCenter)

        layout = QVBoxLayout()
        self.setLayout(layout)
        layout.addWidget(self.widget)

    def apply(self) -> None:
        pass

    def cancel(self) -> None:
        pass


class OsmInfoOptionsWidgetFactory(QgsOptionsWidgetFactory):
    def __init__(self):
        super().__init__(
            "OSMInfo",
            plugin_icon("osminfo.svg"),
        )

    def path(self) -> List[str]:
        return ["NextGIS"]

    def createWidget(
        self, parent: Optional[QWidget] = None
    ) -> Optional[QgsOptionsPageWidget]:
        try:
            return OsmInfoOptionsPageWidget(parent)
        except Exception:
            # logger.exception("Settings dialog was crashed")
            return OsmInfoOptionsErrorPageWidget(parent)
