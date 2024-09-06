# -*- coding: utf-8 -*-
# ******************************************************************************
#
# OSMInfo
# ---------------------------------------------------------
# This plugin takes coordinates of a mouse click and gets information about all
# objects from this point from OSM using Overpass API.
#
# Author:   Maxim Dubinin, sim@gis-lab.info
# *****************************************************************************
# Copyright (c) 2015. NextGIS, info@nextgis.com
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

from qgis.PyQt import uic
from qgis.PyQt.QtCore import QLocale, QUrl, QSettings
from qgis.PyQt.QtWidgets import QDialogButtonBox, QDialog
from qgis.PyQt.QtGui import QPixmap, QDesktopServices

from .plugin_settings import PluginSettings
from . import resources  # noqa: F401
import configparser

FORM_CLASS, _ = uic.loadUiType(
    os.path.join(os.path.dirname(__file__), "ui/settingsdialogbase.ui")
)


class SettingsDialog(QDialog, FORM_CLASS):
    def __init__(self, parent=None):
        super(SettingsDialog, self).__init__(parent)
        self.setupUi(self)
        self.fill_pages()

        self.btnHelp = self.buttonBox.button(QDialogButtonBox.Help)

        self.lblLogo.setPixmap(QPixmap(":/plugins/osminfo/icons/osminfo.png"))

        cfg = configparser.ConfigParser()
        cfg.read(os.path.join(os.path.dirname(__file__), "metadata.txt"))
        version = cfg.get("general", "version")
        self.lblName.setText(self.tr("OSMInfo Settings"))
        self.lblDistance.setText(self.tr("Distance"))
        self.lblTimeout.setText(self.tr("Timeout"))

        self.buttonBox.helpRequested.connect(self.openHelp)
        self.accepted.connect(self.save_settings)

    def fill_pages(self):
        # common
        self.distSpinner.setValue(PluginSettings.distance_value())
        self.timeoutSpinner.setValue(PluginSettings.timeout_value())

    def save_settings(self):
        # common
        PluginSettings.set_distance_value(self.distSpinner.value())
        PluginSettings.set_timeout_value(self.timeoutSpinner.value())

    def reject(self):
        QDialog.reject(self)

    def openHelp(self):
        overrideLocale = QSettings().value(
            "locale/overrideFlag", False, type=bool
        )
        if not overrideLocale:
            localeFullName = QLocale.system().name()
        else:
            localeFullName = QSettings().value("locale/userLocale", "")

        localeShortName = localeFullName[0:2]
        if localeShortName in ["ru", "uk"]:
            QDesktopServices.openUrl(
                QUrl("http://gis-lab.info/qa/osminfo.html")
            )
        else:
            QDesktopServices.openUrl(
                QUrl("http://gis-lab.info/qa/osminfo-en.html")
            )
