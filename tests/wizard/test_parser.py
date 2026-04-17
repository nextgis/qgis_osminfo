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


def test_parse_simple_equality_with_bbox_bounds(
    parser, wizard_modules
) -> None:
    models = wizard_modules.models

    wizard_search = parser.parse("amenity=school in bbox")

    assert wizard_search == models.WizardSearch(
        bounds=models.WizardBounds.BBOX,
        query=models.ConditionNode(
            query=models.ConditionQueryType.EQ,
            key="amenity",
            val="school",
        ),
        area=None,
    )


def test_parse_regex_and_global_bounds(parser, wizard_modules) -> None:
    models = wizard_modules.models

    wizard_search = parser.parse("name~/Main/i global")

    assert wizard_search == models.WizardSearch(
        bounds=models.WizardBounds.GLOBAL,
        query=models.ConditionNode(
            query=models.ConditionQueryType.LIKE,
            key="name",
            val=models.RegexValue(regex="Main", modifier="i"),
        ),
        area=None,
    )


@pytest.mark.parametrize(
    ("search_string", "expected_query_type"),
    [
        ("name is null global", "nokey"),
        ("name is not null global", "key"),
    ],
)
def test_parse_null_statements(
    parser, wizard_modules, search_string, expected_query_type
) -> None:
    wizard_search = parser.parse(search_string)
    assert wizard_search.query.query.value == expected_query_type


def test_parse_invalid_type_raises_parser_error(
    parser, wizard_modules
) -> None:
    with pytest.raises(wizard_modules.exceptions.OsmInfoWizardParserError):
        parser.parse("type:restaurant global")


@pytest.mark.parametrize(
    ("search_string", "expected_query"),
    [
        (
            "tourism==museum",
            ("eq", "tourism", "museum"),
        ),
        (
            'name<>"Main Street"',
            ("neq", "name", "Main Street"),
        ),
        (
            "cycleway:opp",
            ("substr", "cycleway", "opp"),
        ),
        (
            "name like /street$/i",
            ("like", "name", ("street$", "i")),
        ),
        (
            'ref~"[0-9]+"',
            ("like", "ref", "[0-9]+"),
        ),
        (
            '~building~".*"',
            ("likelike", "building", ".*"),
        ),
        (
            'name not like "foo"',
            ("notlike", "name", "foo"),
        ),
        (
            '"addr:housenumber"=*',
            ("key", "addr:housenumber", None),
        ),
        (
            '"addr:housenumber" is null',
            ("nokey", "addr:housenumber", None),
        ),
    ],
)
def test_parse_documented_selector_variants(
    parser,
    wizard_modules,
    search_string,
    expected_query,
) -> None:
    models = wizard_modules.models
    query_type, expected_key, expected_value = expected_query
    if isinstance(expected_value, tuple):
        expected_value = models.RegexValue(
            regex=expected_value[0],
            modifier=expected_value[1],
        )

    wizard_search = parser.parse(search_string)

    assert wizard_search == models.WizardSearch(
        bounds=models.WizardBounds.BBOX,
        query=models.ConditionNode(
            query=models.ConditionQueryType(query_type),
            key=expected_key,
            val=expected_value,
        ),
        area=None,
    )


@pytest.mark.parametrize(
    ("search_string", "expected_meta", "expected_value"),
    [
        ("id:263621287", "id", "263621287"),
        ("user:SomeonesUsername", "user", "SomeonesUsername"),
        ("uid:12345", "uid", "12345"),
        ('newer:"4 weeks"', "newer", "4 weeks"),
        (
            'newer:"2013-11-24T19:01:00Z"',
            "newer",
            "2013-11-24T19:01:00Z",
        ),
    ],
)
def test_parse_meta_selectors(
    parser,
    wizard_modules,
    search_string,
    expected_meta,
    expected_value,
) -> None:
    models = wizard_modules.models

    wizard_search = parser.parse(search_string)

    assert wizard_search == models.WizardSearch(
        bounds=models.WizardBounds.BBOX,
        query=models.ConditionNode(
            query=models.ConditionQueryType.META,
            meta=models.MetaQueryType(expected_meta),
            val=expected_value,
        ),
        area=None,
    )


def test_parse_example_with_area_and_free_form(parser, wizard_modules) -> None:
    models = wizard_modules.models

    wizard_search = parser.parse('"Drinking Water" in London')

    assert wizard_search == models.WizardSearch(
        bounds=models.WizardBounds.AREA,
        query=models.ConditionNode(
            query=models.ConditionQueryType.FREE_FORM,
            free="Drinking Water",
        ),
        area="London",
    )


