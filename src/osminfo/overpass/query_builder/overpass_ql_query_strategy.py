import re
from typing import List, Optional

from osminfo.settings.osm_info_settings import OsmInfoSettings

from .query_header import QueryHeaderBuilder
from .string_query_strategy import StringQueryStrategy

OVERPASS_QL_PATTERN = re.compile(
    r"\[out:[^\]]+\]"
    r"|(?:^|[\s;(])(?:node|way|relation|nwr|nw|wr|is_in|area)\s*\("
    r"|\bout\b\s*(?:[a-z\s]+)?;",
    re.IGNORECASE,
)


class OverpassQlQueryStrategy(StringQueryStrategy):
    """Detect and pass through raw Overpass QL input.

    Recognize search strings that already look like Overpass QL and ensure they
    receive a normalized query header.
    """

    NAME = "ql"

    def __init__(
        self,
        settings: Optional[OsmInfoSettings] = None,
    ) -> None:
        self._query_header_builder = QueryHeaderBuilder(settings)

    def build(self, search_string: str) -> List[str]:
        normalized_search_string = search_string.strip()
        if len(normalized_search_string) == 0:
            return []

        if OVERPASS_QL_PATTERN.search(normalized_search_string) is None:
            return []

        return [self._query_header_builder.apply(normalized_search_string)]
