# -*- coding: utf-8 -*-
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

from qgis.PyQt.QtCore import QCoreApplication, QTranslator, QFileInfo, QSettings, QLocale
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import QAction, QMessageBox
from qgis.core import *

from .compat import get_file_dir, QGis
from . import osminfotool
from . import about_dialog, settingsdialog

from . import resources
import os
from os import path
import sys

_current_path = get_file_dir(__file__)


class OsmInfo:

    def tr(self, message):
        return QCoreApplication.translate(__class__.__name__, message)

    def __init__(self, iface):
        """Initialize class"""
        # save reference to QGIS interface
        self.iface = iface
        self.plugin_dir = path.dirname(__file__)
        self.qgsVersion = str(QGis.QGIS_VERSION_INT)

        # i18n support
        override_locale = QSettings().value('locale/overrideFlag', False, type=bool)
        if not override_locale:
            locale_full_name = QLocale.system().name()
        else:
            locale_full_name = QSettings().value('locale/userLocale', '', type=str)

        self.locale_path = '%s/i18n/osminfo_%s.qm' % (_current_path, locale_full_name[0:2])
        if QFileInfo(self.locale_path).exists():
            self.translator = QTranslator()
            self.translator.load(self.locale_path)
            QCoreApplication.installTranslator(self.translator)

    def initGui(self):
        """Initialize graphic user interface"""
        # check if the plugin is ran below 2.0
        if int(self.qgsVersion) < 20000:
            qgisVersion = self.qgsVersion[0] + "." + self.qgsVersion[2] + "." + self.qgsVersion[3]
            QMessageBox.warning(self.iface.mainWindow(),
                                'OSMInfo', self.tr('Error'),
                                'OSMInfo', self.tr('QGIS %s detected.\n') % (qgisVersion) +
                                'OSMInfo', self.tr(
                    'This version of OSMInfo requires at least QGIS version 2.0.\nPlugin will not be enabled.'))
            return None

        # create action that will be run by the plugin
        self.actionRun = QAction(self.tr('Get OSM info for a point'), self.iface.mainWindow())

        self.actionRun.setIcon(QIcon(':/plugins/osminfo/icons/osminfo.png'))
        self.actionRun.setWhatsThis(self.tr('Select point'))
        self.actionRun.setStatusTip(self.tr('Select point to get OpenStreetMap data for'))

        self.actionAbout = QAction(self.tr('About'), self.iface.mainWindow())

        self.actionSettings = QAction(self.tr('Settings'), self.iface.mainWindow())
        self.actionSettings.setWhatsThis(self.tr('Set various parameters related to OSMInfo'))

        # add plugin menu to Web
        self.osminfo_menu = self.tr(u'OSMInfo')
        self.iface.addPluginToWebMenu(self.osminfo_menu, self.actionRun)
        self.iface.addPluginToWebMenu(self.osminfo_menu, self.actionAbout)
        self.iface.addPluginToWebMenu(self.osminfo_menu, self.actionSettings)

        # add icon to new menu item in Web toolbar
        self.iface.addWebToolBarIcon(self.actionRun)

        # connect action to the run method
        self.actionRun.triggered.connect(self.run)
        self.actionAbout.triggered.connect(self.about)
        self.actionSettings.triggered.connect(self.settings)

        # prepare map tool
        self.mapTool = osminfotool.OSMInfotool(self.iface)
        # self.iface.mapCanvas().mapToolSet.connect(self.mapToolChanged)

    def unload(self):
        """Actions to run when the plugin is unloaded"""
        # remove menu and icon from the menu
        self.iface.removeWebToolBarIcon(self.actionRun)
        self.iface.removePluginWebMenu(self.tr('OSMInfo'), self.actionAbout)
        self.iface.removePluginWebMenu(self.tr('OSMInfo'), self.actionSettings)
        self.iface.removePluginWebMenu(self.tr('OSMInfo'), self.actionRun)

        if self.iface.mapCanvas().mapTool() == self.mapTool:
            self.iface.mapCanvas().unsetMapTool(self.mapTool)

        del self.mapTool

    def run(self):
        """Action to run"""
        self.iface.mapCanvas().setMapTool(self.mapTool)

    def about(self):
        dialog = about_dialog.AboutDialog(os.path.basename(self.plugin_dir))
        dialog.exec_()

    def settings(self):
        d = settingsdialog.SettingsDialog()
        d.exec_()
