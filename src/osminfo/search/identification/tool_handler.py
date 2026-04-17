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


from typing import Optional

from qgis.core import QgsMapLayer
from qgis.gui import QgsAbstractMapToolHandler, QgsMapTool
from qgis.PyQt.QtWidgets import QAction


class OsmInfoToolHandler(QgsAbstractMapToolHandler):
    """Delegate base map-tool handler behavior to QGIS

    :ivar map_tool: Map tool instance managed by the handler.
    :ivar action: QAction associated with the map tool.
    """

    def __init__(self, map_tool: QgsMapTool, action: QAction) -> None:  # pyright: ignore[reportInvalidTypeForm]
        """Initialize the handler.

        :param map_tool: Map tool used for identification.
        :param action: Associated QAction.
        """
        super().__init__(map_tool, action)

    def isCompatibleWithLayer(
        self,
        layer: Optional[QgsMapLayer],
        context: QgsAbstractMapToolHandler.Context,
    ) -> bool:
        """Return whether the handler supports the provided layer.

        :param layer: Layer to check compatibility for, may be ``None``.
        :param context: Context of the map tool handler.
        :return: True
        """
        return True
