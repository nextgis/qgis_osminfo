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

from html import escape
from pathlib import Path
from typing import List, Optional

from qgis.core import Qgis
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

from osminfo.core.exceptions import OsmInfoUiLoadError
from osminfo.logging import logger, update_logging_level
from osminfo.notifier.message_bar_notifier import MessageBarNotifier
from osminfo.osminfo_interface import OsmInfoInterface
from osminfo.overpass.endpoints import OverpassEndpoint, OverpassEndpointInfo
from osminfo.overpass.healthcheck_task import (
    HealthCheckStatus,
    HealthCheckTask,
)
from osminfo.settings.osm_info_settings import OsmInfoSettings
from osminfo.ui.icon import material_icon, plugin_icon
from osminfo.ui.loading_tool_button import LoadingToolButton

OVERPASS_INSTANCES_WIKI_URL = (
    "https://wiki.openstreetmap.org/wiki/Overpass_API"
    "#Public_Overpass_API_instances"
)


class OsmInfoOptionsPageWidget(QgsOptionsPageWidget):
    widget: QWidget

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.__init__ui()
        self.__init__settings()
        self._task = None
        self._notifier = MessageBarNotifier(self, self._widget.message_bar)

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
        self._widget.nearby_checkbox.toggled.connect(
            self._update_distance_controls_enabled
        )
        self._widget.timeout_checkbox.toggled.connect(
            self._update_timeout_controls_enabled
        )
        self._widget.max_size_checkbox.toggled.connect(
            self._update_max_size_controls_enabled
        )
        self._init_tooltips()
        self._widget.info_label.setTextFormat(Qt.TextFormat.RichText)
        self._widget.info_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextBrowserInteraction
        )
        self._widget.info_label.setOpenExternalLinks(True)
        self._widget.info_label.setWordWrap(True)

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
            message = self.tr("Failed to load settings UI")
            logger.exception(message)
            raise OsmInfoUiLoadError(
                log_message=message,
                user_message=message,
            ) from error
        if widget is None:
            log_message = "Settings UI loading returned no widget"
            user_message = self.tr("Failed to load settings UI")
            logger.error(log_message)
            raise OsmInfoUiLoadError(
                log_message=log_message,
                user_message=user_message,
            )

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
        self._update_endpoint_info_label()
        self._widget.nearby_checkbox.setChecked(settings.fetch_nearby)
        self._widget.enclosing_checkbox.setChecked(settings.fetch_enclosing)
        self._widget.timeout_checkbox.setChecked(settings.is_timeout_enabled)
        self._widget.timeout_spinbox.setValue(settings.timeout)
        self._widget.max_size_checkbox.setChecked(settings.is_max_size_enabled)
        self._widget.max_size_spinbox.setValue(settings.max_size_megabytes)
        self._widget.distance_spinbox.setValue(settings.distance)
        self._widget.debug_checkbox.setChecked(settings.is_debug_enabled)
        self._update_distance_controls_enabled(
            self._widget.nearby_checkbox.isChecked()
        )
        self._update_timeout_controls_enabled(
            self._widget.timeout_checkbox.isChecked()
        )
        self._update_max_size_controls_enabled(
            self._widget.max_size_checkbox.isChecked()
        )

    def _apply_settings(self):
        settings = OsmInfoSettings()
        settings.overpass_endpoint = self._selected_service_id()
        settings.custom_endpoint = (
            self._widget.custom_endpoint_lineedit.text().strip()
        )
        settings.fetch_enclosing = self._widget.enclosing_checkbox.isChecked()
        settings.fetch_nearby = self._widget.nearby_checkbox.isChecked()
        settings.is_timeout_enabled = self._widget.timeout_checkbox.isChecked()
        settings.timeout = self._widget.timeout_spinbox.value()
        settings.is_max_size_enabled = (
            self._widget.max_size_checkbox.isChecked()
        )
        settings.max_size_megabytes = self._widget.max_size_spinbox.value()
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
            self._notifier.display_message(
                self.tr("Please enter a custom Overpass API URL"),
                header=self.tr("Connection failed"),
                level=Qgis.MessageLevel.Critical,
            )
            return

        self.check_endpoint_button.start()
        self._set_endpoint_controls_enabled(False)

        self._task = HealthCheckTask(overpass_url)
        self._task.taskCompleted.connect(self._check_endpoint_finished)
        self._task.taskTerminated.connect(self._check_endpoint_finished)
        OsmInfoInterface.instance().task_manager.addTask(self._task)

    @pyqtSlot()
    def _check_endpoint_finished(self) -> None:
        self.check_endpoint_button.stop()
        self._set_endpoint_controls_enabled(True)

        if self._task is None:
            return

        if self._task.check_status in (
            HealthCheckStatus.SUCCESS,
            HealthCheckStatus.WARNING,
        ):
            self._notifier.display_message(
                self.tr("Successfully connected to the Overpass API instance"),
                header=self.tr("Connection successful"),
                level=Qgis.MessageLevel.Success,
            )
        # elif self._task.check_status == HealthCheckStatus.WARNING:
        #     self._notifier.display_message(
        #         self.tr("Connection check completed with warnings"),
        #         header=self.tr("Connection check completed with warnings"),
        #         level=Qgis.MessageLevel.Warning,
        #     )
        elif self._task.check_status == HealthCheckStatus.FAILURE:
            self._notifier.display_message(
                self.tr("Failed to connect to the Overpass API instance"),
                header=self.tr("Connection failed"),
                level=Qgis.MessageLevel.Critical,
            )

        self._finish_task()

    @pyqtSlot(int)
    def _on_endpoint_changed(self, _: int) -> None:
        self._update_custom_endpoint_widget_visibility()
        self._update_endpoint_info_label()

    def _init_tooltips(self) -> None:
        timeout_tooltip = self.tr(
            "Enable a custom Overpass query timeout. When disabled, the "
            "server default timeout is used."
        )
        max_size_tooltip = self.tr(
            "Enable a custom maximum Overpass response size. When disabled, "
            "the server default limit is used."
        )

        self._set_tooltip_for_widgets(
            timeout_tooltip,
            [
                self._widget.timeout_label,
                self._widget.timeout_checkbox,
                self._widget.timeout_spinbox,
            ],
        )
        self._set_tooltip_for_widgets(
            max_size_tooltip,
            [
                self._widget.max_size_label,
                self._widget.max_size_checkbox,
                self._widget.max_size_spinbox,
            ],
        )

    def _set_tooltip_for_widgets(
        self,
        tooltip: str,
        widgets: List[QWidget],
    ) -> None:
        for widget in widgets:
            widget.setToolTip(tooltip)

    @pyqtSlot(bool)
    def _update_distance_controls_enabled(self, is_enabled: bool) -> None:
        self._widget.distance_label.setEnabled(is_enabled)
        self._widget.distance_spinbox.setEnabled(is_enabled)

    @pyqtSlot(bool)
    def _update_timeout_controls_enabled(self, is_enabled: bool) -> None:
        self._widget.timeout_spinbox.setEnabled(is_enabled)

    @pyqtSlot(bool)
    def _update_max_size_controls_enabled(self, is_enabled: bool) -> None:
        self._widget.max_size_spinbox.setEnabled(is_enabled)

    def _update_custom_endpoint_widget_visibility(self) -> None:
        is_custom_endpoint = (
            self._selected_service_id()
            == OverpassEndpoint.CUSTOM.value.service_id
        )
        self._widget.custom_endpoint_widget.setVisible(is_custom_endpoint)

    def _update_endpoint_info_label(self) -> None:
        selected_endpoint = self._selected_endpoint()
        is_custom_endpoint = selected_endpoint == OverpassEndpoint.CUSTOM
        self._widget.info_label.setVisible(not is_custom_endpoint)

        if is_custom_endpoint:
            self._widget.info_label.clear()
            return

        self._widget.info_label.setText(
            self._build_endpoint_info_html(selected_endpoint)
        )

    def _selected_endpoint(self) -> OverpassEndpoint:
        selected_endpoint = OverpassEndpoint.from_service_id(
            self._selected_service_id()
        )
        if selected_endpoint is None:
            return OverpassEndpoint.MAIN

        return selected_endpoint

    def _build_endpoint_info_html(self, endpoint: OverpassEndpoint) -> str:
        endpoint_info = endpoint.value
        lines = []

        lines.append('<table cellspacing="4" cellpadding="0">')

        if endpoint_info.project_url is not None:
            lines.append(
                self._build_info_row_html(
                    self.tr("Project"),
                    self._build_link_html(
                        endpoint_info.project_url,
                        endpoint_info.project_url,
                    ),
                )
            )

        lines.append(
            self._build_info_row_html(
                self.tr("Coverage"),
                escape(endpoint_info.data_coverage),
            )
        )

        if endpoint_info.overpass_turbo_url is not None:
            lines.append(
                self._build_info_row_html(
                    self.tr("Overpass Turbo"),
                    self._build_link_html(
                        endpoint_info.overpass_turbo_url,
                        endpoint_info.overpass_turbo_url,
                    ),
                )
            )

        lines.append(
            self._build_info_row_html(
                self.tr("Endpoint"),
                self._build_link_html(
                    endpoint_info.url,
                    endpoint_info.url,
                ),
            )
        )

        if endpoint_info.note is not None:
            lines.append(
                self._build_info_row_html(
                    self.tr("Note"),
                    f"<i>{escape(endpoint_info.note)}</i>",
                )
            )

        if endpoint_info.usage_policy is not None:
            lines.append(
                self._build_info_row_html(
                    self.tr("Usage policy"),
                    escape(endpoint_info.usage_policy),
                )
            )

        if endpoint_info.contact is not None:
            lines.append(
                self._build_info_row_html(
                    self.tr("Contact"),
                    self._build_contact_html(endpoint_info),
                )
            )
        lines.append("</table>")

        lines.append("<br><br>")

        lines.append(
            self.tr(
                "For more details, check the <a href='{wiki_url}'>OSM Wiki</a> "
                "page with the list of Overpass API instances."
            ).format(wiki_url=OVERPASS_INSTANCES_WIKI_URL)
        )

        return "".join(lines)

    def _build_info_row_html(
        self,
        label: str,
        value_html: str,
    ) -> str:
        return (
            f"<tr><td><b>{escape(label)}:</b></td><td>{value_html}</td></tr>"
        )

    def _build_link_html(
        self,
        url: str,
        label: str,
    ) -> str:
        return f'<a href="{escape(url, quote=True)}">{escape(label)}</a>'

    def _build_contact_html(
        self,
        endpoint: OverpassEndpointInfo,
    ) -> str:
        contact = endpoint.contact
        if contact is None:
            return ""

        if endpoint.contact_url is None:
            return escape(contact)

        return self._build_link_html(
            endpoint.contact_url,
            contact,
        )

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
        QDesktopServices.openUrl(QUrl(OVERPASS_INSTANCES_WIKI_URL))

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
        self.widget = QLabel(self.tr("Settings dialog crashed"), self)
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
        super().__init__("OSMInfo", plugin_icon())

    def path(self) -> List[str]:
        return ["NextGIS"]

    def createWidget(
        self, parent: Optional[QWidget] = None
    ) -> Optional[QgsOptionsPageWidget]:
        try:
            return OsmInfoOptionsPageWidget(parent)
        except Exception:
            logger.exception("Settings dialog crashed")
            return OsmInfoOptionsErrorPageWidget(parent)
