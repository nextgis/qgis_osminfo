# -*- coding: utf-8 -*-
#******************************************************************************
#
# OSMInfo
# ---------------------------------------------------------
# This plugin takes coordinates of a mouse click and gets information about all 
# objects from this point from OSM using Overpass API.
#
# Author:   Maxim Dubinin, sim@gis-lab.info
# Author:   Alexander Lisovenko, alexander.lisovenko@nextgis.ru
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
#******************************************************************************
import ConfigParser
import os

from PyQt4 import uic
from PyQt4.QtGui import QDialogButtonBox, QPixmap, QTextDocument, QDialog, QDesktopServices
from PySide.QtCore import QSettings, QUrl, QLocale

import resources

FORM_CLASS, _ = uic.loadUiType(os.path.join(os.path.dirname(__file__), 'ui/aboutdialogbase.ui'))


class AboutDialog(QDialog, FORM_CLASS):
    def __init__(self, parent=None):
        super(AboutDialog, self).__init__(parent)
        self.setupUi(self)

        self.btnHelp = self.buttonBox.button(QDialogButtonBox.Help)

        self.lblLogo.setPixmap(QPixmap(':/plugins/osminfo/icons/osminfo.png'))

        cfg = ConfigParser.SafeConfigParser()
        cfg.read(os.path.join(os.path.dirname(__file__), 'metadata.txt'))
        version = cfg.get('general', 'version')

        self.lblVersion.setText(self.tr('Version: %s') % version)
        self.lblName.setText(self.tr('OSMInfo'))

        doc = QTextDocument()
        doc.setHtml(self.getAboutText())
        self.textBrowser.setDocument(doc)
        self.textBrowser.setOpenExternalLinks(True)

        self.buttonBox.helpRequested.connect(self.openHelp)

    def reject(self):
        QDialog.reject(self)

    def openHelp(self):
        overrideLocale = QSettings().value('locale/overrideFlag', False, type=bool)
        if not overrideLocale:
            localeFullName = QLocale.system().name()
        else:
            localeFullName = QSettings().value('locale/userLocale', '')

        localeShortName = localeFullName[0:2]
        if localeShortName in ['ru', 'uk']:
            QDesktopServices.openUrl(QUrl('http://gis-lab.info/qa/osminfo.html'))
        else:
            QDesktopServices.openUrl(QUrl('http://gis-lab.info/qa/qtiles-en.html'))

    def getAboutText(self):
        return self.tr('<p>This plugin takes coordinates of a mouse click and extracts information for nearby and enclosing objects.</p>'
            '<p>It uses Overpass API to extract data from OpenStreetMap.'
            '<p><strong>Developers</strong>: Maxim Dubinin and Alexander Lisovenko'
            ' (<a href="http://nextgis.com">NextGIS</a>).</p>'
            '<p><strong>Homepage</strong>: '
            '<a href="https://github.com/nextgis/osminfo">'
            'https://github.com/nextgis/osminfo</a></p>'
            '<p>Please report bugs at '
            '<a href="https://github.com/nextgis/osminfo/issues">'
            'bugtracker</a></p>'
            )
