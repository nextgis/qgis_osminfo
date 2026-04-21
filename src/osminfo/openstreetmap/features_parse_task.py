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

from time import perf_counter
from typing import Dict, Iterable, Optional

from qgis.core import QgsTask

from osminfo.core.exceptions import OsmInfoOverpassParsingError
from osminfo.core.logging import logger
from osminfo.openstreetmap.features_parser import OsmFeaturesParser
from osminfo.openstreetmap.models import OsmResultGroupType, OsmResultTree


class OverpassFeaturesParseTask(QgsTask):
    def __init__(
        self,
        locale_name: str,
        nearby_elements: Iterable[dict],
        enclosing_elements: Iterable[dict],
        search_elements: Iterable[dict],
        titles: Dict[OsmResultGroupType, str],
    ) -> None:
        super().__init__(
            "Parse Overpass features",
            QgsTask.Flag.CanCancel,
        )
        self._locale_name = locale_name
        self._nearby_elements = tuple(nearby_elements)
        self._enclosing_elements = tuple(enclosing_elements)
        self._search_elements = tuple(search_elements)
        self._titles = dict(titles)
        self._result_tree = OsmResultTree()
        self._error: Optional[OsmInfoOverpassParsingError] = None

    @property
    def result_tree(self) -> OsmResultTree:
        return self._result_tree

    @property
    def error(self) -> Optional[OsmInfoOverpassParsingError]:
        return self._error

    def run(self) -> bool:
        self._error = None
        self._result_tree = OsmResultTree()
        started_at = perf_counter()
        status = "failed"

        logger.debug(
            "Starting Overpass features parse task: nearby=%d, enclosing=%d, search=%d",
            len(self._nearby_elements),
            len(self._enclosing_elements),
            len(self._search_elements),
        )

        try:
            self._result_tree = self._parse_result_tree()

            status = "completed"
            return True
        except Exception as error:
            self._error = OsmInfoOverpassParsingError(
                log_message=f"Failed to parse Overpass features: {error}",
                user_message=self.tr("Failed to parse Overpass features."),
                detail=str(error),
            )
            logger.exception("Failed to parse Overpass features")
            return False
        finally:
            logger.debug(
                "Finished Overpass features parse task with status %s in %.3f s",
                status,
                perf_counter() - started_at,
            )

    def _parse_result_tree(self) -> OsmResultTree:
        parser = OsmFeaturesParser(self._locale_name)
        return parser.parse_result_tree(
            nearby_elements=self._nearby_elements,
            enclosing_elements=self._enclosing_elements,
            search_elements=self._search_elements,
            titles=self._titles,
        )
