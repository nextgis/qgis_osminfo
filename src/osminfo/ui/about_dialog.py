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

import importlib.util
import json
from enum import Enum
from html import escape
from pathlib import Path
from typing import Any, Dict, Optional, Union

from qgis.core import QgsSettings
from qgis.PyQt import uic
from qgis.PyQt.QtCore import (
    QT_VERSION_STR,
    QByteArray,
    QFile,
    QLocale,
    QRectF,
    QSize,
    Qt,
    QUrl,
)
from qgis.PyQt.QtGui import QDesktopServices, QIcon, QPainter, QPixmap
from qgis.PyQt.QtSvg import QSvgRenderer
from qgis.PyQt.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QListWidgetItem,
    QToolButton,
    QVBoxLayout,
    QWidget,
)
from qgis.utils import pluginMetadata

QT_MAJOR_VERSION = int(QT_VERSION_STR.split(".")[0])
if QT_MAJOR_VERSION < 6:
    from qgis.PyQt.QtSvg import (
        QSvgWidget,  # pyright: ignore[reportAttributeAccessIssue]
    )
elif importlib.util.find_spec("qgis.PyQt.QtSvgWidgets"):
    from qgis.PyQt.QtSvgWidgets import (  # pyright: ignore[reportMissingImports]
        QSvgWidget,
    )
else:
    from PyQt6.QtSvgWidgets import QSvgWidget

CURRENT_PATH = Path(__file__).parent
UI_PATH = Path(__file__).parent / "ui"
RESOURCES_PATH = Path(__file__).parents[1] / "resources"


if (UI_PATH / "about_dialog_base.ui").exists():
    Ui_AboutDialogBase, _ = uic.loadUiType(
        str(UI_PATH / "about_dialog_base.ui")
    )
elif (UI_PATH / "aboutdialogbase.ui").exists():
    Ui_AboutDialogBase, _ = uic.loadUiType(str(UI_PATH / "aboutdialogbase.ui"))
elif (RESOURCES_PATH / "about_dialog_base.ui").exists():
    Ui_AboutDialogBase, _ = uic.loadUiType(
        str(RESOURCES_PATH / "about_dialog_base.ui")
    )
elif (CURRENT_PATH / "about_dialog_base.ui").exists():
    Ui_AboutDialogBase, _ = uic.loadUiType(
        str(CURRENT_PATH / "about_dialog_base.ui")
    )
elif (UI_PATH / "about_dialog_base.py").exists():
    from .ui.about_dialog_base import (  # type: ignore
        Ui_AboutDialogBase,
    )
elif (UI_PATH / "aboutdialogbase.py").exists():
    from .ui.aboutdialogbase import (  # type: ignore
        Ui_AboutDialogBase,
    )
elif (UI_PATH / "ui_aboutdialogbase.py").exists():
    from .ui.ui_aboutdialogbase import (  # type: ignore
        Ui_AboutDialogBase,
    )
else:
    raise ImportError


BALANCE_ICON = r'<svg xmlns="http://www.w3.org/2000/svg" height="48px" viewBox="0 -960 960 960" width="48px" fill="#ffffff"><path d="M80-120v-60h370v-484q-26-9-46.5-29.5T374-740H215l125 302q-1 45-38.5 76.5T210-330q-54 0-91.5-31.5T80-438l125-302h-85v-60h254q12-35 41-57.5t65-22.5q36 0 65 22.5t41 57.5h254v60h-85l125 302q-1 45-38.5 76.5T750-330q-54 0-91.5-31.5T620-438l125-302H586q-9 26-29.5 46.5T510-664v484h370v60H80Zm595-320h150l-75-184-75 184Zm-540 0h150l-75-184-75 184Zm345-280q21 0 35.5-15t14.5-35q0-21-14.5-35.5T480-820q-20 0-35 14.5T430-770q0 20 15 35t35 15Z"/></svg>'
OPEN_IN_NEW_ICON = r'<svg xmlns="http://www.w3.org/2000/svg" height="40px" viewBox="0 -960 960 960" width="40px" fill="#ffffff"><path d="M186.67-120q-27 0-46.84-19.83Q120-159.67 120-186.67v-586.66q0-27 19.83-46.84Q159.67-840 186.67-840H466v66.67H186.67v586.66h586.66V-466H840v279.33q0 27-19.83 46.84Q800.33-120 773.33-120H186.67ZM384-336.67 337.33-384l389.34-389.33h-194V-840H840v307.33h-66.67V-726L384-336.67Z"/></svg>'


