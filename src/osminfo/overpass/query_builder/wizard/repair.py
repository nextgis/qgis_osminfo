import re
from typing import Optional

from osminfo.core.exceptions import OsmInfoWizardFreeFormError

from .free_form import PresetFreeFormResolver
from .models import ConditionQueryType, NormalizedWizardSearch


class WizardSearchRepairer:
    """Suggest corrected wizard searches for unresolved free-form presets.

    Inspect parsed free-form terms and replace unmatched fragments with fuzzy
    preset suggestions while preserving the original search structure.
    """

    def __init__(
        self,
        free_form_resolver: Optional[PresetFreeFormResolver] = None,
    ) -> None:
        self._free_form_resolver = (
            free_form_resolver or PresetFreeFormResolver()
        )

    def repair(
        self,
        search_string: str,
        normalized_search: NormalizedWizardSearch,
    ) -> Optional[str]:
        repaired = False
        remaining_search = search_string
        search_parts = []

        for conjunction in normalized_search.query.queries:
            for condition in conjunction.queries:
                if condition.query != ConditionQueryType.FREE_FORM:
                    continue

                if condition.free is None:
                    continue

                try:
                    self._free_form_resolver.resolve(condition.free)
                    continue
                except OsmInfoWizardFreeFormError:
                    suggestion = self._free_form_resolver.fuzzy_search(
                        condition.free
                    )

                if suggestion is None:
                    continue

                escaped_free_form = re.escape(condition.free)
                free_regex = re.compile(rf"['\"]?{escaped_free_form}['\"]?")
                match = free_regex.search(remaining_search)
                if match is None:
                    continue

                search_parts.append(remaining_search[: match.start()])
                search_parts.append(self._quote_search_term(suggestion))
                remaining_search = remaining_search[match.end() :]
                repaired = True

        if not repaired:
            return None

        search_parts.append(remaining_search)
        return "".join(search_parts)

    def _quote_search_term(self, value: str) -> str:
        if re.fullmatch(r"[a-zA-Z0-9_]+", value) is not None:
            return value

        escaped_value = value.replace('"', '\\"')
        return f'"{escaped_value}"'
