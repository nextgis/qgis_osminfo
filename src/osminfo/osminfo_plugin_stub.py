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
from qgis.core import Qgis, QgsTaskManager
from qgis.gui import QgisInterface
from qgis.PyQt.QtCore import (
    QT_VERSION_STR,
    QSysInfo,
    pyqtSlot,
)
from qgis.utils import iface

from osminfo.core.logging import logger
from osminfo.notifier.message_bar_notifier import MessageBarNotifier
from osminfo.notifier.notifier_interface import NotifierInterface
from osminfo.osminfo_interface import OsmInfoInterface

if TYPE_CHECKING:
    assert isinstance(iface, QgisInterface)


class OsmInfoPluginStub(OsmInfoInterface):
    """NextGIS OsmInfo Plugin stub for exceptions processing"""

    def __init__(self) -> None:
        super().__init__()

        logger.debug("<b>✓ Plugin stub object created</b>")
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
        self.__notifier = None

    @property
    def task_manager(self) -> QgsTaskManager:
        raise NotImplementedError

    @pyqtSlot()
    def open_settings(self) -> None:
        raise NotImplementedError

    @pyqtSlot()
    def open_about_dialog(self) -> None:
        raise NotImplementedError

    @property
    def notifier(self) -> "NotifierInterface":
        """Return the notifier for displaying messages to the user.

        :returns: Notifier interface instance.
        :rtype: NotifierInterface
        """
        assert self.__notifier is not None, "Notifier is not initialized"
        return self.__notifier

    def _load(self) -> None:
        logger.debug("<b>Start stub initialization</b>")

        self.__notifier = MessageBarNotifier(self)

        logger.debug("<b>End stub initialization</b>")

    def _unload(self) -> None:
        logger.debug("<b>Start stub unloading</b>")

        self.__notifier.deleteLater()
        self.__notifier = None

        logger.debug("<b>End stub unloading</b>")
