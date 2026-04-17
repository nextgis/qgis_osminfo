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

from typing import TYPE_CHECKING

from qgis.core import QgsRuntimeProfiler

if TYPE_CHECKING:
    from qgis.gui import QgisInterface

from osminfo.osminfo_interface import OsmInfoInterface
from osminfo.settings.osm_info_settings import OsmInfoSettings


def classFactory(_iface: "QgisInterface") -> OsmInfoInterface:
    """
    Create an instance of the NextGIS OsmInfo plugin.

    :param _iface: Reference to the QGIS interface
    :returns: Instance of the NextGIS OsmInfo plugin
    """

    settings = OsmInfoSettings()

    try:
        with QgsRuntimeProfiler.profile("Import plugin"):  # type: ignore PylancereportAttributeAccessIssue
            from osminfo.osminfo_plugin import OsmInfoPlugin

        plugin = OsmInfoPlugin()

        settings.did_last_launch_fail = False

    except Exception as error:
        import copy

        from qgis.PyQt.QtCore import QTimer

        from osminfo.core.exceptions import (
            OsmInfoReloadAfterUpdateWarning,
        )
        from osminfo.osminfo_plugin_stub import (
            OsmInfoPluginStub,
        )

        error_copy = copy.deepcopy(error)
        exception = error_copy

        if not settings.did_last_launch_fail:
            # Sometimes after an update that changes the plugin structure,
            # the plugin may fail to load. Restarting QGIS helps.
            exception = OsmInfoReloadAfterUpdateWarning()
            exception.__cause__ = error_copy

        settings.did_last_launch_fail = True

        plugin = OsmInfoPluginStub()

        def display_exception() -> None:
            plugin.notifier.display_exception(exception)

        QTimer.singleShot(0, display_exception)

    return plugin
