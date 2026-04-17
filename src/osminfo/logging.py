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

import html
import logging
import re
from pprint import pformat
from typing import TYPE_CHECKING, Dict, List, Optional, Set, Union, cast

from qgis.core import Qgis, QgsApplication
from qgis.PyQt.QtWidgets import QPlainTextEdit, QTabWidget
from qgis.utils import iface

from osminfo.core.constants import PLUGIN_NAME
from osminfo.settings.osm_info_settings import OsmInfoSettings

if TYPE_CHECKING:
    from qgis.gui import QgisInterface

    assert isinstance(iface, QgisInterface)

SUCCESS_LEVEL = logging.INFO + 1
logging.addLevelName(SUCCESS_LEVEL, "SUCCESS")


def map_logging_level_to_qgis(level: int) -> Qgis.MessageLevel:
    """Map Python logging level to QGIS message level.

    :param level: Logging level
    :type level: int
    :return: QGIS message level
    :rtype: Qgis.MessageLevel
    """
    if level >= logging.ERROR:
        return Qgis.MessageLevel.Critical
    if level >= logging.WARNING:
        return Qgis.MessageLevel.Warning
    if level == SUCCESS_LEVEL:
        return Qgis.MessageLevel.Success
    if level >= logging.DEBUG:
        return Qgis.MessageLevel.Info

    return Qgis.MessageLevel.NoLevel


def map_qgis_level_to_logging(level: Qgis.MessageLevel) -> int:
    """Map QGIS message level to Python logging level.

    :param level: QGIS message level
    :type level: Qgis.MessageLevel
    :return: Corresponding Python logging level
    :rtype: int
    """
    if level == Qgis.MessageLevel.Critical:
        return logging.ERROR
    if level == Qgis.MessageLevel.Warning:
        return logging.WARNING
    if level == Qgis.MessageLevel.Success:
        return SUCCESS_LEVEL
    if level == Qgis.MessageLevel.Info:
        return logging.INFO

    return logging.NOTSET


class QgisLogger(logging.Logger):
    """Custom logger for QGIS nextgis_connect.

    Provides integration with QGIS message log and adds a 'success' level.

    :param name: Logger name
    :type name: str
    :param level: Logging level
    :type level: int
    """

    def __init__(self, name: str, level: int = logging.NOTSET) -> None:
        """Initialize QgisLogger instance.

        :param name: Logger name
        :type name: str
        :param level: Logging level
        :type level: int
        """
        super().__init__(name, level)

    def log(
        self,
        level: Union[int, Qgis.MessageLevel],
        msg: str,
        *args,
        **kwargs,
    ) -> None:
        """Log 'msg % args' with the integer severity 'level'.

        To pass exception information, use the keyword argument exc_info with
        a true value, e.g.

        logger.log(level, "We have a %s", "mysterious problem", exc_info=True)
        """
        if isinstance(level, Qgis.MessageLevel):
            level = map_qgis_level_to_logging(level)

        super().log(level, msg, *args, **kwargs)

    def success(self, message: str, *args, **kwargs) -> None:
        """Log a message with SUCCESS level.

        :param message: Log message
        :type message: str
        """
        if self.isEnabledFor(SUCCESS_LEVEL):
            self._log(SUCCESS_LEVEL, message, args, **kwargs)


class QgisLoggerHandler(logging.Handler):
    """Logging handler that sends messages to QGIS message log.

    Formats and routes log records to QgsApplication.messageLog().
    """

    def emit(self, record: logging.LogRecord) -> None:
        """Emit a log record to QGIS message log.

        :param record: Log record
        :type record: logging.LogRecord
        """
        level = map_logging_level_to_qgis(record.levelno)
        message = self.format(record)
        message_log = QgsApplication.messageLog()
        if record.levelno == logging.DEBUG:
            message = f"[DEBUG]    {message}"
        assert message_log is not None

        message_log.logMessage(self._process_html(message), record.name, level)

    def _process_html(self, message: str) -> str:
        """Process message for HTML compatibility in QGIS log.

        :param message: Log message
        :type message: str
        :return: Processed message
        :rtype: str
        """
        message = message.replace(" ", "\u00a0")

        if Qgis.versionInt() < 34202:
            return message

        # https://github.com/qgis/QGIS/issues/45834
        for tag in ("i", "b"):
            message = re.sub(
                rf"<{tag}\b[^>]*?>", "", message, flags=re.IGNORECASE
            )
            message = re.sub(rf"</{tag}>", "", message, flags=re.IGNORECASE)

        return message


def load_logger() -> QgisLogger:
    """Create and configure QgisLogger instance.

    Temporarily sets QgisLogger as the logger class, then restores the original.

    :return: Configured QgisLogger instance
    :rtype: QgisLogger
    """
    original_logger_class = logging.getLoggerClass()
    logging.setLoggerClass(QgisLogger)
    logger = logging.getLogger(PLUGIN_NAME)
    logging.setLoggerClass(original_logger_class)

    logger.propagate = False

    handler = QgisLoggerHandler()
    logger.addHandler(handler)

    is_debug_logs_enabled = OsmInfoSettings().is_debug_enabled
    logger.setLevel(logging.DEBUG if is_debug_logs_enabled else logging.INFO)
    if is_debug_logs_enabled:
        logger.warning("Debug messages are enabled")

    return cast(QgisLogger, logger)


def update_logging_level() -> None:
    """Update logging level based on plugin settings."""
    is_debug_logs_enabled = OsmInfoSettings().is_debug_enabled
    logger.setLevel(logging.DEBUG if is_debug_logs_enabled else logging.INFO)


def unload_logger() -> None:
    """Remove all handlers and reset logger."""
    logger = logging.getLogger(PLUGIN_NAME)

    handlers = logger.handlers.copy()
    for handler in handlers:
        logger.removeHandler(handler)
        handler.close()

    logger.propagate = True

    logger.setLevel(logging.NOTSET)


def escape_html(message: str) -> str:
    """
    Escape HTML special characters in a string.

    :param message: The message to escape.
    :return: The escaped message.
    """
    # https://github.com/qgis/QGIS/issues/45834
    return html.escape(message) if Qgis.versionInt() < 34202 else message


def format_container_data(data: Union[List, Set, Dict]) -> str:
    """
    Format container data (list, set, dict) for logging.

    :param data: The container data to format.
    :return: Formatted string representation of the data.
    """
    return pformat(data)


def extract_plugin_logs() -> str:
    """
    Extract log messages from QGIS log viewer for the plugin tab.
    :returns: Log messages as a single string.
    :rtype: str
    """
    log_viewer = iface.mainWindow().logViewer()
    tab_widget: QTabWidget = log_viewer.findChild(QTabWidget)
    assert tab_widget is not None

    text_edit: Optional[QPlainTextEdit] = None
    for index in range(tab_widget.count()):
        if tab_widget.tabText(index) == PLUGIN_NAME:
            text_edit = tab_widget.widget(index)
            break

    if text_edit is None:
        return ""

    return text_edit.toPlainText()


def open_plugin_logs() -> None:
    """
    Open QGIS log viewer with the plugin tab selected.
    """
    if Qgis.versionInt() >= 34400:
        iface.openMessageLog(PLUGIN_NAME)
    else:
        iface.openMessageLog()


logger = load_logger()
