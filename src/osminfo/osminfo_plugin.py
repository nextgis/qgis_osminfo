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

import sys
from typing import TYPE_CHECKING

from osgeo import gdal
from qgis.core import Qgis, QgsTask, QgsTaskManager
from qgis.gui import QgisInterface
from qgis.PyQt.QtCore import (
    QT_VERSION_STR,
    QSysInfo,
    pyqtSlot,
)
from qgis.PyQt.QtWidgets import QAction
from qgis.utils import iface

from osminfo import resources  # noqa: F401
from osminfo.about_dialog import AboutDialog
from osminfo.core.constants import PACKAGE_NAME, PLUGIN_NAME, SHORT_PLUGIN_NAME
from osminfo.logging import logger
from osminfo.notifier.message_bar_notifier import MessageBarNotifier
from osminfo.notifier.notifier_interface import NotifierInterface
from osminfo.osminfo_interface import OsmInfoInterface
from osminfo.search.search_manager import OsmInfoSearchManager
from osminfo.settings.osm_info_settings_page import OsmInfoOptionsWidgetFactory
from osminfo.ui.icon import plugin_icon, qgis_icon

if TYPE_CHECKING:
    assert isinstance(iface, QgisInterface)


class OsmInfoPlugin(OsmInfoInterface):
    """NextGIS OsmInfo Plugin"""

    def __init__(self) -> None:
        super().__init__()

        logger.debug("<b>✓ Plugin object created</b>")
        logger.debug(f"<b>ⓘ OS:</b> {QSysInfo().prettyProductName()}")
        logger.debug(f"<b>ⓘ Qt version:</b> {QT_VERSION_STR}")
        logger.debug(f"<b>ⓘ QGIS version:</b> {Qgis.version()}")
        logger.debug(f"<b>ⓘ Python version:</b> {sys.version}")
        logger.debug(f"<b>ⓘ GDAL version:</b> {gdal.__version__}")
        logger.debug(f"<b>ⓘ Plugin version:</b> {self.version}")
        logger.debug(
            f"<b>ⓘ Plugin path:</b> {self.path}"
            + (f" -> {self.path.resolve()}" if self.path.is_symlink() else "")
        )

        self._notifier = None
        self._search_manager = None
        self._settings_action = None
        self._about_action = None
        self._help_action = None
        self._options_factory = None
        self._task_manager = None

    @property
    def task_manager(self) -> QgsTaskManager:
        if self._task_manager is None:
            self._load_task_manager()

        assert self._task_manager is not None, (
            "Task manager is not initialized"
        )
        return self._task_manager

    @pyqtSlot()
    def open_settings(self) -> None:
        iface.showOptionsDialog(iface.mainWindow(), SHORT_PLUGIN_NAME)

    @pyqtSlot()
    def open_about_dialog(self) -> None:
        dialog = AboutDialog(PACKAGE_NAME)
        dialog.exec()

    @property
    def notifier(self) -> "NotifierInterface":
        """Return the notifier for displaying messages to the user.

        :returns: Notifier interface instance.
        :rtype: NotifierInterface
        """
        assert self._notifier is not None, "Notifier is not initialized"
        return self._notifier

    def _load(self) -> None:
        logger.debug("<b>Start plugin initialization</b>")

        self._notifier = MessageBarNotifier(self)

        self._search_manager = OsmInfoSearchManager(self)
        self._search_manager.load()

        self._load_settings()
        self._load_settings_action()
        self._load_about_action()
        self._load_help_action()
        self._patch_menu_icon()
        self._load_task_manager()

        logger.debug("<b>End plugin initialization</b>")

    def _unload(self) -> None:
        logger.debug("<b>Start plugin unloading</b>")

        self._unload_help_action()
        self._unload_settings_action()
        self._unload_about_action()
        self._unload_settings()
        self._unload_task_manager()

        self._search_manager.unload()
        self._search_manager = None

        self._notifier.deleteLater()
        self._notifier = None

        logger.debug("<b>End plugin unloading</b>")

    def _load_help_action(self) -> None:
        self._help_action = QAction(plugin_icon(), PLUGIN_NAME, self)

        plugin_help_menu = iface.pluginHelpMenu()
        assert plugin_help_menu is not None
        plugin_help_menu.addAction(self._help_action)

        # connect action to the run method
        self._help_action.triggered.connect(self.open_about_dialog)

    def _unload_help_action(self) -> None:
        if self._help_action is None:
            return

        plugin_help_menu = iface.pluginHelpMenu()
        assert plugin_help_menu is not None
        plugin_help_menu.removeAction(self._help_action)
        self._help_action.deleteLater()
        self._help_action = None

    def _load_about_action(self) -> None:
        self._about_action = QAction(
            qgis_icon("mActionPropertiesWidget.svg"),
            self.tr("About plugin…"),
            self,
        )
        self._about_action.triggered.connect(self.open_about_dialog)
        iface.addPluginToWebMenu(PLUGIN_NAME, self._about_action)

    def _unload_about_action(self) -> None:
        if self._about_action is None:
            return

        iface.removePluginWebMenu(PLUGIN_NAME, self._about_action)
        self._about_action.deleteLater()
        self._about_action = None

    def _load_settings_action(self) -> None:
        self._settings_action = QAction(
            qgis_icon("mActionOptions.svg"),
            self.tr("Settings"),
            self,
        )
        self._settings_action.triggered.connect(self.open_settings)
        iface.addPluginToWebMenu(PLUGIN_NAME, self._settings_action)

    def _unload_settings_action(self) -> None:
        if self._settings_action is None:
            return

        iface.removePluginWebMenu(PLUGIN_NAME, self._settings_action)
        self._settings_action.deleteLater()
        self._settings_action = None

    def _load_settings(self) -> None:
        self._options_factory = OsmInfoOptionsWidgetFactory()
        iface.registerOptionsWidgetFactory(self._options_factory)

    def _unload_settings(self) -> None:
        if self._options_factory is None:
            return

        iface.unregisterOptionsWidgetFactory(self._options_factory)
        self._options_factory.deleteLater()
        self._options_factory = None

    def _load_task_manager(self) -> None:
        self._task_manager = QgsTaskManager()

    def _unload_task_manager(self) -> None:
        if self._task_manager is None:
            return

        # Stop all running tasks
        TaskStatus = QgsTask.TaskStatus
        for task in self._task_manager.tasks():
            if task.status() not in (
                TaskStatus.Complete,
                TaskStatus.Terminated,
            ):
                task.cancel()

        self._task_manager.deleteLater()
        self._task_manager = None

    def _patch_menu_icon(self) -> None:
        for action in iface.webMenu().actions():
            if action.text() != PLUGIN_NAME:
                continue

            action.setIcon(plugin_icon())
            break