def render_svg_icon(
    svg: Union[Path, str],
    *,
    color: Optional[str] = None,
    size: Optional[int] = None,
    replacements: Optional[Dict[str, str]] = None,
) -> QIcon:
    if isinstance(svg, Path):
        svg_content = svg.read_text(encoding="utf-8")
    else:
        svg_content = svg

    if color:
        modified_svg = svg_content.replace('fill="#ffffff"', f'fill="{color}"')
        modified_svg = modified_svg.replace("fill:#ffffff", f"fill:{color}")
    else:
        modified_svg = svg_content

    if replacements:
        for key, value in replacements.items():
            modified_svg = modified_svg.replace(key, value)

    byte_array = QByteArray(modified_svg.encode("utf-8"))
    renderer = QSvgRenderer()
    if not renderer.load(byte_array):
        message = f"Failed to load SVG: {svg}"
        raise ValueError(message)

    target_size = renderer.defaultSize() if size is None else QSize(size, size)
    pixmap = QPixmap(target_size)
    pixmap.fill(Qt.GlobalColor.transparent)

    painter = QPainter(pixmap)
    renderer.render(
        painter,
        QRectF(0, 0, target_size.width(), target_size.height()),
    )
    painter.end()

    return QIcon(pixmap)


class AboutTab(str, Enum):
    Information = "information_tab"
    License = "license_tab"
    Components = "components_tab"
    Contributors = "contributors_tab"

    def __str__(self) -> str:
        return str(self.value)


