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

from osminfo.search.request_feedback_tracker import (
    SearchRequestFeedbackTracker,
)


def test_overpass_failure_hint_is_shown_on_second_failure() -> None:
    tracker = SearchRequestFeedbackTracker()

    assert tracker.record_overpass_failure() is False
    assert tracker.record_overpass_failure() is True
    assert tracker.consecutive_overpass_failures == 2


def test_overpass_success_resets_failure_counter() -> None:
    tracker = SearchRequestFeedbackTracker()

    tracker.record_overpass_failure()
    tracker.record_overpass_success()

    assert tracker.consecutive_overpass_failures == 0
    assert tracker.record_overpass_failure() is False


def test_regional_coordinate_empty_hint_is_shown_on_second_empty() -> None:
    tracker = SearchRequestFeedbackTracker()

    assert (
        tracker.record_regional_empty_result(
            is_empty=True,
            is_regional_endpoint=True,
        )
        is False
    )
    assert (
        tracker.record_regional_empty_result(
            is_empty=True,
            is_regional_endpoint=True,
        )
        is True
    )


def test_coordinate_empty_counter_resets_for_non_regional_or_non_empty() -> (
    None
):
    tracker = SearchRequestFeedbackTracker()

    tracker.record_regional_empty_result(
        is_empty=True,
        is_regional_endpoint=True,
    )
    assert (
        tracker.record_regional_empty_result(
            is_empty=True,
            is_regional_endpoint=False,
        )
        is False
    )
    assert tracker.consecutive_regional_empty_results == 0

    tracker.record_regional_empty_result(
        is_empty=True,
        is_regional_endpoint=True,
    )
    assert (
        tracker.record_regional_empty_result(
            is_empty=False,
            is_regional_endpoint=True,
        )
        is False
    )
    assert tracker.consecutive_regional_empty_results == 0


def test_overpass_failure_resets_coordinate_empty_counter() -> None:
    tracker = SearchRequestFeedbackTracker()

    tracker.record_regional_empty_result(
        is_empty=True,
        is_regional_endpoint=True,
    )
    tracker.record_overpass_failure()

    assert tracker.consecutive_regional_empty_results == 0
