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
from typing import Any, List, Optional

from qgis.core import (
    QgsApplication,
    QgsFeedback,
    QgsNetworkAccessManager,
    QgsTask,
)
from qgis.PyQt.QtCore import QByteArray, QUrl
from qgis.PyQt.QtNetwork import QNetworkReply, QNetworkRequest

from osminfo.core.exceptions import OsmInfoOverpassQueryError
from osminfo.logging import logger
from osminfo.ui.utils import human_readable_size

OVERPASS_TRANSFER_TIMEOUT_MARGIN_SECONDS = 5


class _OverpassQueryCancelledError(OsmInfoOverpassQueryError):
    def __init__(self) -> None:
        message = QgsApplication.translate(
            "Exceptions",
            "Overpass query was cancelled.",
        )
        super().__init__(
            log_message=message,
            user_message=message,
        )


class OverpassQueryTask(QgsTask):
    def __init__(
        self,
        endpoint: str,
        overpass_query: str,
        timeout_seconds: Optional[int] = None,
    ) -> None:
        self._endpoint = endpoint.strip()
        self._overpass_query = overpass_query
        self._timeout_seconds = timeout_seconds
        description = f"Overpass query: {self._endpoint or 'unknown endpoint'}"
        super().__init__(description, QgsTask.Flag.CanCancel)

        self._elements: List[Any] = []
        self._error: Optional[OsmInfoOverpassQueryError] = None
        self._active_feedback: Optional[QgsFeedback] = None

    @property
    def elements(self) -> List[Any]:
        return self._elements

    @property
    def error(self) -> Optional[OsmInfoOverpassQueryError]:
        return self._error

    def cancel(self) -> None:
        if self._active_feedback is not None:
            self._active_feedback.cancel()

        super().cancel()

    def run(self) -> bool:
        self._elements = []
        self._error = None

        try:
            self._elements = self._fetch_elements()
        except _OverpassQueryCancelledError:
            return False
        except OsmInfoOverpassQueryError as error:
            self._error = error
            logger.warning("Overpass query failed: %s", error.log_message)
            return False
        except Exception as error:
            self._error = OsmInfoOverpassQueryError(
                log_message=f"Unexpected Overpass query error: {error}",
                user_message=str(error),
            )
            logger.exception("Unexpected Overpass query error")
            return False

        return True

    def _fetch_elements(self) -> List[Any]:
        if len(self._endpoint) == 0:
            raise OsmInfoOverpassQueryError(
                log_message="Custom Overpass API URL is not set",
                user_message=self.tr("Custom Overpass API URL is not set"),
            )

        self._check_cancellation()

        started_at = perf_counter()

        logger.debug(
            "Running Overpass query for %s\n%s",
            self._endpoint,
            self._overpass_query,
        )

        request = QNetworkRequest(QUrl(self._endpoint))
        request.setHeader(
            QNetworkRequest.KnownHeaders.ContentTypeHeader,
            "application/x-www-form-urlencoded",
        )

        timeout_milliseconds = self._transfer_timeout_milliseconds()
        if timeout_milliseconds is not None and hasattr(
            request, "setTransferTimeout"
        ):
            request.setTransferTimeout(timeout_milliseconds)

        feedback = QgsFeedback()
        self._active_feedback = feedback
        qgs_network_access_manager = QgsNetworkAccessManager.instance()

        try:
            reply_content = qgs_network_access_manager.blockingPost(
                request,
                QByteArray(self._overpass_query.encode("utf-8")),
                "",
                False,
                feedback,
            )
        finally:
            self._active_feedback = None

        if self.isCanceled() or feedback.isCanceled():
            raise _OverpassQueryCancelledError()

        if reply_content.error() != QNetworkReply.NetworkError.NoError:
            detail = reply_content.errorString()
            logger.error(detail)
            raise OsmInfoOverpassQueryError(
                log_message=f"Overpass request failed: {detail}",
                user_message=self.tr("Error getting data from the server"),
                detail=detail,
            )

        response_content = reply_content.content()
        response_size_bytes = int(response_content.size())
        elapsed_seconds = perf_counter() - started_at

        try:
            json_content = json.loads(response_content.data())
        except Exception as error:
            logger.exception("Parsing data error")
            raise OsmInfoOverpassQueryError(
                log_message="Parsing data error",
                user_message=self.tr("Parsing data error"),
                detail=str(error),
            ) from error

        self._check_cancellation()

        if json_content.get("remark") is not None:
            remark = str(json_content["remark"])
            raise OsmInfoOverpassQueryError(
                log_message=f"Overpass API returned remark: {remark}",
                user_message=remark,
            )

        elements = json_content.get("elements", [])
        logger.debug(
            "Fetched %d elements in %.3f s, response size %s",
            len(elements),
            elapsed_seconds,
            human_readable_size(response_size_bytes / 1024.0),
        )
        return elements

    def _check_cancellation(self) -> None:
        if self.isCanceled():
            raise _OverpassQueryCancelledError()

    def _transfer_timeout_milliseconds(self) -> Optional[int]:
        if self._timeout_seconds is None:
            return None

        timeout_seconds = self._timeout_seconds
        timeout_seconds += OVERPASS_TRANSFER_TIMEOUT_MARGIN_SECONDS
        return timeout_seconds * 1000
