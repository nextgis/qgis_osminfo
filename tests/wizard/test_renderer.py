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


def test_renderer_renders_closed_way_filter(
    renderer,
    wizard_modules,
) -> None:
    models = wizard_modules.models
    rendered_query = renderer.render(
        models.ResolvedWizardSearch(
            bounds=models.WizardBounds.GLOBAL,
            conjunctions=[
                models.ResolvedConjunction(
                    types=[models.OsmElementType.WAY],
                    conditions=[
                        models.ConditionNode(
                            query=models.ConditionQueryType.EQ,
                            key="leisure",
                            val="fitness_station",
                        )
                    ],
                    closed_way_only=True,
                )
            ],
        ),
        original_search="type:closed_way and leisure=fitness_station",
    )

    assert (
        'way["leisure"="fitness_station"](if:is_closed());'
        in rendered_query.query
    )
