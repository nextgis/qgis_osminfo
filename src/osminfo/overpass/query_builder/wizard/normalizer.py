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

from typing import List

from qgis.core import QgsApplication

from osminfo.core.exceptions import OsmInfoWizardNormalizationError

from .models import (
    ConditionNode,
    LogicalNode,
    LogicalOperator,
    NormalizedConjunction,
    NormalizedQuery,
    NormalizedWizardSearch,
    WizardExpression,
    WizardSearch,
)


class WizardAstNormalizer:
    """Normalize the parsed wizard AST into disjunctive normal form.

    Flatten nested boolean expressions into conjunction branches that can be
    resolved and rendered deterministically.
    """

    def normalize(self, wizard_search: WizardSearch) -> NormalizedWizardSearch:
        return NormalizedWizardSearch(
            bounds=wizard_search.bounds,
            area=wizard_search.area,
            query=NormalizedQuery(
                logical=LogicalOperator.OR,
                queries=self._normalize_recursive(wizard_search.query),
            ),
        )

    def _normalize_recursive(
        self,
        expression: WizardExpression,
    ) -> List[NormalizedConjunction]:
        if isinstance(expression, ConditionNode):
            return [NormalizedConjunction(queries=[expression])]

        if not isinstance(expression, LogicalNode):
            raise OsmInfoWizardNormalizationError(
                log_message="Unknown wizard expression",
                user_message=self.tr("Unknown wizard expression."),
            )

        if expression.logical == LogicalOperator.AND:
            left = self._normalize_recursive(expression.queries[0])
            right = self._normalize_recursive(expression.queries[1])
            conjunctions: List[NormalizedConjunction] = []
            for left_item in left:
                for right_item in right:
                    conjunctions.append(
                        NormalizedConjunction(
                            queries=left_item.queries + right_item.queries,
                        )
                    )
            return conjunctions

        if expression.logical == LogicalOperator.OR:
            left = self._normalize_recursive(expression.queries[0])
            right = self._normalize_recursive(expression.queries[1])
            return left + right

        raise OsmInfoWizardNormalizationError(
            log_message=(
                f"Unsupported boolean operator: {expression.logical.value}"
            ),
            user_message=self.tr(
                "Unsupported boolean operator: {operator}."
            ).format(operator=expression.logical.value),
        )

    @classmethod
    def tr(cls, message: str) -> str:
        return QgsApplication.translate(cls.__name__, message)
