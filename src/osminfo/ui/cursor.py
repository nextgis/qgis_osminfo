import math
from dataclasses import dataclass
from enum import Enum

from qgis.core import Qgis, QgsApplication
from qgis.PyQt.QtGui import QCursor, QFontMetrics

from osminfo.ui.icon import plugin_icon


@dataclass
class _CursorMetadata:
    """
    Represents information about a cursor.

    :param icon: Path to the cursor icon.
    :type icon: str
    :param active_x: X-coordinate of the cursor's active point.
    :type active_x: int
    :param active_y: Y-coordinate of the cursor's active point.
    :type active_y: int
    """

    icon: str
    active_x: int
    active_y: int


class OsmInfoCursor(Enum):
    """
    Enum representing available cursors for the OSMInfo plugin.

    :cvar IDENTIFY: Cursor for the "Identify" tool.
    """

    IDENTIFY = _CursorMetadata("cursor.svg", 3, 6)


def create_cursor(cursor_metadata: OsmInfoCursor) -> QCursor:
    """
    Generate a QCursor object based on the provided OsmInfoCursor.

    This function creates a cursor using the icon and active point
    specified in the `_CursorMetadata` of the given `OsmInfoCursor`.
    Based on QgsApplication::getThemeCursor.

    :param cursor_metadata: The cursor type to generate.
    :return: A QCursor object for the specified cursor type.
    """
    DEFAULT_ICON_SIZE = 32.0

    icon = plugin_icon(cursor_metadata.value.icon)
    if icon is None or icon.isNull():
        return QCursor()

    font_metrics = QFontMetrics(QgsApplication.font())
    scale = Qgis.UI_SCALE_FACTOR * font_metrics.height() / DEFAULT_ICON_SIZE
    cursor = QCursor(
        icon.pixmap(
            math.ceil(DEFAULT_ICON_SIZE * scale),
            math.ceil(DEFAULT_ICON_SIZE * scale),
        ),
        math.ceil(cursor_metadata.value.active_x * scale),
        math.ceil(cursor_metadata.value.active_y * scale),
    )

    return cursor
