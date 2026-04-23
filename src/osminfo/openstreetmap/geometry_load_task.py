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
from typing import Dict, Iterable, Optional, Set, Tuple

from qgis.core import QgsTask

from osminfo.core.exceptions import OsmInfoOverpassParsingError
from osminfo.core.logging import logger
from osminfo.openstreetmap.features_parser import OsmFeaturesParser
from osminfo.openstreetmap.models import OsmElement


class OverpassGeometryLoadTask(QgsTask):
    def __init__(
        self,
        locale_name: str,
        raw_elements: Iterable[dict],
        element_keys: Set[Tuple[str, int]],
    ) -> None:
        super().__init__(
            "Load Overpass feature geometries",
            QgsTask.Flag.CanCancel,
        )
        self._locale_name = locale_name
        self._raw_elements = tuple(raw_elements)
        self._element_keys = set(element_keys)
        self._parsed_elements: Dict[Tuple[str, int], OsmElement] = {}
        self._error: Optional[OsmInfoOverpassParsingError] = None

    @property
    def parsed_elements(self) -> Dict[Tuple[str, int], OsmElement]:
        return dict(self._parsed_elements)

    @property
    def error(self) -> Optional[OsmInfoOverpassParsingError]:
        return self._error

    def run(self) -> bool:
        self._error = None
        self._parsed_elements = {}
        started_at = perf_counter()
        status = "failed"

        logger.debug(
            "Starting geometry load task for %d Overpass elements with %d raw context elements",
            len(self._element_keys),
            len(self._raw_elements),
        )

        try:
            parser = OsmFeaturesParser(self._locale_name)
            self._parsed_elements = parser.parse_elements_by_keys(
                self._raw_elements,
                self._element_keys,
            )
            if self.isCanceled():
                status = "canceled"
                return False

            status = "completed"
            return True
        except Exception as error:
            self._error = OsmInfoOverpassParsingError(
                log_message=(
                    f"Failed to load Overpass feature geometries: {error}"
                ),
                user_message=self.tr("Failed to load feature geometry."),
                detail=str(error),
            )
            logger.exception("Failed to load Overpass feature geometries")
            return False
        finally:
            logger.debug(
                "Finished geometry load task with status %s in %.3f s",
                status,
                perf_counter() - started_at,
            )
