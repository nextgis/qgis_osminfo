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
