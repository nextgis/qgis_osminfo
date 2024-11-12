from pathlib import Path
from typing import List, Optional

from qgis.core import QgsApplication
from qgis.gui import (
    QgsOptionsPageWidget,
    QgsOptionsWidgetFactory,
)
from qgis.PyQt import uic
from qgis.PyQt.QtCore import Qt, QUrl, pyqtSlot
from qgis.PyQt.QtGui import QDesktopServices, QIcon
from qgis.PyQt.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from osminfo.logging import logger, update_level
from osminfo.settings.osm_info_settings import OsmInfoSettings


class OsmInfoOptionsPageWidget(QgsOptionsPageWidget):
    widget: QWidget

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.__init_ui()
        self.__init_settings()

    def apply(self) -> None:
        self.__apply_settings()

    def cancel(self) -> None:
        pass

    def __init_ui(self) -> None:
        self.__load_ui()

        self.__widget.endpoint_combobox.addItem(
            "Main Overpass API instance",
            "https://overpass-api.de/api/interpreter",
        )
        self.__widget.endpoint_combobox.addItem(
            "VK Maps Overpass API instance (Russia)",
            "https://maps.mail.ru/osm/tools/overpass/api/interpreter",
        )
        self.__widget.endpoint_combobox.addItem(
            "Russian Overpass API instance",
            "https://overpass.openstreetmap.ru/api/interpreter",
        )
        self.__widget.endpoint_combobox.addItem(
            "Swiss Overpass API instance",
            "https://overpass.osm.ch/api/interpreter",
        )
        self.__widget.endpoint_combobox.addItem(
            "Private.coffee Overpass Instance",
            "https://overpass.private.coffee/api/interpreter",
        )
        self.__widget.endpoint_combobox.addItem(
            "Japan Overpass API instance",
            "https://overpass.osm.jp/api/interpreter",
        )

        self.__widget.endpoint_button.setIcon(
            QgsApplication.getThemeIcon("mActionPropertiesWidget.svg")
        )
        self.__widget.endpoint_button.clicked.connect(self.__open_osm_wiki)

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
        self.__widget.surrounding_checkbox.setChecked(
            settings.fetch_surrounding
        )
        self.__widget.timeout_spinbox.setValue(settings.timeout)
        self.__widget.distance_spinbox.setValue(settings.distance)
        self.__widget.debug_checkbox.setChecked(settings.is_debug_enabled)

    def __apply_settings(self):
        settings = OsmInfoSettings()
        settings.overpass_endpoint = (
            self.__widget.endpoint_combobox.currentData()
        )
        settings.fetch_surrounding = (
            self.__widget.surrounding_checkbox.isChecked()
        )
        settings.fetch_nearby = self.__widget.nearby_checkbox.isChecked()
        settings.timeout = self.__widget.timeout_spinbox.value()
        settings.distance = self.__widget.distance_spinbox.value()

        old_debug_enabled = settings.is_debug_enabled
        new_debug_enabled = self.__widget.debug_checkbox.isChecked()
        settings.is_debug_enabled = new_debug_enabled
        if old_debug_enabled != new_debug_enabled:
            debug_state = "enabled" if new_debug_enabled else "disabled"
            update_level()
            logger.info(f"Debug messages are now {debug_state}")

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
            QIcon(":/plugins/osminfo/icons/osminfo.svg"),
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
