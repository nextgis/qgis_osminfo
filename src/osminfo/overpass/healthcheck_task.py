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
import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Dict, List, Optional, Tuple
from urllib.parse import urlencode, urlparse

from qgis.core import (
    QgsApplication,
    QgsFeedback,
    QgsNetworkAccessManager,
    QgsTask,
)
from qgis.PyQt.QtCore import QByteArray, QUrl
from qgis.PyQt.QtNetwork import QNetworkReply, QNetworkRequest

from osminfo.core.exceptions import (
    OsmInfoOverpassHealthCheckError,
    OsmInfoOverpassHealthCheckNetworkError,
    OsmInfoOverpassHealthCheckWarning,
)
from osminfo.core.logging import logger

OVERPASS_STATUS_REQUEST_TIMEOUT_SECONDS = 10
OVERPASS_METADATA_REQUEST_TIMEOUT_SECONDS = 10

OVERPASS_WARNING_LATENCY_MILLISECONDS = 1000
OVERPASS_FAILURE_LATENCY_MILLISECONDS = 2000

OVERPASS_WARNING_RUNNING_QUERIES = 5
OVERPASS_FAILURE_RUNNING_QUERIES = 10

OVERPASS_OK_SLOTS_AVAILABLE_RATIO = 0.5
OVERPASS_WARNING_SLOTS_AVAILABLE_RATIO = 0.25

OVERPASS_WARNING_DATA_AGE_MINUTES = 120
OVERPASS_FAILURE_DATA_AGE_MINUTES = 24 * 60

OVERPASS_METADATA_QUERY = "[out:json][timeout:5];node(1);out meta;"

OVERPASS_HTTP_ERROR_MESSAGES = {
    400: "Bad request",
    429: "Rate limited",
    502: "Bad gateway",
    503: "Service unavailable",
    504: "Gateway timeout",
}

OVERPASS_OPTIONAL_STATUS_HTTP_CODES = {403, 404, 405, 501}

OVERPASS_GENERATOR_PATTERN = re.compile(r"Overpass API ([\d.]+)\s*(\w+)?")
OVERPASS_SLOTS_AVAILABLE_PATTERN = re.compile(r"(\d+) slots")
OVERPASS_NEXT_SLOT_PATTERN = re.compile(r"Slot available after: ([^,]+)")


class _OverpassHealthCheckCancelledError(OsmInfoOverpassHealthCheckError):
    def __init__(self) -> None:
        # fmt: off
        message = QgsApplication.translate(
            "Exceptions",
            "Overpass health check was cancelled"
        )
        # fmt: on
        super().__init__(
            log_message=message,
            user_message=message,
        )


class HealthCheckStatus(Enum):
    """Describe the overall result of a health check."""

    SUCCESS = "Success"
    WARNING = "Warning"
    FAILURE = "Failure"


@dataclass
class OverpassVersionInfo:
    """Store parsed Overpass generator version details.

    Keep the original generator string together with parsed version parts
    that can be shown in logs or diagnostic output.

    :ivar full: Store the original generator string.
    :ivar version: Store the extracted version value.
    :ivar commit: Store the optional commit or build suffix.
    """

    full: str
    version: str
    commit: Optional[str] = None


@dataclass
class OverpassRunningQuery:
    """Store information about a running Overpass query.

    Represent one entry from the status endpoint running-queries block.

    :ivar pid: Store the Overpass process identifier.
    :ivar space_limit: Store the memory limit reported by the server.
    :ivar time_limit: Store the execution time limit.
    :ivar start_time: Store the reported query start time.
    """

    pid: str
    space_limit: str
    time_limit: str
    start_time: str


class OverpassTimestampType(Enum):
    """Describe how the metadata timestamp value was interpreted."""

    ISO_8601 = "iso_8601"
    OPAQUE = "opaque"


@dataclass
class OverpassTimestampInfo:
    """Store metadata timestamp parsing results.

    Preserve both the original timestamp value and the parsed UTC datetime
    when the value matches a supported ISO 8601 format.

    :ivar raw_value: Store the original timestamp text.
    :ivar value_type: Describe how the timestamp was classified.
    :ivar parsed_utc: Store the parsed UTC datetime when available.
    """

    raw_value: str
    value_type: OverpassTimestampType
    parsed_utc: Optional[datetime] = None


