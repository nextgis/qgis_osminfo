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

import pytest


def test_semantic_resolver_expands_free_form_and_applies_type_filter(
    semantic_resolver,
    wizard_modules,
) -> None:
    models = wizard_modules.models
    normalized_search = models.NormalizedWizardSearch(
        bounds=models.WizardBounds.BBOX,
        query=models.NormalizedQuery(
            queries=[
                models.NormalizedConjunction(
                    queries=[
                        models.ConditionNode(
                            query=models.ConditionQueryType.FREE_FORM,
                            free="restaurant",
                        ),
                        models.ConditionNode(
                            query=models.ConditionQueryType.TYPE,
                            type=models.OsmElementType.WAY,
                        ),
                        models.ConditionNode(
                            query=models.ConditionQueryType.EQ,
                            key="name",
                            val="Cafe",
                        ),
                    ]
                )
            ]
        ),
    )

    resolved_search = semantic_resolver.resolve(normalized_search)

    assert resolved_search == models.ResolvedWizardSearch(
        bounds=models.WizardBounds.BBOX,
        conjunctions=[
            models.ResolvedConjunction(
                types=[models.OsmElementType.WAY],
                conditions=[
                    models.ConditionNode(
                        query=models.ConditionQueryType.EQ,
                        key="amenity",
                        val="restaurant",
                    ),
                    models.ConditionNode(
                        query=models.ConditionQueryType.EQ,
                        key="name",
                        val="Cafe",
                    ),
                ],
            )
        ],
        area=None,
        used_free_form=True,
    )


def test_semantic_resolver_returns_empty_types_for_incompatible_filter(
    semantic_resolver,
    wizard_modules,
) -> None:
    models = wizard_modules.models
    normalized_search = models.NormalizedWizardSearch(
        bounds=models.WizardBounds.GLOBAL,
        query=models.NormalizedQuery(
            queries=[
                models.NormalizedConjunction(
                    queries=[
                        models.ConditionNode(
                            query=models.ConditionQueryType.FREE_FORM,
                            free="booth",
                        ),
                        models.ConditionNode(
                            query=models.ConditionQueryType.TYPE,
                            type=models.OsmElementType.WAY,
                        ),
                    ]
                )
            ]
        ),
    )

    resolved_search = semantic_resolver.resolve(normalized_search)

    assert resolved_search.conjunctions[0].types == []
    assert resolved_search.used_free_form is True


def test_semantic_resolver_marks_closed_way_queries_as_closed_ways(
    semantic_resolver,
    wizard_modules,
) -> None:
    models = wizard_modules.models
    normalized_search = models.NormalizedWizardSearch(
        bounds=models.WizardBounds.BBOX,
        query=models.NormalizedQuery(
            queries=[
                models.NormalizedConjunction(
                    queries=[
                        models.ConditionNode(
                            query=models.ConditionQueryType.FREE_FORM,
                            free="restaurant",
                        ),
                        models.ConditionNode(
                            query=models.ConditionQueryType.TYPE,
                            type=models.OsmElementType.CLOSED_WAY,
                        ),
                    ]
                )
            ]
        ),
    )

    resolved_search = semantic_resolver.resolve(normalized_search)

    assert resolved_search.conjunctions[0] == models.ResolvedConjunction(
        types=[models.OsmElementType.WAY],
        conditions=[
            models.ConditionNode(
                query=models.ConditionQueryType.EQ,
                key="amenity",
                val="restaurant",
            )
        ],
        closed_way_only=True,
    )


def test_semantic_resolver_rejects_closed_way_for_point_only_preset(
    semantic_resolver,
    wizard_modules,
) -> None:
    models = wizard_modules.models
    normalized_search = models.NormalizedWizardSearch(
        bounds=models.WizardBounds.BBOX,
        query=models.NormalizedQuery(
            queries=[
                models.NormalizedConjunction(
                    queries=[
                        models.ConditionNode(
                            query=models.ConditionQueryType.FREE_FORM,
                            free="booth",
                        ),
                        models.ConditionNode(
                            query=models.ConditionQueryType.TYPE,
                            type=models.OsmElementType.CLOSED_WAY,
                        ),
                    ]
                )
            ]
        ),
    )

    resolved_search = semantic_resolver.resolve(normalized_search)

    assert resolved_search.conjunctions[0].types == []
    assert resolved_search.conjunctions[0].closed_way_only is True


def test_semantic_resolver_keeps_way_compatible_with_closed_way(
    semantic_resolver,
    wizard_modules,
) -> None:
    models = wizard_modules.models
    normalized_search = models.NormalizedWizardSearch(
        bounds=models.WizardBounds.BBOX,
        query=models.NormalizedQuery(
            queries=[
                models.NormalizedConjunction(
                    queries=[
                        models.ConditionNode(
                            query=models.ConditionQueryType.FREE_FORM,
                            free="restaurant",
                        ),
                        models.ConditionNode(
                            query=models.ConditionQueryType.TYPE,
                            type=models.OsmElementType.WAY,
                        ),
                        models.ConditionNode(
                            query=models.ConditionQueryType.TYPE,
                            type=models.OsmElementType.CLOSED_WAY,
                        ),
                    ]
                )
            ]
        ),
    )

    resolved_search = semantic_resolver.resolve(normalized_search)

    assert resolved_search.conjunctions[0] == models.ResolvedConjunction(
        types=[models.OsmElementType.WAY],
        conditions=[
            models.ConditionNode(
                query=models.ConditionQueryType.EQ,
                key="amenity",
                val="restaurant",
            )
        ],
        closed_way_only=True,
    )


def test_semantic_resolver_keeps_error_for_simple_free_form_with_suggestion(
    semantic_resolver,
    wizard_modules,
) -> None:
    models = wizard_modules.models
    normalized_search = models.NormalizedWizardSearch(
        bounds=models.WizardBounds.BBOX,
        query=models.NormalizedQuery(
            queries=[
                models.NormalizedConjunction(
                    queries=[
                        models.ConditionNode(
                            query=models.ConditionQueryType.FREE_FORM,
                            free="restarant",
                        )
                    ]
                )
            ]
        ),
    )

    with pytest.raises(
        wizard_modules.exceptions.OsmInfoWizardFreeFormError,
        match="Did you mean 'Restaurant'",
    ):
        semantic_resolver.resolve(normalized_search)
