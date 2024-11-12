# ******************************************************************************
#
# OSMInfo
# ---------------------------------------------------------
# This plugin takes coordinates of a mouse click and gets information about all
# objects from this point from OSM using Overpass API.
#
# Author:   Maxim Dubinin, sim@gis-lab.info
# Author:   Alexander Lisovenko, alexander.lisovenko@nextgis.ru
# *****************************************************************************
# Copyright (c) 2012-2015. NextGIS, info@nextgis.com
#
# This source is free software; you can redistribute it and/or modify it under
# the terms of the GNU General Public License as published by the Free
# Software Foundation, either version 2 of the License, or (at your option)
# any later version.
#
# This code is distributed in the hope that it will be useful, but WITHOUT ANY
# WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS
# FOR A PARTICULAR PURPOSE. See the GNU General Public License for more
# details.
#
# A copy of the GNU General Public License is available on the World Wide Web
# at <http://www.gnu.org/licenses/>. You can also obtain it by writing
# to the Free Software Foundation, 51 Franklin Street, Suite 500 Boston,
# MA 02110-1335 USA.
#
# ******************************************************************************

import os
from pathlib import Path

from qgis.core import QgsApplication
from qgis.PyQt.QtCore import (
    QCoreApplication,
    QFileInfo,
    QLocale,
    QSettings,
    QTranslator,
)
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import QAction

from osminfo import about_dialog, osminfotool
from osminfo.logging import unload_logger
from osminfo.settings.osm_info_settings_page import OsmInfoOptionsWidgetFactory

_current_path = str(Path(__file__).parent)


class OsmInfo:
    def tr(self, message):
        return QCoreApplication.translate(__class__.__name__, message)

    def __init__(self, iface):
        """Initialize class"""
        # save reference to QGIS interface
        self.iface = iface

        # i18n support
        override_locale = QSettings().value(
            "locale/overrideFlag", False, type=bool
        )
        if not override_locale:
            locale_full_name = QLocale.system().name()
        else:
            locale_full_name = QSettings().value(
                "locale/userLocale", "", type=str
            )

        self.locale_path = (
            f"{_current_path}/i18n/osminfo_{locale_full_name[0:2]}.qm"
        )
        if QFileInfo(self.locale_path).exists():
            self.translator = QTranslator()
            self.translator.load(self.locale_path)
            QCoreApplication.installTranslator(self.translator)

    def initGui(self):
        """Initialize graphic user interface"""
        # create action that will be run by the plugin
        self.actionRun = QAction(
            self.tr("Get OSM info for a point"), self.iface.mainWindow()
        )

        self.actionRun.setIcon(QIcon(":/plugins/osminfo/icons/osminfo.png"))
        self.actionRun.setWhatsThis(self.tr("Select point"))
        self.actionRun.setStatusTip(
            self.tr("Select point to get OpenStreetMap data for")
        )

        self.actionAbout = QAction(
            QgsApplication.getThemeIcon("mActionPropertiesWidget.svg"),
            self.tr("About plugin…"),
            self.iface.mainWindow(),
        )

        self.actionSettings = QAction(
            QgsApplication.getThemeIcon("mActionOptions.svg"),
            self.tr("Settings"),
            self.iface.mainWindow(),
        )
        self.actionSettings.setWhatsThis(
            self.tr("Set various parameters related to OSMInfo")
        )

        # add plugin menu to Web
        self.osminfo_menu = self.tr("OSMInfo")
        self.iface.addPluginToWebMenu(self.osminfo_menu, self.actionRun)
        self.iface.addPluginToWebMenu(self.osminfo_menu, self.actionAbout)
        self.iface.addPluginToWebMenu(self.osminfo_menu, self.actionSettings)
        for action in self.iface.webMenu().actions():
            if action.text() != self.osminfo_menu:
                continue
            action.setIcon(QIcon(":/plugins/osminfo/icons/osminfo.svg"))

        # add icon to new menu item in Web toolbar
        self.iface.addWebToolBarIcon(self.actionRun)

        # connect action to the run method
        self.actionRun.triggered.connect(self.run)
        self.actionAbout.triggered.connect(self.about)
        self.actionSettings.triggered.connect(self.settings)

        # prepare map tool
        self.mapTool = osminfotool.OSMInfotool(self.iface)
        # self.iface.mapCanvas().mapToolSet.connect(self.mapToolChanged)

        self.__options_factory = OsmInfoOptionsWidgetFactory()
        self.iface.registerOptionsWidgetFactory(self.__options_factory)

    def unload(self):
        """Actions to run when the plugin is unloaded"""
        # remove menu and icon from the menu
        self.iface.removeWebToolBarIcon(self.actionRun)
        self.iface.removePluginWebMenu(self.tr("OSMInfo"), self.actionAbout)
        self.iface.removePluginWebMenu(self.tr("OSMInfo"), self.actionSettings)
        self.iface.removePluginWebMenu(self.tr("OSMInfo"), self.actionRun)

        if self.iface.mapCanvas().mapTool() == self.mapTool:
            self.iface.mapCanvas().unsetMapTool(self.mapTool)

        self.mapTool.deleteLater()
        del self.mapTool

        if self.__options_factory is not None:
            self.iface.unregisterOptionsWidgetFactory(self.__options_factory)
            self.__options_factory.deleteLater()
            self.__options_factory = None

        unload_logger()

    def run(self):
        """Action to run"""
        self.iface.mapCanvas().setMapTool(self.mapTool)

    def about(self):
        dialog = about_dialog.AboutDialog(os.path.basename(_current_path))
        dialog.exec()

    def settings(self):
        self.iface.showOptionsDialog(self.iface.mainWindow(), "OSMInfo")
