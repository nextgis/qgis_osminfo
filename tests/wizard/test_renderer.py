import pytest


@pytest.mark.parametrize(
    ("condition", "expected_snippet"),
    [
        (
            ("substr", "name", "Main", None),
            'nwr["name"~"Main"];',
        ),
        (
            ("key", "", None, None),
            'nwr[~"^$"~".*"];',
        ),
        (
            ("eq", "", "", None),
            'nwr[~"^$"~"^$"];',
        ),
        (
            ("meta", None, "1 day", "newer"),
            'nwr(newer:"{{date:1 day}}");',
        ),
    ],
)
def test_renderer_matches_js_special_cases(
    renderer,
    wizard_modules,
    condition,
    expected_snippet,
) -> None:
    models = wizard_modules.models
    query_name, key, value, meta = condition
    rendered_query = renderer.render(
        models.ResolvedWizardSearch(
            bounds=models.WizardBounds.GLOBAL,
            conjunctions=[
                models.ResolvedConjunction(
                    types=[
                        models.OsmElementType.NODE,
                        models.OsmElementType.WAY,
                        models.OsmElementType.RELATION,
                    ],
                    conditions=[
                        models.ConditionNode(
                            query=models.ConditionQueryType(query_name),
                            key=key,
                            val=value,
                            meta=(
                                models.MetaQueryType(meta)
                                if meta is not None
                                else None
                            ),
                        )
                    ],
                )
            ],
        ),
        original_search="test",
    )

    assert expected_snippet in rendered_query.query


def test_renderer_uses_nwr_for_all_types(renderer, wizard_modules) -> None:
    models = wizard_modules.models
    rendered_query = renderer.render(
        models.ResolvedWizardSearch(
            bounds=models.WizardBounds.BBOX,
            conjunctions=[
                models.ResolvedConjunction(
                    types=[
                        models.OsmElementType.NODE,
                        models.OsmElementType.WAY,
                        models.OsmElementType.RELATION,
                    ],
                    conditions=[
                        models.ConditionNode(
                            query=models.ConditionQueryType.EQ,
                            key="amenity",
                            val="restaurant",
                        )
                    ],
                )
            ],
        ),
        original_search="amenity=restaurant in bbox",
    )

    assert 'nwr["amenity"="restaurant"]({{bbox}});' in rendered_query.query
