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


class SearchRequestFeedbackTracker:
    def __init__(self) -> None:
        self._consecutive_overpass_failures = 0
        self._consecutive_regional_empty_results = 0

    @property
    def consecutive_overpass_failures(self) -> int:
        return self._consecutive_overpass_failures

    @property
    def consecutive_regional_empty_results(self) -> int:
        return self._consecutive_regional_empty_results

    def record_overpass_failure(self) -> bool:
        self._consecutive_overpass_failures += 1
        self._consecutive_regional_empty_results = 0
        return self._consecutive_overpass_failures >= 2

    def record_overpass_success(self) -> None:
        self._consecutive_overpass_failures = 0

    def record_regional_empty_result(
        self,
        *,
        is_empty: bool,
        is_regional_endpoint: bool,
    ) -> bool:
        if not is_empty or not is_regional_endpoint:
            self._consecutive_regional_empty_results = 0
            return False

        self._consecutive_regional_empty_results += 1
        return self._consecutive_regional_empty_results >= 2

    def reset_regional_empty_results(self) -> None:
        self._consecutive_regional_empty_results = 0
