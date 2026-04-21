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

import json
from time import perf_counter
from typing import ClassVar, Dict, List, Optional, Sequence
from urllib.parse import urlencode

from qgis.core import (
    QgsApplication,
    QgsFeedback,
    QgsNetworkAccessManager,
    QgsTask,
)
from qgis.PyQt.QtCore import QUrl
from qgis.PyQt.QtNetwork import QNetworkReply, QNetworkRequest

from osminfo.core.constants import PLUGIN_NAME
from osminfo.core.exceptions import OsmInfoNominatimGeocodeError
from osminfo.core.logging import logger
from osminfo.overpass.query_builder.query_context import QueryContext

NOMINATIM_SEARCH_URL = "https://nominatim.openstreetmap.org/search"
NOMINATIM_TIMEOUT_SECONDS = 15
NOMINATIM_USER_AGENT = PLUGIN_NAME
NOMINATIM_AREA_RELATION_OFFSET = 3600000000
NOMINATIM_AREA_WAY_OFFSET = 2400000000


class _NominatimGeocodeCancelledError(OsmInfoNominatimGeocodeError):
    """Raise a dedicated error when the geocoding task is cancelled."""

    def __init__(self) -> None:
        # fmt: off
        message = QgsApplication.translate(
            "Exceptions",
            "Geocoding task was cancelled."
        )
        # fmt: on
        super().__init__(
            log_message=message,
            user_message=message,
        )


