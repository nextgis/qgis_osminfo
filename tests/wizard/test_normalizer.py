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
