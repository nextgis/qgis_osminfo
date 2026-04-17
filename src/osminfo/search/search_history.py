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

from typing import ClassVar, List

from qgis.core import QgsSettings

from osminfo.core.constants import PLUGIN_SETTINGS_GROUP


class SearchHistory:
    _HISTORY_GROUP: ClassVar[str] = f"{PLUGIN_SETTINGS_GROUP}/search/history"
    _MAX_SIZE_KEY: ClassVar[str] = f"{_HISTORY_GROUP}/maxSize"
    _ITEMS_KEY: ClassVar[str] = f"{_HISTORY_GROUP}/items"

    _settings: QgsSettings

    def __init__(self) -> None:
        self._settings = QgsSettings()

    @property
    def max_size(self) -> int:
        return self._settings.value(self._MAX_SIZE_KEY, 5, type=int)

    @max_size.setter
    def max_size(self, value: int) -> None:
        self._settings.setValue(self._MAX_SIZE_KEY, value)

    @property
    def items(self) -> List[str]:
        return self._settings.value(self._ITEMS_KEY, [], type=list)

    def add_item(self, item: str) -> None:
        items = self.items
        if item in items:
            index = items.index(item)
            items.pop(index)

        items.insert(0, item)

        self._settings.setValue(self._ITEMS_KEY, items[: self.max_size])

    def clear(self) -> None:
        self._settings.setValue(self._ITEMS_KEY, [])
