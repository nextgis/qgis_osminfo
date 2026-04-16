from typing import List, Optional, Tuple

from qgis.core import QgsApplication

from osminfo.core.exceptions import OsmInfoWizardFreeFormError
from osminfo.openstreetmap.preset_repository import (
    PresetDefinition,
    PresetRepository,
)

from .models import (
    ConditionNode,
    ConditionQueryType,
    FreeFormResolution,
    OsmElementType,
)


class PresetFreeFormResolver:
    """Resolve free-form wizard terms into OSM types and tag conditions.

    Match normalized user input against preset definitions and provide fuzzy
    suggestions when no exact preset match is available.
    """

    def __init__(
        self,
        repository: Optional[PresetRepository] = None,
    ) -> None:
        self._repository = repository or PresetRepository()

    def resolve(self, search_term: str) -> FreeFormResolution:
        normalized_search = search_term.strip().lower()
        preset = self._find_preset(normalized_search)
        if preset is None:
            suggestion = self.fuzzy_search(search_term)
            if suggestion is None:
                message = self.tr(
                    "Unknown wizard preset: {search_term}."
                ).format(search_term=search_term)
            else:
                message = self.tr(
                    "Unknown wizard preset: {search_term}. "
                    "Did you mean '{suggestion}'?"
                ).format(
                    search_term=search_term,
                    suggestion=suggestion,
                )

            raise OsmInfoWizardFreeFormError(
                log_message=message,
                user_message=message,
            )

        element_types = self._geometry_to_types(preset.geometry)
        conditions = [
            ConditionNode(
                query=(
                    ConditionQueryType.KEY
                    if value == "*"
                    else ConditionQueryType.EQ
                ),
                key=key,
                val=value if value != "*" else None,
            )
            for key, value in preset.tags.items()
        ]
        return FreeFormResolution(types=element_types, conditions=conditions)

    def fuzzy_search(self, search_term: str) -> Optional[str]:
        normalized_search = search_term.strip().lower()
        if len(normalized_search) == 0:
            return None

        fuzziness = 2 + len(normalized_search) // 7
        candidates: List[Tuple[int, bool, int, PresetDefinition]] = []
        for preset in self._repository.load().values():
            if preset.searchable is False:
                continue

            terms = self._preset_terms(preset)
            if len(terms) == 0:
                continue

            distances = [
                self._levenshtein_distance(term, normalized_search)
                for term in terms
            ]
            minimum_distance = min(distances)
            if minimum_distance <= fuzziness:
                best_term_index = distances.index(minimum_distance)
                has_name_match = best_term_index == 0
                candidates.append(
                    (
                        minimum_distance,
                        not has_name_match,
                        best_term_index,
                        preset,
                    )
                )

        if len(candidates) == 0:
            return None

        candidates.sort(key=lambda item: item[:3])
        preset = candidates[0][3]
        return preset.nameCased or preset.name

    def _find_preset(self, search_term: str) -> Optional[PresetDefinition]:
        candidates: List[Tuple[int, bool, PresetDefinition]] = []
        for preset in self._repository.load().values():
            if preset.searchable is False:
                continue

            if preset.name == search_term:
                candidates.append((-1, True, preset))
                continue

            if search_term in preset.terms:
                candidates.append(
                    (preset.terms.index(search_term), False, preset)
                )

        if len(candidates) == 0:
            return None

        candidates.sort(key=lambda item: (not item[1], item[0]))
        return candidates[0][2]

    def _geometry_to_types(
        self,
        geometry: List[str],
    ) -> List[OsmElementType]:
        element_types: List[OsmElementType] = []
        for item in geometry:
            if item in ("point", "vertex"):
                element_types.append(OsmElementType.NODE)
            elif item == "line":
                element_types.append(OsmElementType.WAY)
            elif item == "area":
                element_types.append(OsmElementType.WAY)
                element_types.append(OsmElementType.RELATION)
            elif item == "relation":
                element_types.append(OsmElementType.RELATION)

        unique_types: List[OsmElementType] = []
        for element_type in element_types:
            if element_type in unique_types:
                continue
            unique_types.append(element_type)

        return unique_types

    def _preset_terms(self, preset: PresetDefinition) -> List[str]:
        terms: List[str] = []
        if preset.name is not None:
            terms.append(preset.name)

        terms.extend(preset.terms)
        return terms

    def _levenshtein_distance(self, left: str, right: str) -> int:
        """Calculate the Levenshtein distance between two strings.

        The Levenshtein distance is a measure of the similarity between two
        strings, defined as the minimum number of single-character edits
        (insertions, deletions, or substitutions) required to change one
        string into the other.
        """
        if len(left) == 0:
            return len(right)

        if len(right) == 0:
            return len(left)

        matrix: List[List[int]] = []
        for row_index in range(len(right) + 1):
            matrix.append([row_index])

        for column_index in range(len(left) + 1):
            matrix[0].append(column_index)

        for row_index in range(1, len(right) + 1):
            for column_index in range(1, len(left) + 1):
                if right[row_index - 1] == left[column_index - 1]:
                    matrix[row_index].append(
                        matrix[row_index - 1][column_index - 1]
                    )
                    continue

                matrix[row_index].append(
                    min(
                        matrix[row_index - 1][column_index - 1] + 1,
                        matrix[row_index][column_index - 1] + 1,
                        matrix[row_index - 1][column_index] + 1,
                    )
                )

        return matrix[len(right)][len(left)]

    @classmethod
    def tr(cls, message: str) -> str:
        return QgsApplication.translate(cls.__name__, message)
