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
        self.__init_ui()
        self.__init_settings()
        self._task = None

    def apply(self) -> None:
        self.__apply_settings()

    def cancel(self) -> None:
        pass

    def __init_ui(self) -> None:
        self.__load_ui()

        for endpoint in OverpassEndpoint:
            self.__widget.endpoint_combobox.addItem(
                endpoint.value.name,
                endpoint.value.url,
            )

        self.check_endpoint_button = LoadingToolButton(
            ":images/themes/default/mIconLoading.gif", self.__widget
        )
        self.check_endpoint_button.setIcon(material_icon("stethoscope"))
        self.check_endpoint_button.setToolTip(
            self.tr("Check connection to the selected Overpass API instance")
        )
        self.check_endpoint_button.clicked.connect(self.__check_endpoint)
        self.__widget.endpoint_layout.addWidget(self.check_endpoint_button)

        wiki_button = QToolButton(self.__widget)
        wiki_button.setIcon(plugin_icon("osm_logo.svg"))
        wiki_button.setToolTip(
            self.tr("Open OSM Wiki page with Overpass API instances list")
        )
        wiki_button.clicked.connect(self.__open_osm_wiki)
        self.__widget.endpoint_layout.addWidget(wiki_button)

        layout = QHBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setMargin(0)  # type: ignore
        self.setLayout(layout)
        layout.addWidget(self.__widget)

    def __load_ui(self) -> None:
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

        self.__widget = widget
        self.__widget.setParent(self)

    def __init_settings(self) -> None:
        settings = OsmInfoSettings()
        self.__widget.endpoint_combobox.setCurrentIndex(
            self.__widget.endpoint_combobox.findData(
                settings.overpass_endpoint
            )
        )
        self.__widget.nearby_checkbox.setChecked(settings.fetch_nearby)
        self.__widget.enclosing_checkbox.setChecked(settings.fetch_enclosing)
        self.__widget.timeout_spinbox.setValue(settings.timeout)
        self.__widget.distance_spinbox.setValue(settings.distance)
        self.__widget.debug_checkbox.setChecked(settings.is_debug_enabled)

    def __apply_settings(self):
        settings = OsmInfoSettings()
        settings.overpass_endpoint = (
            self.__widget.endpoint_combobox.currentData()
        )
        settings.fetch_enclosing = self.__widget.enclosing_checkbox.isChecked()
        settings.fetch_nearby = self.__widget.nearby_checkbox.isChecked()
        settings.timeout = self.__widget.timeout_spinbox.value()
        settings.distance = self.__widget.distance_spinbox.value()

        old_debug_enabled = settings.is_debug_enabled
        new_debug_enabled = self.__widget.debug_checkbox.isChecked()
        settings.is_debug_enabled = new_debug_enabled
        if old_debug_enabled != new_debug_enabled:
            debug_state = "enabled" if new_debug_enabled else "disabled"
            update_logging_level()
            logger.info(f"Debug messages are now {debug_state}")

    @pyqtSlot()
    def __check_endpoint(self) -> None:
        self.check_endpoint_button.start()
        self.__widget.endpoint_combobox.setEnabled(False)
        self.__widget.message_bar.clearWidgets()

        if self._task is not None and not self._task.status() not in (
            HealthCheckTask.TaskStatus.Complete,
            HealthCheckTask.TaskStatus.Terminated,
        ):
            return

        self._task = HealthCheckTask(
            self.__widget.endpoint_combobox.currentData(),
        )
        self._task.taskCompleted.connect(self.__check_endpoint_finished)
        self._task.taskTerminated.connect(self.__check_endpoint_finished)
        QgsApplication.taskManager().addTask(self._task)

    @pyqtSlot()
    def __check_endpoint_finished(self) -> None:
        self.check_endpoint_button.stop()
        self.__widget.endpoint_combobox.setEnabled(True)

        if self._task is None:
            return

        if self._task.check_status == HealthCheckStatus.SUCCESS:
            self.__widget.message_bar.pushMessage(
                self.tr("Connection successful"),
                self.tr("Successfully connected to the Overpass API instance."),
                level=Qgis.MessageLevel.Success,
            )
        elif self._task.check_status == HealthCheckStatus.WARNING:
            self.__widget.message_bar.pushMessage(
                self.tr("Connection check completed with warnings"),
                self.tr(
                    "Connected to the Overpass API instance, but some issues were detected. Please check the log for details."
                ),
                level=Qgis.MessageLevel.Warning,
            )
        elif self._task.check_status == HealthCheckStatus.FAILURE:
            self.__widget.message_bar.pushMessage(
                self.tr("Connection failed"),
                self.tr(
                    "Failed to connect to the Overpass API instance. Please check the log for details."
                ),
                level=Qgis.MessageLevel.Critical,
            )

        self._task = None

    @pyqtSlot()
    def __open_osm_wiki(self) -> None:
        QDesktopServices.openUrl(
            QUrl(
                "https://wiki.openstreetmap.org/wiki/Overpass_API#Public_Overpass_API_instances"
            )
        )


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
