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

from typing import List, Optional, Tuple

from qgis.core import QgsApplication

from osminfo.core.exceptions import (
    OsmInfoWizardFreeFormError,
    OsmInfoWizardRenderError,
)

from .free_form import PresetFreeFormResolver
from .models import (
    ConditionQueryType,
    FreeFormResolution,
    NormalizedConjunction,
    NormalizedWizardSearch,
    OsmElementType,
    ResolvedConjunction,
    ResolvedWizardSearch,
)


class WizardSemanticResolver:
    """Resolve normalized wizard conditions into renderable search clauses.

    Expand free-form presets into concrete tag predicates and narrow the set of
    allowed OSM element types for each conjunction.
    """

    def __init__(
        self,
        free_form_resolver: Optional[PresetFreeFormResolver] = None,
    ) -> None:
        self._free_form_resolver = (
            free_form_resolver or PresetFreeFormResolver()
        )

    @property
    def free_form_resolver(self) -> PresetFreeFormResolver:
        """Expose the free-form resolver for use in repair suggestions."""
        return self._free_form_resolver

    def resolve(
        self,
        wizard_search: NormalizedWizardSearch,
    ) -> ResolvedWizardSearch:
        """Resolve normalized wizard search conditions into concrete element types and tag predicates.

        :param wizard_search: The normalized wizard search to resolve.
        :return: A ResolvedWizardSearch containing the resolved conditions and element types.
        :raises OsmInfoWizardFreeFormError: If a free-form condition cannot be resolved.
        :raises OsmInfoWizardRenderError: If a type condition is invalid.
        """

        conjunctions: List[ResolvedConjunction] = []
        used_free_form = False

        for conjunction in wizard_search.query.queries:
            resolved_conjunction, conjunction_used_free_form = (
                self._resolve_conjunction(conjunction)
            )
            conjunctions.append(resolved_conjunction)
            used_free_form = used_free_form or conjunction_used_free_form

        return ResolvedWizardSearch(
            bounds=wizard_search.bounds,
            area=wizard_search.area,
            conjunctions=conjunctions,
            used_free_form=used_free_form,
        )

    def _resolve_conjunction(
        self,
        conjunction: NormalizedConjunction,
    ) -> Tuple[ResolvedConjunction, bool]:
        element_types = [
            OsmElementType.NODE,
            OsmElementType.WAY,
            OsmElementType.RELATION,
        ]
        conditions = []
        used_free_form = False

        for condition in conjunction.queries:
            if condition.query == ConditionQueryType.FREE_FORM:
                if condition.free is None:
                    raise OsmInfoWizardFreeFormError(
                        log_message="Free-form query is empty",
                        user_message=self.tr("Free-form query is empty."),
                    )

                # Free-form presets constrain both filters and element types.
                resolution = self._free_form_resolver.resolve(condition.free)
                element_types = self._restrict_types(
                    element_types,
                    resolution,
                )
                conditions.extend(resolution.conditions)
                used_free_form = True
                continue

            if condition.query == ConditionQueryType.TYPE:
                if condition.type is None:
                    raise OsmInfoWizardRenderError(
                        log_message="Type condition is empty",
                        user_message=self.tr("Type condition is empty."),
                    )

                if condition.type in element_types:
                    element_types = [condition.type]
                else:
                    element_types = []
                continue

            conditions.append(condition)

        return (
            ResolvedConjunction(
                types=element_types,
                conditions=conditions,
            ),
            used_free_form,
        )

    def _restrict_types(
        self,
        element_types: List[OsmElementType],
        resolution: FreeFormResolution,
    ) -> List[OsmElementType]:
        return [
            element_type
            for element_type in element_types
            if element_type in resolution.types
        ]

    @classmethod
    def tr(cls, message: str) -> str:
        return QgsApplication.translate(cls.__name__, message)