class GeocodeTask(QgsTask):
    """Resolve wizard geocoding placeholders through the Nominatim API.

    Fetch and cache Nominatim search results, then populate query-context
    placeholders for ids, areas, bounding boxes, and coordinates.
    """

    _results_cache: ClassVar[Dict[str, List[dict]]] = {}

    def __init__(
        self,
        query_context: QueryContext,
        id_queries: Sequence[str],
        area_queries: Sequence[str],
        bbox_queries: Sequence[str],
        coordinate_queries: Sequence[str],
    ) -> None:
        super().__init__(
            "Geocode wizard placeholders",
            QgsTask.Flag.CanCancel,
        )
        self._initial_query_context = query_context
        self._id_queries = tuple(id_queries)
        self._area_queries = tuple(area_queries)
        self._bbox_queries = tuple(bbox_queries)
        self._coordinate_queries = tuple(coordinate_queries)
        self._query_context = query_context
        self._error: Optional[OsmInfoNominatimGeocodeError] = None
        self._active_feedback: Optional[QgsFeedback] = None

    @property
    def query_context(self) -> QueryContext:
        return self._query_context

    @property
    def error(self) -> Optional[OsmInfoNominatimGeocodeError]:
        return self._error

    def cancel(self) -> None:
        if self._active_feedback is not None:
            self._active_feedback.cancel()
        super().cancel()

    def run(self) -> bool:
        self._error = None
        self._query_context = self._initial_query_context
        started_at = perf_counter()
        status = "failed"

        logger.debug(
            "Starting geocode task: ids=%d, areas=%d, bboxes=%d, coords=%d",
            len(self._id_queries),
            len(self._area_queries),
            len(self._bbox_queries),
            len(self._coordinate_queries),
        )

        try:
            self._query_context = self._resolve_query_context()

            status = "completed"
            return True
        except _NominatimGeocodeCancelledError:
            status = "cancelled"
            return False
        except OsmInfoNominatimGeocodeError as error:
            self._error = error
            logger.warning("Geocoding failed: %s", error.log_message)
            return False
        except Exception as error:
            self._error = OsmInfoNominatimGeocodeError(
                log_message=f"Unexpected geocoding error: {error}",
                user_message=self.tr("Unexpected geocoding error."),
            )
            logger.exception("Unexpected geocoding error")
            return False
        finally:
            logger.debug(
                "Finished geocode task with status %s in %.3f s",
                status,
                perf_counter() - started_at,
            )

    def _resolve_query_context(self) -> QueryContext:
        geocode_ids = self._resolve_ids()
        geocode_areas = self._resolve_areas()
        geocode_bboxes = self._resolve_bboxes()
        geocode_coords = self._resolve_coords()
        return self._initial_query_context.with_geocoding(
            geocode_ids=geocode_ids,
            geocode_areas=geocode_areas,
            geocode_bboxes=geocode_bboxes,
            geocode_coords=geocode_coords,
        )

    def _resolve_ids(self) -> Dict[str, str]:
        resolved_ids: Dict[str, str] = {}
        for search_text in self._id_queries:
            results = self._request_results(search_text)
            resolved_ids[search_text] = self._resolve_id_result(
                search_text,
                results,
            )
        return resolved_ids

    def _resolve_areas(self) -> Dict[str, str]:
        resolved_areas: Dict[str, str] = {}
        for search_text in self._area_queries:
            results = self._request_results(search_text)
            resolved_areas[search_text] = self._resolve_area_result(
                search_text,
                results,
            )
        return resolved_areas

    def _resolve_bboxes(self) -> Dict[str, str]:
        resolved_bboxes: Dict[str, str] = {}
        for search_text in self._bbox_queries:
            results = self._request_results(search_text)
            resolved_bboxes[search_text] = self._resolve_bbox_result(
                search_text,
                results,
            )
        return resolved_bboxes

    def _resolve_coords(self) -> Dict[str, str]:
        resolved_coords: Dict[str, str] = {}
        for search_text in self._coordinate_queries:
            results = self._request_results(search_text)
            resolved_coords[search_text] = self._resolve_coordinate_result(
                search_text,
                results,
            )
        return resolved_coords

    def _request_results(self, search_text: str) -> List[dict]:
        self._check_cancellation()

        # Cache identical lookups because several placeholders may reuse them.
        cached_results = self.__class__._results_cache.get(search_text)
        if cached_results is not None:
            return cached_results

        params = {
            "format": "jsonv2",
            "limit": 10,
            "q": search_text,
        }

        request_url = f"{NOMINATIM_SEARCH_URL}?{urlencode(params)}"
        request = QNetworkRequest(QUrl(request_url))
        request.setRawHeader(
            # QGIS overrides the User-Agent header and does not allow setting
            # it directly, so we use a custom header to pass the user agent
            # to the server. Same header is used by overpass-turbo
            b"X-Requested-With",
            NOMINATIM_USER_AGENT.encode("utf-8"),
        )
        request.setRawHeader(b"Accept", b"application/json")

        timeout_milliseconds = NOMINATIM_TIMEOUT_SECONDS * 1000
        if hasattr(request, "setTransferTimeout"):
            request.setTransferTimeout(timeout_milliseconds)

        feedback = QgsFeedback()
        self._active_feedback = feedback
        network_access_manager = QgsNetworkAccessManager.instance()
        try:
            reply_content = network_access_manager.blockingGet(
                request,
                "",
                False,
                feedback,
            )
        finally:
            self._active_feedback = None

        if self.isCanceled() or feedback.isCanceled():
            raise _NominatimGeocodeCancelledError()

        if reply_content.error() != QNetworkReply.NetworkError.NoError:
            detail = reply_content.errorString()
            raise OsmInfoNominatimGeocodeError(
                log_message=(
                    f"Nominatim request failed for '{search_text}': {detail}"
                ),
                user_message=self.tr(
                    "Failed to geocode '{search_text}'."
                ).format(search_text=search_text),
                detail=detail,
            )

        status_code = reply_content.attribute(
            QNetworkRequest.Attribute.HttpStatusCodeAttribute
        )
        if status_code is not None and int(status_code) >= 400:
            raise OsmInfoNominatimGeocodeError(
                log_message=(
                    f"Nominatim returned HTTP {int(status_code)} for "
                    f"'{search_text}'"
                ),
                user_message=self.tr(
                    "Failed to geocode '{search_text}'."
                ).format(search_text=search_text),
                detail=reply_content.errorString(),
            )

        try:
            results = json.loads(reply_content.content().data())
        except Exception as error:
            raise OsmInfoNominatimGeocodeError(
                log_message="Failed to parse geocoder response",
                user_message=self.tr("Failed to parse geocoder response."),
            ) from error

        if not isinstance(results, list) or len(results) == 0:
            raise OsmInfoNominatimGeocodeError(
                log_message=f"No geocoding result for '{search_text}'",
                user_message=self.tr(
                    "No geocoding result for '{search_text}'."
                ).format(search_text=search_text),
            )

        self.__class__._results_cache[search_text] = results

        return results

    def _resolve_area_result(
        self, search_text: str, results: List[dict]
    ) -> str:
        for result in results:
            area_reference = self._nominatim_area_reference(result)
            if area_reference is not None:
                return area_reference

        raise OsmInfoNominatimGeocodeError(
            log_message=(
                f"No supported area result found for '{search_text}'"
            ),
            user_message=self.tr(
                "No supported area result found for '{search_text}'."
            ).format(search_text=search_text),
        )

    def _resolve_id_result(self, search_text: str, results: List[dict]) -> str:
        for result in results:
            osm_reference = self._nominatim_object_reference(result)
            if osm_reference is not None:
                return osm_reference

        raise OsmInfoNominatimGeocodeError(
            log_message=f"No supported id result found for '{search_text}'",
            user_message=self.tr(
                "No supported id result found for '{search_text}'."
            ).format(search_text=search_text),
        )

    def _resolve_bbox_result(
        self, search_text: str, results: List[dict]
    ) -> str:
        for result in results:
            bbox = self._nominatim_bbox_reference(result)
            if bbox is not None:
                return bbox

        raise OsmInfoNominatimGeocodeError(
            log_message=(
                f"No supported bounding box result found for '{search_text}'"
            ),
            user_message=self.tr(
                "No supported bounding box result found for '{search_text}'."
            ).format(search_text=search_text),
        )

    def _resolve_coordinate_result(
        self,
        search_text: str,
        results: List[dict],
    ) -> str:
        best_result = results[0]
        try:
            latitude = float(best_result["lat"])
            longitude = float(best_result["lon"])
        except (KeyError, TypeError, ValueError) as error:
            raise OsmInfoNominatimGeocodeError(
                log_message=f"Invalid coordinate result for '{search_text}'",
                user_message=self.tr(
                    "Invalid geocoder result for '{search_text}'."
                ).format(search_text=search_text),
                detail=str(error),
            ) from error

        return QueryContext.format_center(latitude, longitude)

    def _nominatim_area_reference(self, result: dict) -> Optional[str]:
        osm_type = str(result.get("osm_type", "")).lower()
        try:
            osm_id = int(result["osm_id"])
        except (KeyError, TypeError, ValueError):
            return None

        if osm_type == "relation":
            area_id = NOMINATIM_AREA_RELATION_OFFSET + osm_id
            return f"area(id:{area_id})"
        if osm_type == "way":
            area_id = NOMINATIM_AREA_WAY_OFFSET + osm_id
            return f"area(id:{area_id},{osm_id})"

        return None

    def _nominatim_object_reference(self, result: dict) -> Optional[str]:
        osm_type = str(result.get("osm_type", "")).lower()
        if len(osm_type) == 0:
            return None

        try:
            osm_id = int(result["osm_id"])
        except (KeyError, TypeError, ValueError):
            return None

        return f"{osm_type}(id:{osm_id})"

    def _nominatim_bbox_reference(self, result: dict) -> Optional[str]:
        try:
            bounding_box = result["boundingbox"]
            south = float(bounding_box[0])
            north = float(bounding_box[1])
            west = float(bounding_box[2])
            east = float(bounding_box[3])
        except (KeyError, TypeError, ValueError, IndexError):
            return None

        return QueryContext.format_bbox_coordinates(
            south,
            west,
            north,
            east,
        )

    def _check_cancellation(self) -> None:
        if self.isCanceled():
            raise _NominatimGeocodeCancelledError()
