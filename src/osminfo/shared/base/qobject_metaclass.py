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

from abc import ABCMeta

from qgis.PyQt.QtCore import QObject


class QObjectMetaClass(ABCMeta, type(QObject)):
    """Defines a metaclass for QObject-based classes.

    QObjectMetaClass: A metaclass that combines ABCMeta (for abstract base
    classes) and the metaclass of QObject, allowing for the creation of
    abstract Qt objects.
    """