def test_parse_example_with_nested_or_and_type(parser, wizard_modules) -> None:
    models = wizard_modules.models

    wizard_search = parser.parse(
        "(highway=primary or highway=secondary) and type:way"
    )

    assert wizard_search == models.WizardSearch(
        bounds=models.WizardBounds.BBOX,
        query=models.LogicalNode(
            logical=models.LogicalOperator.AND,
            queries=[
                models.LogicalNode(
                    logical=models.LogicalOperator.OR,
                    queries=[
                        models.ConditionNode(
                            query=models.ConditionQueryType.EQ,
                            key="highway",
                            val="primary",
                        ),
                        models.ConditionNode(
                            query=models.ConditionQueryType.EQ,
                            key="highway",
                            val="secondary",
                        ),
                    ],
                ),
                models.ConditionNode(
                    query=models.ConditionQueryType.TYPE,
                    type=models.OsmElementType.WAY,
                ),
            ],
        ),
        area=None,
    )


def test_parse_mixed_case_type_as_substring(parser, wizard_modules) -> None:
    models = wizard_modules.models

    wizard_search = parser.parse("Type:Node")

    assert wizard_search == models.WizardSearch(
        bounds=models.WizardBounds.BBOX,
        query=models.ConditionNode(
            query=models.ConditionQueryType.SUBSTR,
            key="Type",
            val="Node",
        ),
        area=None,
    )


def test_parse_mixed_case_meta_as_substring(parser, wizard_modules) -> None:
    models = wizard_modules.models

    wizard_search = parser.parse("USER:SomeonesUsername")

    assert wizard_search == models.WizardSearch(
        bounds=models.WizardBounds.BBOX,
        query=models.ConditionNode(
            query=models.ConditionQueryType.SUBSTR,
            key="USER",
            val="SomeonesUsername",
        ),
        area=None,
    )


def test_parse_unicode_key_in_null_selector(parser, wizard_modules) -> None:
    models = wizard_modules.models

    wizard_search = parser.parse("имя is null")

    assert wizard_search == models.WizardSearch(
        bounds=models.WizardBounds.BBOX,
        query=models.ConditionNode(
            query=models.ConditionQueryType.NO_KEY,
            key="имя",
        ),
        area=None,
    )


def test_parse_operator_precedence_matches_upstream(
    parser,
    wizard_modules,
) -> None:
    models = wizard_modules.models

    wizard_search = parser.parse("foo=bar or asd=fasd and baz=qux")

    assert wizard_search == models.WizardSearch(
        bounds=models.WizardBounds.BBOX,
        query=models.LogicalNode(
            logical=models.LogicalOperator.OR,
            queries=[
                models.ConditionNode(
                    query=models.ConditionQueryType.EQ,
                    key="foo",
                    val="bar",
                ),
                models.LogicalNode(
                    logical=models.LogicalOperator.AND,
                    queries=[
                        models.ConditionNode(
                            query=models.ConditionQueryType.EQ,
                            key="asd",
                            val="fasd",
                        ),
                        models.ConditionNode(
                            query=models.ConditionQueryType.EQ,
                            key="baz",
                            val="qux",
                        ),
                    ],
                ),
            ],
        ),
        area=None,
    )


def test_parse_symbolic_boolean_operator_without_spaces(
    parser,
    wizard_modules,
) -> None:
    models = wizard_modules.models

    wizard_search = parser.parse("foo=bar&&baz=qux")

    assert wizard_search == models.WizardSearch(
        bounds=models.WizardBounds.BBOX,
        query=models.LogicalNode(
            logical=models.LogicalOperator.AND,
            queries=[
                models.ConditionNode(
                    query=models.ConditionQueryType.EQ,
                    key="foo",
                    val="bar",
                ),
                models.ConditionNode(
                    query=models.ConditionQueryType.EQ,
                    key="baz",
                    val="qux",
                ),
            ],
        ),
        area=None,
    )


@pytest.mark.parametrize(
    "search_string",
    [
        '"type":foo',
        'name="a\\x"',
    ],
)
def test_parse_upstream_invalid_inputs_raise(
    parser,
    wizard_modules,
    search_string,
) -> None:
    with pytest.raises(wizard_modules.exceptions.OsmInfoWizardParserError):
        parser.parse(search_string)


def test_parse_raises_dependency_error_when_pyparsing_missing(
    wizard_modules,
    monkeypatch,
) -> None:
    parser_module = wizard_modules.parser
    parser = parser_module.WizardSyntaxParser()
    original_find_spec = parser_module.find_spec

    def fake_find_spec(name: str):
        if name == "pyparsing":
            return None

        return original_find_spec(name)

    monkeypatch.setattr(parser_module, "find_spec", fake_find_spec)

    with pytest.raises(wizard_modules.exceptions.OsmInfoWizardDependencyError):
        parser.parse("amenity=school")
