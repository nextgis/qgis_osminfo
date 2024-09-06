"""
/***************************************************************************
 Common Plugins settings

 NextGIS
                             -------------------
        begin                : 2014-10-31
        git sha              : $Format:%H$
        copyright            : (C) 2014 by NextGIS
        email                : info@nextgis.com
 ***************************************************************************/

/***************************************************************************
 *                                                                         *
 *   This program is free software; you can redistribute it and/or modify  *
 *   it under the terms of the GNU General Public License as published by  *
 *   the Free Software Foundation; either version 2 of the License, or     *
 *   (at your option) any later version.                                   *
 *                                                                         *
 ***************************************************************************/
"""

from qgis.PyQt.QtCore import QSettings


class PluginSettings:
    _company_name = "NextGIS"
    _product = "OSMInfo"

    @classmethod
    def product_name(cls):
        return cls._product

    @classmethod
    def get_settings(cls):
        return QSettings(cls._company_name, cls._product)

    @classmethod
    def distance_value(cls):
        return cls.get_settings().value("distance", 20, int)

    @classmethod
    def timeout_value(cls):
        return cls.get_settings().value("timeout", 30, int)

    @classmethod
    def set_distance_value(cls, int_val):
        cls.get_settings().setValue("distance", int_val)

    @classmethod
    def set_timeout_value(cls, int_val):
        cls.get_settings().setValue("timeout", int_val)
