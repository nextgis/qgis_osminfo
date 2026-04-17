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

from typing import Optional

from osminfo.core.exceptions import OsmInfoWizardParserError

from .free_form_syntax import contains_reserved_free_form_syntax
from .models import RenderedWizardQuery
from .normalizer import WizardAstNormalizer
from .parser import WizardSyntaxParser
from .renderer import OverpassWizardRenderer
from .repair import WizardSearchRepairer
from .semantic import WizardSemanticResolver


class WizardQueryCompiler:
    """Compile wizard search text into an executable Overpass query.

    Coordinate parsing, normalization, semantic resolution, rendering, and
    repair suggestions for wizard searches.
    """

    def __init__(
        self,
        parser: Optional[WizardSyntaxParser] = None,
        normalizer: Optional[WizardAstNormalizer] = None,
        semantic_resolver: Optional[WizardSemanticResolver] = None,
        renderer: Optional[OverpassWizardRenderer] = None,
        repairer: Optional[WizardSearchRepairer] = None,
    ) -> None:
        self._parser = parser or WizardSyntaxParser()
        self._normalizer = normalizer or WizardAstNormalizer()
        self._semantic_resolver = semantic_resolver or WizardSemanticResolver()
        self._renderer = renderer or OverpassWizardRenderer()
        self._repairer = repairer or WizardSearchRepairer(
            self._semantic_resolver.free_form_resolver
        )

    def compile(self, search_string: str) -> RenderedWizardQuery:
        parsed_search = self._parse_with_fallback(search_string)
        normalized_search = self._normalizer.normalize(parsed_search)
        resolved_search = self._semantic_resolver.resolve(normalized_search)
        return self._renderer.render(resolved_search, search_string)

    def repair_search(self, search_string: str) -> Optional[str]:
        try:
            parsed_search = self._parse_with_fallback(search_string)
        except OsmInfoWizardParserError:
            return None

        normalized_search = self._normalizer.normalize(parsed_search)
        return self._repairer.repair(search_string, normalized_search)

    def _parse_with_fallback(self, search_string: str):
        try:
            return self._parser.parse(search_string)
        except OsmInfoWizardParserError as error:
            first_error = error

        # Treat plain multi-word input as a quoted preset name before failing.
        quoted_search = self._quoted_free_form_fallback(search_string)
        if quoted_search is None:
            raise first_error

        try:
            return self._parser.parse(quoted_search)
        except OsmInfoWizardParserError as error:
            raise first_error from error

    def _quoted_free_form_fallback(
        self,
        search_string: str,
    ) -> Optional[str]:
        """Apply a fallback strategy to interpret free-form input as a quoted preset name."""
        normalized_search = search_string.strip()
        if len(normalized_search) == 0:
            return None

        if normalized_search[0] in ('"', "'"):
            return None

        if contains_reserved_free_form_syntax(normalized_search):
            return None

        if " " not in normalized_search:
            return None

        escaped_value = normalized_search.replace('"', '\\"')
        return f'"{escaped_value}"'
