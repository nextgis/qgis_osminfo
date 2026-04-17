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
from typing import List, Optional

from osminfo.settings.osm_info_settings import OsmInfoSettings

_HEADER_OPTIONS_PATTERN = re.compile(r"\[[^\]]+\]")
_OUT_OPTION_PATTERN = re.compile(r"^\[out:[^\]]+\]$", re.IGNORECASE)
_TIMEOUT_OPTION_PATTERN = re.compile(
    r"^\[timeout:[^\]]+\]$",
    re.IGNORECASE,
)
_MAXSIZE_OPTION_PATTERN = re.compile(
    r"^\[maxsize:[^\]]+\]$",
    re.IGNORECASE,
)
_HEADER_PATTERN = re.compile(
    r"^(?P<prefix>\s*(?:/\*[\s\S]*?\*/\s*)?)"
    r"(?P<header>(?:\[[^\]]+\])+;)?"
    r"(?P<body>[\s\S]*)$"
)


class QueryHeaderBuilder:
    """Build and normalize Overpass query headers.

    Merge caller-specified header options with plugin settings while replacing
    timeout and maxsize directives deterministically.
    """

    def __init__(
        self,
        settings: Optional[OsmInfoSettings] = None,
    ) -> None:
        self._settings = settings

    def build(
        self,
        out_option: str = "[out:json]",
        preserved_options: Optional[List[str]] = None,
    ) -> str:
        header_parts = [out_option]

        if preserved_options is not None:
            header_parts.extend(preserved_options)

        if self._settings is not None and self._settings.is_timeout_enabled:
            header_parts.append(f"[timeout:{self._settings.timeout}]")

        max_size_bytes = self._query_max_size()
        if max_size_bytes is not None:
            header_parts.append(f"[maxsize:{max_size_bytes}Mi]")

        return "".join(header_parts) + ";"

    def apply(
        self,
        query: str,
        default_out_option: str = "[out:json]",
    ) -> str:
        match = _HEADER_PATTERN.match(query)
        if match is None:
            header = self.build(default_out_option)
            if len(query) == 0:
                return header
            return f"{header}\n{query}"

        prefix = match.group("prefix")
        header = match.group("header")
        body = match.group("body")

        out_option = default_out_option
        preserved_options: List[str] = []

        if header is not None:
            for option in _HEADER_OPTIONS_PATTERN.findall(header):
                if _OUT_OPTION_PATTERN.fullmatch(option) is not None:
                    out_option = option
                    continue

                if _TIMEOUT_OPTION_PATTERN.fullmatch(option) is not None:
                    continue

                if _MAXSIZE_OPTION_PATTERN.fullmatch(option) is not None:
                    continue

                preserved_options.append(option)

        normalized_header = self.build(out_option, preserved_options)

        if header is not None:
            return f"{prefix}{normalized_header}{body}"

        separator = ""
        if len(body) > 0 and not body.startswith("\n"):
            separator = "\n"

        return f"{prefix}{normalized_header}{separator}{body}"

    def _query_max_size(self) -> Optional[int]:
        if self._settings is None:
            return None

        if not self._settings.is_max_size_enabled:
            return None

        max_size_megabytes = self._settings.max_size_megabytes
        if max_size_megabytes <= 0:
            return None

        return max_size_megabytes