class AboutDialog(QDialog, Ui_AboutDialogBase):
    COMPONENT_ITEM_HEIGHT = 64
    COMPONENT_BUTTON_ICON_SIZE = 16
    COMPONENT_BUTTON_SIZE = 22

    def __init__(self, package_name: str, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setupUi(self)
        self.__package_name = package_name

        module_spec = importlib.util.find_spec(self.__package_name)
        if module_spec and module_spec.origin:
            self.__package_path = Path(module_spec.origin).parent
        else:
            self.__package_path = Path(__file__).parent

        self.tab_widget.setCurrentIndex(0)

        metadata = self.__metadata()
        self.__set_icon(metadata)
        self.__fill_headers(metadata)
        self.__fill_get_involved(metadata)
        self.__fill_about(metadata)
        self.__fill_license()
        self.__fill_components()
        self.__fill_contributors()

    def __fill_headers(self, metadata: Dict[str, Optional[str]]) -> None:
        plugin_name = metadata["plugin_name"]
        assert isinstance(plugin_name, str)
        if "NextGIS" not in plugin_name:
            plugin_name += self.tr(" by NextGIS")

        self.setWindowTitle(self.windowTitle().format(plugin_name=plugin_name))
        self.plugin_name_label.setText(
            self.plugin_name_label.text().format_map(metadata)
        )
        self.version_label.setText(
            self.version_label.text().format_map(metadata)
        )

    def __set_icon(self, metadata: Dict[str, Optional[str]]) -> None:
        if metadata.get("icon_path") is None:
            return

        header_size: QSize = self.info_layout.sizeHint()

        icon_path = self.__package_path / str(metadata.get("icon_path"))
        svg_icon_path = icon_path.with_suffix(".svg")

        if svg_icon_path.exists():
            icon_widget: QWidget = QSvgWidget(str(svg_icon_path), self)
            icon_size: QSize = icon_widget.sizeHint()
        else:
            pixmap = QPixmap(str(icon_path))
            if pixmap.size().height() > header_size.height():
                pixmap = pixmap.scaled(
                    header_size.height(),
                    header_size.height(),
                    Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                )

            icon_size: QSize = pixmap.size()

            icon_widget = QLabel(self)
            icon_widget.setPixmap(pixmap)
            icon_widget.setAlignment(Qt.AlignmentFlag.AlignCenter)

        icon_size.scale(
            header_size.height(),
            header_size.height(),
            Qt.AspectRatioMode.KeepAspectRatioByExpanding,
        )
        icon_widget.setFixedSize(icon_size)
        self.header_layout.insertWidget(0, icon_widget)

    def __fill_get_involved(self, metadata: Dict[str, Optional[str]]) -> None:
        file_path = str(self.__package_path / "icons" / "nextgis_logo.svg")
        resources_path = (
            f":/plugins/{self.__package_name}/icons/nextgis_logo.svg"
        )

        if QFile(resources_path).exists():
            self.get_involved_button.setIcon(QIcon(resources_path))
        elif QFile(file_path).exists():
            self.get_involved_button.setIcon(QIcon(file_path))

        self.get_involved_button.clicked.connect(
            lambda: QDesktopServices.openUrl(
                QUrl(metadata["get_involved_url"])
            )
        )

    def __fill_about(self, metadata: Dict[str, Optional[str]]) -> None:
        self.about_text_browser.setHtml(self.__html(metadata))

    def __fill_license(self) -> None:
        license_path = self.__package_path / "LICENSE"
        if not license_path.exists():
            self.tab_widget.removeTab(self.__tab_to_index(AboutTab.License))
            return

        self.license_text_browser.setPlainText(license_path.read_text())

    def __fill_components(self) -> None:
        components_path = self.__package_path / "resources" / "components.json"
        if not components_path.exists():
            self.tab_widget.removeTab(self.__tab_to_index(AboutTab.Components))
            return

        try:
            components_data = json.loads(
                components_path.read_text(encoding="utf-8")
            )
        except (OSError, ValueError):
            self.tab_widget.removeTab(self.__tab_to_index(AboutTab.Components))
            return

        if not isinstance(components_data, list):
            self.tab_widget.removeTab(self.__tab_to_index(AboutTab.Components))
            return

        self.components_list_widget.clear()
        self.components_list_widget.setUniformItemSizes(True)
        self.components_list_widget.setSpacing(2)

        for component_data in components_data:
            if not isinstance(component_data, dict):
                continue

            item_widget = self.__component_item_widget(component_data)
            if item_widget is None:
                continue

            item = QListWidgetItem()
            item.setSizeHint(QSize(0, self.COMPONENT_ITEM_HEIGHT))
            self.components_list_widget.addItem(item)
            self.components_list_widget.setItemWidget(item, item_widget)

        if self.components_list_widget.count() == 0:
            self.tab_widget.removeTab(self.__tab_to_index(AboutTab.Components))

    def __fill_contributors(self) -> None:
        self.tab_widget.removeTab(self.__tab_to_index(AboutTab.Contributors))

    def __component_item_widget(
        self, component_data: Dict[str, Any]
    ) -> Optional[QWidget]:
        title = self.__component_text(component_data, "title")
        description = self.__component_text(component_data, "description")
        license_url = self.__component_text(component_data, "license_url")
        project_url = self.__component_text(component_data, "project_url")

        if None in (title, description, license_url, project_url):
            return None

        assert title is not None
        assert description is not None
        assert license_url is not None
        assert project_url is not None

        version = self.__component_text(component_data, "version")

        item_widget = QWidget(self.components_list_widget)
        item_widget.setFixedHeight(self.COMPONENT_ITEM_HEIGHT)

        content_layout = QHBoxLayout(item_widget)
        content_layout.setContentsMargins(8, 4, 8, 4)
        content_layout.setSpacing(8)

        text_layout = QVBoxLayout()
        text_layout.setContentsMargins(0, 0, 0, 0)
        text_layout.setSpacing(1)

        title_label = QLabel(item_widget)
        title_label.setTextFormat(Qt.TextFormat.RichText)
        title_label.setWordWrap(True)
        title_label.setText(self.__component_title(title, version))
        title_label.setAlignment(Qt.AlignmentFlag.AlignVCenter)

        description_label = QLabel(description, item_widget)
        description_label.setWordWrap(True)
        description_label.setAlignment(Qt.AlignmentFlag.AlignVCenter)

        full_title = title if version is None else f"{title} ({version})"
        title_label.setToolTip(full_title)
        description_label.setToolTip(description)

        text_layout.addWidget(title_label)
        text_layout.addWidget(description_label)

        buttons_layout = QHBoxLayout()
        buttons_layout.setContentsMargins(0, 0, 0, 0)
        buttons_layout.setSpacing(0)

        license_button = self.__component_button(
            icon=BALANCE_ICON,
            url=license_url,
        )
        project_button = self.__component_button(
            icon=OPEN_IN_NEW_ICON,
            url=project_url,
        )

        buttons_layout.addWidget(license_button)
        buttons_layout.addWidget(project_button)

        content_layout.addLayout(text_layout, 1)
        content_layout.addLayout(buttons_layout)

        return item_widget

    def __component_button(self, *, icon: str, url: str) -> QToolButton:
        button = QToolButton(self.components_list_widget)
        button.setAutoRaise(True)
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.setIcon(
            render_svg_icon(
                icon,
                color=self.palette().text().color().name(),
                size=self.COMPONENT_BUTTON_ICON_SIZE,
            )
        )
        button.setIconSize(
            QSize(
                self.COMPONENT_BUTTON_ICON_SIZE,
                self.COMPONENT_BUTTON_ICON_SIZE,
            )
        )
        button.setFixedSize(
            QSize(self.COMPONENT_BUTTON_SIZE, self.COMPONENT_BUTTON_SIZE)
        )
        button.setToolTip(url)
        button.clicked.connect(
            lambda checked=False, url=url: QDesktopServices.openUrl(QUrl(url))
        )
        return button

    def __component_text(
        self, component_data: Dict[str, Any], key: str
    ) -> Optional[str]:
        value = component_data.get(key)
        if isinstance(value, str):
            normalized_value = value.strip()
            return normalized_value or None

        if not isinstance(value, dict):
            return None

        locale = self.__locale()
        localized_value = value.get(locale, value.get("en"))
        if not isinstance(localized_value, str):
            return None

        normalized_value = localized_value.strip()
        return normalized_value or None

    def __component_title(self, title: str, version: Optional[str]) -> str:
        escaped_title = escape(title)
        if version is None:
            return f'<span style="font-weight: 600;">{escaped_title}</span>'

        escaped_version = escape(version)
        return (
            f'<span style="font-weight: 600;">{escaped_title}</span> '
            f"({escaped_version})"
        )

    def __locale(self) -> str:
        override_locale = QgsSettings().value(
            "locale/overrideFlag", defaultValue=False, type=bool
        )
        if not override_locale:
            locale_full_name = QLocale.system().name()
        else:
            locale_full_name = QgsSettings().value("locale/userLocale", "")

        return locale_full_name[0:2]

    def __metadata(self) -> Dict[str, Optional[str]]:
        locale = self.__locale()
        speaks_russian = locale in ["be", "kk", "ky", "ru", "uk"]

        def metadata_value(key: str) -> Optional[str]:
            value = pluginMetadata(self.__package_name, f"{key}[{locale}]")
            if value == "__error__":
                value = pluginMetadata(self.__package_name, key)
            if value == "__error__":
                value = None
            return value

        about = metadata_value("about")
        assert about is not None
        for about_stop_phrase in (
            "Разработан",
            "Developed by",
            "Développé par",
            "Desarrollado por",
            "Sviluppato da",
            "Desenvolvido por",
        ):
            if about.find(about_stop_phrase) > 0:
                about = about[: about.find(about_stop_phrase)]

        package_name = self.__package_name.replace("qgis_", "")

        main_url = f"https://nextgis.{'ru' if speaks_russian else 'com'}"
        utm = f"utm_source=qgis_plugin&utm_medium=about&utm_campaign=constant&utm_term={package_name}&utm_content={locale}"

        return {
            "plugin_name": metadata_value("name"),
            "version": metadata_value("version"),
            "icon_path": metadata_value("icon"),
            "description": metadata_value("description"),
            "about": about,
            "authors": metadata_value("author"),
            "video_url": metadata_value("video"),
            "homepage_url": metadata_value("homepage"),
            "tracker_url": metadata_value("tracker"),
            "user_guide_url": metadata_value("user_guide"),
            "main_url": main_url,
            "data_url": main_url.replace("://", "://data."),
            "get_involved_url": f"https://nextgis.com/redirect/{locale}/ak45prp5?{utm}",
            "community_url": "https://community.nextgis.com",
            "utm": f"?{utm}",
            "speaks_russian": str(speaks_russian),
        }

    def __html(self, metadata: Dict[str, Optional[str]]) -> str:
        report_end = self.tr("REPORT_END")
        if report_end == "REPORT_END":
            report_end = ""

        titles = {
            "developers_title": self.tr("Developers"),
            "homepage_title": self.tr("Homepage"),
            "community_title": self.tr("Join the community"),
            "user_guide": self.tr("User Guide"),
            "report_title": self.tr("Please report bugs at"),
            "report_end": report_end,
            "bugtracker_title": self.tr("bugtracker"),
            "video_title": self.tr("Video with an overview of the plugin"),
            "services_title": self.tr("Other helpful services by NextGIS"),
            "extracts_title": self.tr(
                "Convenient up-to-date data extracts for any place in the world"
            ),
            "webgis_title": self.tr("Fully featured Web GIS service"),
        }

        description = """
            <p>{description}</p>
            <p>{about}</p>
        """

        if metadata.get("user_guide_url") is not None:
            description += '<p><b>{user_guide}:</b> <a href="{user_guide_url}{utm}">{user_guide_url}</a></p>'

        description += """
            <p><b>{developers_title}:</b> <a href="{main_url}/{utm}">{authors}</a></p>
            <p><b>{homepage_title}:</b> <a href="{homepage_url}">{homepage_url}</a></p>
            <p><b>{community_title}:</b> <a href="{community_url}/{utm}">{community_url}</a></p>
            <p><b>{report_title}</b> <a href="{tracker_url}">{bugtracker_title}</a> {report_end}</p>
        """

        if metadata.get("video_url") is not None:
            description += '<p><b>{video_title}:</b> <a href="{video_url}">{video_url}</a></p>'

        services = """
            <p>
            {services_title}:
            <ul>
              <li><b>{extracts_title}</b>: <a href="{data_url}/{utm}">{data_url}</a></li>
              <li><b>{webgis_title}</b>: <a href="{main_url}/nextgis-com/plans{utm}">{main_url}/nextgis-com/plans</a></li>
            </ul>
            </p>
            """

        replacements = dict()
        replacements.update(titles)
        replacements.update(metadata)

        return (description + services).format_map(replacements)

    def __tab_to_index(self, tab_name: AboutTab) -> int:
        tab = self.tab_widget.findChild(QWidget, str(tab_name))
        return self.tab_widget.indexOf(tab)
