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


def test_normalizer_distributes_and_over_or(
    normalizer, wizard_modules
) -> None:
    models = wizard_modules.models

    expression = models.LogicalNode(
        logical=models.LogicalOperator.AND,
        queries=[
            models.ConditionNode(
                query=models.ConditionQueryType.FREE_FORM,
                free="restaurant",
            ),
            models.LogicalNode(
                logical=models.LogicalOperator.OR,
                queries=[
                    models.ConditionNode(
                        query=models.ConditionQueryType.EQ,
                        key="amenity",
                        val="restaurant",
                    ),
                    models.ConditionNode(
                        query=models.ConditionQueryType.EQ,
                        key="amenity",
                        val="cafe",
                    ),
                ],
            ),
        ],
    )
    search = models.WizardSearch(
        bounds=models.WizardBounds.BBOX,
        query=expression,
    )

    normalized_search = normalizer.normalize(search)

    assert normalized_search.query.queries == [
        models.NormalizedConjunction(
            queries=[
                models.ConditionNode(
                    query=models.ConditionQueryType.FREE_FORM,
                    free="restaurant",
                ),
                models.ConditionNode(
                    query=models.ConditionQueryType.EQ,
                    key="amenity",
                    val="restaurant",
                ),
            ]
        ),
        models.NormalizedConjunction(
            queries=[
                models.ConditionNode(
                    query=models.ConditionQueryType.FREE_FORM,
                    free="restaurant",
                ),
                models.ConditionNode(
                    query=models.ConditionQueryType.EQ,
                    key="amenity",
                    val="cafe",
                ),
            ]
        ),
    ]