@dataclass
class OverpassHealthCheckDetails:
    """Store raw metrics collected during a health check.

    Aggregate status endpoint values, metadata endpoint values, and any
    diagnostic errors so callers can inspect the measured server state.

    :ivar service_url: Store the normalized Overpass service URL.
    :ivar status_url: Store the resolved status endpoint URL.
    :ivar interpreter_url: Store the resolved interpreter endpoint URL.
    :ivar checked_at: Store the UTC timestamp of the check start.
    :ivar latency_milliseconds: Store the measured request latency.
    :ivar connection_id: Store the connection identifier from status.
    :ivar current_time: Store the server-reported current time.
    :ivar announced_endpoint: Store the announced endpoint value.
    :ivar rate_limit: Store the total query slot count.
    :ivar slots_available: Store the available query slot count.
    :ivar slots_total: Store the total query slot count.
    :ivar slots_used: Store the computed used slot count.
    :ivar slots_available_ratio: Store the available slot ratio.
    :ivar running_queries: Store running query entries.
    :ivar next_slot_times: Store reported slot release times.
    :ivar timestamp_osm_base: Store parsed osm_base timestamp details.
    :ivar data_age_minutes: Store the computed replication lag in minutes.
    :ivar generator: Store the metadata generator string.
    :ivar version: Store parsed generator version details.
    :ivar status_error: Store the status request error, if any.
    :ivar metadata_error: Store the metadata request error, if any.
    """

    service_url: str
    status_url: str
    interpreter_url: str
    checked_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    latency_milliseconds: Optional[int] = None
    connection_id: Optional[str] = None
    current_time: Optional[str] = None
    announced_endpoint: Optional[str] = None
    rate_limit: Optional[int] = None
    slots_available: Optional[int] = None
    slots_total: Optional[int] = None
    slots_used: Optional[int] = None
    slots_available_ratio: Optional[float] = None
    running_queries: List[OverpassRunningQuery] = field(default_factory=list)
    next_slot_times: List[str] = field(default_factory=list)
    timestamp_osm_base: Optional[OverpassTimestampInfo] = None
    data_age_minutes: Optional[int] = None
    generator: Optional[str] = None
    version: Optional[OverpassVersionInfo] = None
    status_error: Optional[str] = None
    metadata_error: Optional[str] = None


