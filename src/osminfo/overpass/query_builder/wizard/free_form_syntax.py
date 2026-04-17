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

import re
from typing import Tuple

FREE_FORM_LOGICAL_KEYWORDS: Tuple[str, ...] = (
    "and",
    "or",
)
FREE_FORM_BOUNDS_KEYWORDS: Tuple[str, ...] = (
    "in",
    "around",
    "global",
)
FREE_FORM_RESERVED_KEYWORDS: Tuple[str, ...] = (
    *FREE_FORM_LOGICAL_KEYWORDS,
    *FREE_FORM_BOUNDS_KEYWORDS,
    "like",
    "not",
    "is",
    "type",
    "user",
    "uid",
    "newer",
    "id",
)
FREE_FORM_KEYWORDS_PATTERN = re.compile(
    r"\b(" + "|".join(FREE_FORM_RESERVED_KEYWORDS) + r")\b",
    re.IGNORECASE,
)
FREE_FORM_NON_FREE_FORM_MARKERS = re.compile(r"[()=:~&|*/<>!]")


def contains_reserved_free_form_syntax(value: str) -> bool:
    normalized_value = value.strip()
    if len(normalized_value) == 0:
        return False

    if FREE_FORM_NON_FREE_FORM_MARKERS.search(normalized_value) is not None:
        return True

    return FREE_FORM_KEYWORDS_PATTERN.search(normalized_value) is not None