class HealthCheckTask(QgsTask):
    """Run a health check against an Overpass API endpoint.

    Query the status and interpreter endpoints, evaluate the collected
    metrics, and expose the resulting state through task properties.
    """

    def __init__(self, overpass_url: str) -> None:
        """Initialize the task for an Overpass endpoint.

        :param overpass_url: Identify the Overpass base or endpoint URL.
        :raises OsmInfoOverpassHealthCheckError: If the URL is invalid.
        """
        (
            self._service_url,
            self._status_url,
            self._interpreter_url,
        ) = self._resolve_endpoint_urls(overpass_url)
        description = f"Overpass health check: {self._service_url}"
        super().__init__(description, QgsTask.Flag.CanCancel)

        self._status: Optional[HealthCheckStatus] = None
        self._warning: str = ""
        self._error: Optional[OsmInfoOverpassHealthCheckError] = None
        self._details = OverpassHealthCheckDetails(
            service_url=self._service_url,
            status_url=self._status_url,
            interpreter_url=self._interpreter_url,
        )
        self._active_feedback: Optional[QgsFeedback] = None

    @property  # type: ignore
    def check_status(self) -> Optional[HealthCheckStatus]:
        """Return the evaluated health check status.

        :return: Return the final task status when available.
        """
        return self._status

    @property
    def warning(self) -> str:
        """Return warning text collected during the check.

        :return: Return aggregated warning messages.
        """
        return self._warning

    @property
    def error(self) -> Optional[OsmInfoOverpassHealthCheckError]:
        """Return the error collected during the check.

        :return: Return the final task error when available.
        """
        return self._error

    @property
    def details(self) -> OverpassHealthCheckDetails:
        """Return collected diagnostic details.

        :return: Return the structure with measured endpoint details.
        """
        return self._details

    def cancel(self) -> None:
        """Cancel the active request and the task itself."""

        if self._active_feedback is not None:
            self._active_feedback.cancel()

        super().cancel()

    def run(self) -> bool:
        """Execute the health check workflow.

        Reset previously collected state, query the Overpass endpoints,
        evaluate the collected metrics, and update task result fields.

        :return: Return True when the workflow finishes without task-level
            failure, otherwise return False.
        """

        self._status = None
        self._warning = ""
        self._error = None
        self._details = OverpassHealthCheckDetails(
            service_url=self._service_url,
            status_url=self._status_url,
            interpreter_url=self._interpreter_url,
        )
        started_at = time.perf_counter()
        status = "failed"

        logger.debug(f"Starting Overpass health check for {self._service_url}")

        try:
            self._run_health_check()

            status = "completed"
            logger.debug(
                "Overpass health check finished with status %s in %.3f s\n%s",
                self.check_status.value
                if self.check_status is not None
                else "unknown",
                time.perf_counter() - started_at,
                self._format_details_for_debug(),
            )
            return True
        except _OverpassHealthCheckCancelledError as error:
            self._status = HealthCheckStatus.FAILURE
            self._error = error
            status = "cancelled"
            return False
        except OsmInfoOverpassHealthCheckError as error:
            self._status = HealthCheckStatus.FAILURE
            self._error = error
            logger.warning(
                "Overpass health check failed: %s",
                error.log_message,
            )
            return False
        except Exception as error:
            self._status = HealthCheckStatus.FAILURE
            self._error = OsmInfoOverpassHealthCheckError(
                log_message=(
                    f"Unexpected Overpass health check error: {error}"
                ),
                user_message=str(error),
                detail=repr(error),
            )
            logger.exception("Unexpected Overpass health check error")
            return False
        finally:
            logger.debug(
                "Finished Overpass health check task for %s with status %s in %.3f s",
                self._service_url,
                status,
                time.perf_counter() - started_at,
            )

    def _run_health_check(self) -> None:
        warnings: List[OsmInfoOverpassHealthCheckWarning] = []

        (
            status_warning,
            status_request_succeeded,
        ) = self._update_status()
        if status_warning is not None:
            warnings.append(status_warning)
            logger.debug(
                "Status warning: %s",
                status_warning.user_message,
            )

        (
            metadata_warning,
            metadata_request_succeeded,
        ) = self._update_metadata()
        if metadata_warning is not None:
            warnings.append(metadata_warning)
            logger.debug(
                "Metadata warning: %s",
                metadata_warning.user_message,
            )

        if not status_request_succeeded and not metadata_request_succeeded:
            logger.debug("Both Overpass requests failed")
            raise OsmInfoOverpassHealthCheckError(
                log_message=(
                    "Overpass status and metadata requests both failed "
                    f"for {self._service_url}"
                ),
                user_message=self.tr(
                    "Failed to connect to Overpass API status and "
                    "interpreter endpoints"
                ),
            )

        self._evaluate_result(warnings)

    def _update_status(
        self,
    ) -> Tuple[Optional[OsmInfoOverpassHealthCheckWarning], bool]:
        try:
            status_text = self._request_text(
                url=self._status_url,
                method="GET",
                timeout=OVERPASS_STATUS_REQUEST_TIMEOUT_SECONDS,
            )
        except _OverpassHealthCheckCancelledError:
            raise
        except OsmInfoOverpassHealthCheckNetworkError as error:
            if error.http_status_code in OVERPASS_OPTIONAL_STATUS_HTTP_CODES:
                self._details.status_error = error.user_message
                logger.debug(
                    "Overpass status endpoint is unavailable: %s (%s)",
                    error.request_url,
                    error.log_message,
                )
                return None, False

            warning = OsmInfoOverpassHealthCheckWarning(
                log_message="Overpass status request failed",
                user_message=f"Status check failed: {error.user_message}",
                detail=error.detail,
            )
            self._details.status_error = warning.user_message
            return warning, False

        self._parse_status_response(status_text)
        logger.debug("Parsed Overpass status response")
        return None, True

    def _update_metadata(
        self,
    ) -> Tuple[Optional[OsmInfoOverpassHealthCheckWarning], bool]:
        payload = urlencode({"data": OVERPASS_METADATA_QUERY}).encode("utf-8")
        try:
            response_text = self._request_text(
                url=self._interpreter_url,
                method="POST",
                data=payload,
                timeout=OVERPASS_METADATA_REQUEST_TIMEOUT_SECONDS,
                headers={
                    "Content-Type": "application/x-www-form-urlencoded",
                },
            )
        except _OverpassHealthCheckCancelledError:
            raise
        except OsmInfoOverpassHealthCheckNetworkError as error:
            warning = OsmInfoOverpassHealthCheckWarning(
                log_message="Overpass metadata request failed",
                user_message=f"Metadata check failed: {error.user_message}",
                detail=error.detail,
            )
            self._details.metadata_error = warning.user_message
            return warning, False

        try:
            metadata = json.loads(response_text)
        except Exception as error:
            warning = OsmInfoOverpassHealthCheckWarning(
                log_message="Overpass metadata parsing failed",
                user_message="Metadata response parsing failed",
                detail=str(error),
            )
            self._details.metadata_error = warning.user_message
            return warning, True

        timestamp_osm_base = metadata.get("osm3s", {}).get(
            "timestamp_osm_base"
        )
        if isinstance(timestamp_osm_base, str):
            timestamp_info = self._parse_timestamp_osm_base(timestamp_osm_base)
            self._details.timestamp_osm_base = timestamp_info
            if timestamp_info.parsed_utc is not None:
                self._details.data_age_minutes = (
                    self._calculate_data_age_minutes(timestamp_info.parsed_utc)
                )

        generator = metadata.get("generator")
        if isinstance(generator, str):
            self._details.generator = generator
            self._details.version = self._parse_generator(generator)

        logger.debug("Parsed Overpass metadata response")

        return None, True

    def _evaluate_result(
        self,
        warnings: List[OsmInfoOverpassHealthCheckWarning],
    ) -> None:
        failure_messages: List[str] = []
        warning_messages: List[str] = []

        latency_milliseconds = self._details.latency_milliseconds
        if latency_milliseconds is not None:
            if latency_milliseconds >= OVERPASS_FAILURE_LATENCY_MILLISECONDS:
                failure_messages.append(
                    f"Latency is too high: {latency_milliseconds} ms"
                )
            elif latency_milliseconds >= OVERPASS_WARNING_LATENCY_MILLISECONDS:
                warning_messages.append(
                    f"Latency is elevated: {latency_milliseconds} ms"
                )

        running_queries_count = len(self._details.running_queries)
        if running_queries_count >= OVERPASS_FAILURE_RUNNING_QUERIES:
            failure_messages.append(
                f"Too many running queries: {running_queries_count}"
            )
        elif running_queries_count >= OVERPASS_WARNING_RUNNING_QUERIES:
            warning_messages.append(
                f"High number of running queries: {running_queries_count}"
            )

        slots_available_ratio = self._details.slots_available_ratio
        if slots_available_ratio is not None:
            if slots_available_ratio < OVERPASS_WARNING_SLOTS_AVAILABLE_RATIO:
                failure_messages.append(
                    "Too few query slots available: "
                    f"{self._details.slots_available}/{self._details.slots_total}"
                )
            elif slots_available_ratio <= OVERPASS_OK_SLOTS_AVAILABLE_RATIO:
                warning_messages.append(
                    "Limited query slots available: "
                    f"{self._details.slots_available}/{self._details.slots_total}"
                )
        elif self._details.slots_available == 0:
            warning_messages.append("No query slots are currently available")

        data_age_minutes = self._details.data_age_minutes
        if data_age_minutes is not None:
            if data_age_minutes >= OVERPASS_FAILURE_DATA_AGE_MINUTES:
                failure_messages.append(
                    f"Data is stale: {data_age_minutes} minutes old"
                )
            elif data_age_minutes >= OVERPASS_WARNING_DATA_AGE_MINUTES:
                warning_messages.append(
                    f"Data age is elevated: {data_age_minutes} minutes"
                )

        for warning in warnings:
            warning_messages.append(warning.user_message)

        if failure_messages:
            self._status = HealthCheckStatus.FAILURE
            self._error = OsmInfoOverpassHealthCheckError(
                log_message="; ".join(failure_messages),
                user_message="; ".join(failure_messages),
            )
            self._warning = "; ".join(warning_messages)
            logger.debug(
                "Overpass health check result: failure\nFailures:\n%s\nWarnings:\n%s",
                self._format_messages_for_debug(failure_messages),
                self._format_messages_for_debug(warning_messages),
            )
            return

        if warning_messages:
            self._status = HealthCheckStatus.WARNING
            self._warning = "; ".join(warning_messages)
            self._error = None
            logger.debug(
                "Overpass health check result: warning\nWarnings:\n%s",
                self._format_messages_for_debug(warning_messages),
            )
            return

        self._status = HealthCheckStatus.SUCCESS
        self._warning = ""
        self._error = None
        logger.debug("Overpass health check result: success")

    def _parse_status_response(self, status_text: str) -> None:
        self._check_cancellation()

        lines = status_text.splitlines()
        running_queries: List[OverpassRunningQuery] = []
        next_slot_times: List[str] = []
        slots_used = 0
        is_running_queries_block = False

        for line in lines:
            self._check_cancellation()

            stripped_line = line.strip()
            if line.startswith("Connected as:"):
                self._details.connection_id = line.replace(
                    "Connected as:", ""
                ).strip()
            elif line.startswith("Current time:"):
                self._details.current_time = line.replace(
                    "Current time:", ""
                ).strip()
            elif line.startswith("Announced endpoint:"):
                self._details.announced_endpoint = line.replace(
                    "Announced endpoint:", ""
                ).strip()
            elif line.startswith("Rate limit:"):
                rate_limit_text = line.replace("Rate limit:", "").strip()
                self._details.rate_limit = self._parse_int(rate_limit_text)
                self._details.slots_total = self._details.rate_limit
            elif "slots available" in line:
                slots_match = OVERPASS_SLOTS_AVAILABLE_PATTERN.search(line)
                if slots_match is not None:
                    self._details.slots_available = int(slots_match.group(1))
            elif line.startswith("Currently running queries"):
                is_running_queries_block = True
            elif "Slot available after" in line:
                slots_used += 1
                next_slot_match = OVERPASS_NEXT_SLOT_PATTERN.search(line)
                if next_slot_match is not None:
                    next_slot_times.append(next_slot_match.group(1).strip())
            elif is_running_queries_block and stripped_line:
                parts = stripped_line.split()
                if len(parts) >= 4:
                    running_queries.append(
                        OverpassRunningQuery(
                            pid=parts[0],
                            space_limit=parts[1],
                            time_limit=parts[2],
                            start_time=" ".join(parts[3:]),
                        )
                    )

        slots_used = max(slots_used, len(running_queries))
        if (
            self._details.slots_total is not None
            and self._details.slots_available is not None
        ):
            slots_used = (
                self._details.slots_total - self._details.slots_available
            )
            if self._details.slots_total > 0:
                self._details.slots_available_ratio = (
                    self._details.slots_available / self._details.slots_total
                )

        self._details.running_queries = running_queries
        self._details.next_slot_times = next_slot_times
        self._details.slots_used = slots_used

    def _request_text(
        self,
        url: str,
        method: str,
        timeout: int,
        data: Optional[bytes] = None,
        headers: Optional[Dict[str, str]] = None,
    ) -> str:
        self._check_cancellation()

        logger.debug(
            "Sending Overpass %s request to %s",
            method,
            url,
        )

        request = QNetworkRequest(QUrl(url))
        timeout_milliseconds = timeout * 1000
        if hasattr(request, "setTransferTimeout"):
            request.setTransferTimeout(timeout_milliseconds)

        if headers is not None:
            for header_name, header_value in headers.items():
                request.setRawHeader(
                    header_name.encode("utf-8"),
                    header_value.encode("utf-8"),
                )

        feedback = QgsFeedback()
        self._active_feedback = feedback
        qgs_network_access_manager = QgsNetworkAccessManager.instance()

        started_at = time.perf_counter()
        try:
            if method == "GET":
                reply_content = qgs_network_access_manager.blockingGet(
                    request,
                    "",
                    False,
                    feedback,
                )
            elif method == "POST":
                payload = QByteArray(data if data is not None else b"")
                reply_content = qgs_network_access_manager.blockingPost(
                    request,
                    payload,
                    "",
                    False,
                    feedback,
                )
            else:
                raise OsmInfoOverpassHealthCheckError(
                    log_message=f"Unsupported HTTP method: {method}",
                    user_message="Unsupported HTTP method for health check.",
                )
        finally:
            self._active_feedback = None

        if self.isCanceled() or feedback.isCanceled():
            raise _OverpassHealthCheckCancelledError()

        elapsed_milliseconds = int(
            round((time.perf_counter() - started_at) * 1000)
        )
        if url == self._status_url or (
            url == self._interpreter_url
            and self._details.latency_milliseconds is None
        ):
            self._details.latency_milliseconds = elapsed_milliseconds

        network_error = reply_content.error()
        if network_error != QNetworkReply.NetworkError.NoError:
            status_code = reply_content.attribute(
                QNetworkRequest.Attribute.HttpStatusCodeAttribute
            )
            detail = reply_content.errorString()
            if status_code is not None:
                raise OsmInfoOverpassHealthCheckNetworkError(
                    request_url=url,
                    method=method,
                    http_status_code=int(status_code),
                    user_message=self._format_http_error(int(status_code)),
                    detail=detail,
                )

            raise OsmInfoOverpassHealthCheckNetworkError(
                request_url=url,
                method=method,
                user_message=detail,
                detail=detail,
            )

        status_code = reply_content.attribute(
            QNetworkRequest.Attribute.HttpStatusCodeAttribute
        )
        if status_code is not None and int(status_code) >= 400:
            raise OsmInfoOverpassHealthCheckNetworkError(
                request_url=url,
                method=method,
                http_status_code=int(status_code),
                user_message=self._format_http_error(int(status_code)),
                detail=reply_content.errorString(),
            )

        logger.debug(
            "Overpass %s request to %s succeeded in %d ms with HTTP %s",
            method,
            url,
            elapsed_milliseconds,
            status_code,
        )

        content = reply_content.content().data()
        try:
            return content.decode("utf-8")
        except UnicodeDecodeError:
            return content.decode("utf-8", errors="replace")

    def _check_cancellation(self) -> None:
        if self.isCanceled():
            raise _OverpassHealthCheckCancelledError()

    @classmethod
    def _resolve_endpoint_urls(cls, overpass_url: str) -> Tuple[str, str, str]:
        normalized_url = overpass_url.strip().rstrip("/")
        parsed_url = urlparse(normalized_url)
        if not parsed_url.scheme or not parsed_url.netloc:
            raise OsmInfoOverpassHealthCheckError(
                log_message=f"Invalid Overpass URL: {overpass_url}",
                user_message="Invalid Overpass URL.",
                detail=overpass_url,
            )

        path = parsed_url.path.rstrip("/")
        lowered_path = path.lower()

        service_path = ""

        if lowered_path.endswith("/interpreter"):
            service_path = path[: -len("/interpreter")]
        elif lowered_path.endswith("/status"):
            service_path = path[: -len("/status")]
        elif lowered_path.endswith("/api"):
            service_path = path
        elif path:
            service_path = f"{path}/api"

        if not service_path:
            raise OsmInfoOverpassHealthCheckError(
                log_message=f"Determined empty service path from URL: {overpass_url}",
                user_message="Invalid Overpass URL path.",
            )

        service_url = cls._build_url(parsed_url, service_path)
        status_url = cls._build_url(parsed_url, f"{service_path}/status")
        interpreter_url = cls._build_url(
            parsed_url,
            f"{service_path}/interpreter",
        )

        return service_url, status_url, interpreter_url

    @staticmethod
    def _build_url(parsed_url, path: str) -> str:
        normalized_path = path or "/"
        return parsed_url._replace(
            path=normalized_path,
            params="",
            query="",
            fragment="",
        ).geturl()

    @staticmethod
    def _parse_int(value: str) -> Optional[int]:
        match = re.search(r"\d+", value)
        if match is None:
            return None
        return int(match.group(0))

    @staticmethod
    def _parse_generator(generator: str) -> OverpassVersionInfo:
        match = OVERPASS_GENERATOR_PATTERN.match(generator)
        if match is None:
            return OverpassVersionInfo(full=generator, version=generator)

        return OverpassVersionInfo(
            full=generator,
            version=match.group(1),
            commit=match.group(2),
        )

    @staticmethod
    def _parse_timestamp_osm_base(
        timestamp: str,
    ) -> OverpassTimestampInfo:
        parsed_timestamp = HealthCheckTask._parse_timestamp(timestamp)
        if parsed_timestamp is not None:
            return OverpassTimestampInfo(
                raw_value=timestamp,
                value_type=OverpassTimestampType.ISO_8601,
                parsed_utc=parsed_timestamp,
            )

        return OverpassTimestampInfo(
            raw_value=timestamp,
            value_type=OverpassTimestampType.OPAQUE,
        )

    @staticmethod
    def _calculate_data_age_minutes(
        parsed_timestamp: datetime,
    ) -> Optional[int]:
        diff = datetime.now(timezone.utc) - parsed_timestamp
        if diff.total_seconds() < 0:
            return 0

        return int(diff.total_seconds() // 60)

    def _format_details_for_debug(self) -> str:
        timestamp_info = self._details.timestamp_osm_base
        timestamp_value = "None"
        if timestamp_info is not None:
            parsed_utc = (
                timestamp_info.parsed_utc.isoformat()
                if timestamp_info.parsed_utc is not None
                else "None"
            )
            timestamp_value = (
                f"raw={timestamp_info.raw_value}, "
                f"type={timestamp_info.value_type.value}, "
                f"parsed_utc={parsed_utc}"
            )

        version_value = "None"
        if self._details.version is not None:
            version_value = (
                f"full={self._details.version.full}, "
                f"version={self._details.version.version}, "
                f"commit={self._details.version.commit}"
            )

        next_slot_times = ", ".join(self._details.next_slot_times)
        if next_slot_times == "":
            next_slot_times = "None"

        fields = [
            f"  latency_milliseconds: {self._details.latency_milliseconds}",
            f"  connection_id: {self._details.connection_id}",
            f"  current_time: {self._details.current_time}",
            f"  rate_limit: {self._details.rate_limit}",
            f"  slots_available: {self._details.slots_available}",
            f"  slots_total: {self._details.slots_total}",
            f"  slots_used: {self._details.slots_used}",
            (
                "  slots_available_ratio: "
                f"{self._details.slots_available_ratio}"
            ),
            (f"  running_queries_count: {len(self._details.running_queries)}"),
            f"  next_slot_times: {next_slot_times}",
            f"  timestamp_osm_base: {timestamp_value}",
            f"  data_age_minutes: {self._details.data_age_minutes}",
            f"  generator: {self._details.generator}",
            f"  version: {version_value}",
            f"  status_error: {self._details.status_error}",
            f"  metadata_error: {self._details.metadata_error}",
        ]

        return "\n".join(fields)

    @staticmethod
    def _format_messages_for_debug(messages: List[str]) -> str:
        if not messages:
            return "  none"

        return "\n".join(f"  - {message}" for message in messages)

    @staticmethod
    def _parse_timestamp(timestamp: str) -> Optional[datetime]:
        formats = (
            "%Y-%m-%dT%H:%M:%SZ",
            "%Y-%m-%dT%H:%M:%S.%fZ",
        )
        for date_format in formats:
            try:
                return datetime.strptime(timestamp, date_format).replace(
                    tzinfo=timezone.utc
                )
            except ValueError:
                continue

        return None

    @staticmethod
    def _format_http_error(status_code: int) -> str:
        return OVERPASS_HTTP_ERROR_MESSAGES.get(
            status_code,
            f"HTTP {status_code}",
        )
