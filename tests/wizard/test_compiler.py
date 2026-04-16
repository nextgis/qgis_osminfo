import re

import pytest


def compact_query(query: str) -> str:
    query = re.sub(r"/\*[\s\S]*?\*/", "", query)
    query = re.sub(r"//.*", "", query)
    query = re.sub(r"\[out:json\];", "", query)
    query = query.replace("({{bbox}})", "(bbox)")
    query = re.sub(r"\{\{geocodeArea:([^}]*)\}\}", r"area(\1)", query)
    query = re.sub(
        r"\{\{geocodeCoords:([^}]*)\}\}",
        r"coords:\1",
        query,
    )
    query = re.sub(r"\{\{date:([^}]*)\}\}", r"date:\1", query)
    query = re.sub(r"\{\{[\s\S]*?\}\}", "", query)
    query = re.sub(r" *\n *", "", query)
    return query.strip()


@pytest.mark.parametrize(
    (
        "search_string",
        "expected_bounds",
        "expected_count",
        "expected_snippets",
    ),
    [
        (
            "restaurant in Berlin",
            "area",
            1,
            [
                "{{geocodeArea:Berlin}}->.searchArea;",
                'nwr["amenity"="restaurant"](area.searchArea);',
            ],
        ),
        (
            "restaurant and (amenity=restaurant or amenity=cafe) in bbox",
            "bbox",
            2,
            [
                'nwr["amenity"="restaurant"]["amenity"="restaurant"]({{bbox}});',
                'nwr["amenity"="restaurant"]["amenity"="cafe"]({{bbox}});',
            ],
        ),
    ],
)
def test_compile_matches_expected_js_semantics(
    compiler,
    search_string,
    expected_bounds,
    expected_count,
    expected_snippets,
) -> None:
    compiled_query = compiler.compile(search_string)

    assert compiled_query.bounds.value == expected_bounds
    assert compiled_query.query_count == expected_count
    for expected_snippet in expected_snippets:
        assert expected_snippet in compiled_query.query


@pytest.mark.parametrize(
    ("search_string", "expected_query"),
    [
        ("foo=*", 'nwr["foo"](bbox);out geom;'),
        ("foo!=*", 'nwr["foo"!~".*"](bbox);out geom;'),
        ("foo=bar", 'nwr["foo"="bar"](bbox);out geom;'),
        ("foo!=bar", 'nwr["foo"!="bar"](bbox);out geom;'),
        ("foo~bar", 'nwr["foo"~"bar"](bbox);out geom;'),
        ("~foo~bar", 'nwr[~"foo"~"bar"](bbox);out geom;'),
        ("foo!~bar", 'nwr["foo"!~"bar"](bbox);out geom;'),
        ("foo:bar", 'nwr["foo"~"bar"](bbox);out geom;'),
        (
            "foo=bar and asd=fasd",
            'nwr["foo"="bar"]["asd"="fasd"](bbox);out geom;',
        ),
        (
            "foo=bar or asd=fasd",
            '(nwr["foo"="bar"](bbox);nwr["asd"="fasd"](bbox););out geom;',
        ),
        (
            "foo=bar and (type:node or type:way)",
            '(node["foo"="bar"](bbox);way["foo"="bar"](bbox););out geom;',
        ),
        (
            "foo=bar and type:node and type:way",
            "();out geom;",
        ),
        ("foo=bar and type:node global", 'node["foo"="bar"];out geom;'),
        ("type:node", "node(bbox);out geom;"),
        (
            "type:node in foobar",
            "area(foobar)->.searchArea;node(area.searchArea);out geom;",
        ),
        ("type:node around foobar", "node(around:,coords:foobar);out geom;"),
        (
            'newer:"2000-01-01T01:01:01Z" and type:node',
            'node(newer:"2000-01-01T01:01:01Z")(bbox);out geom;',
        ),
        (
            "newer:1day and type:node",
            'node(newer:"date:1day")(bbox);out geom;',
        ),
        ('foo="" and type:way', 'way["foo"~"^$"](bbox);out geom;'),
        (
            "''=bar and type:way",
            'way[~"^$"~"^bar$"](bbox);out geom;',
        ),
    ],
)
def test_compile_matches_compacted_official_shapes(
    compiler,
    search_string,
    expected_query,
) -> None:
    compiled_query = compiler.compile(search_string)

    assert compact_query(compiled_query.query) == expected_query


def test_compile_marks_free_form_usage(compiler) -> None:
    compiled_query = compiler.compile("restaurant in Berlin")
    assert compiled_query.used_free_form is True


def test_compile_retries_as_quoted_free_form_for_plain_phrase(
    compiler,
) -> None:
    compiled_query = compiler.compile("Drinking Water")

    assert compiled_query.used_free_form is True
    assert compiled_query.query_count == 1
    assert '"amenity"="drinking_water"' in compiled_query.query


@pytest.mark.parametrize(
    ("search_string", "expected_snippet"),
    [
        ("foo=*", 'nwr["foo"]({{bbox}});'),
        ("foo==*", 'nwr["foo"]({{bbox}});'),
        ("foo is not null", 'nwr["foo"]({{bbox}});'),
        ("foo!=*", 'nwr["foo"!~".*"]({{bbox}});'),
        ("foo<>*", 'nwr["foo"!~".*"]({{bbox}});'),
        ("foo is null", 'nwr["foo"!~".*"]({{bbox}});'),
        ("foo=bar", 'nwr["foo"="bar"]({{bbox}});'),
        ("foo==bar", 'nwr["foo"="bar"]({{bbox}});'),
        ("foo!=bar", 'nwr["foo"!="bar"]({{bbox}});'),
        ("foo<>bar", 'nwr["foo"!="bar"]({{bbox}});'),
    ],
)
def test_compile_basic_operator_aliases(
    compiler,
    search_string,
    expected_snippet,
) -> None:
    compiled_query = compiler.compile(search_string)

    assert expected_snippet in compiled_query.query


@pytest.mark.parametrize(
    ("search_string", "expected_snippet"),
    [
        ("foo~bar", 'nwr["foo"~"bar"]({{bbox}});'),
        ("foo~/bar/", 'nwr["foo"~"bar"]({{bbox}});'),
        ("foo~=bar", 'nwr["foo"~"bar"]({{bbox}});'),
        ("foo~=/bar/", 'nwr["foo"~"bar"]({{bbox}});'),
        ("foo like bar", 'nwr["foo"~"bar"]({{bbox}});'),
        ("foo like /bar/", 'nwr["foo"~"bar"]({{bbox}});'),
        ("foo~/bar/i", 'nwr["foo"~"bar",i]({{bbox}});'),
        ("~foo~bar", 'nwr[~"foo"~"bar"]({{bbox}});'),
        ("~foo~/bar/", 'nwr[~"foo"~"bar"]({{bbox}});'),
        ("~foo~=bar", 'nwr[~"foo"~"bar"]({{bbox}});'),
        ("~foo~=/bar/", 'nwr[~"foo"~"bar"]({{bbox}});'),
        ("foo!~bar", 'nwr["foo"!~"bar"]({{bbox}});'),
        ("foo not like bar", 'nwr["foo"!~"bar"]({{bbox}});'),
        ("foo:'*'", 'nwr["foo"~"\\\\*"]({{bbox}});'),
    ],
)
def test_compile_regex_and_substring_variants(
    compiler,
    search_string,
    expected_snippet,
) -> None:
    compiled_query = compiler.compile(search_string)

    assert expected_snippet in compiled_query.query


@pytest.mark.parametrize(
    ("search_string", "expected_snippet"),
    [
        ('"a key"="a value"', 'nwr["a key"="a value"]({{bbox}});'),
        ("'foo bar'='asd fasd'", 'nwr["foo bar"="asd fasd"]({{bbox}});'),
        ("name='بیجنگ'", 'nwr["name"="بیجنگ"]({{bbox}});'),
        ("name=Béziers", 'nwr["name"="Béziers"]({{bbox}});'),
    ],
)
def test_compile_quoted_and_unicode_strings(
    compiler,
    search_string,
    expected_snippet,
) -> None:
    compiled_query = compiler.compile(search_string)

    assert expected_snippet in compiled_query.query


@pytest.mark.parametrize(
    ("search_string", "expected_count", "expected_snippets"),
    [
        (
            "foo=bar and asd=fasd",
            1,
            ['nwr["foo"="bar"]["asd"="fasd"]({{bbox}});'],
        ),
        (
            "foo=bar & asd=fasd",
            1,
            ['nwr["foo"="bar"]["asd"="fasd"]({{bbox}});'],
        ),
        (
            "foo=bar && asd=fasd",
            1,
            ['nwr["foo"="bar"]["asd"="fasd"]({{bbox}});'],
        ),
        (
            "foo=bar or asd=fasd",
            2,
            [
                'nwr["foo"="bar"]({{bbox}});',
                'nwr["asd"="fasd"]({{bbox}});',
            ],
        ),
        (
            "foo=bar | asd=fasd",
            2,
            [
                'nwr["foo"="bar"]({{bbox}});',
                'nwr["asd"="fasd"]({{bbox}});',
            ],
        ),
        (
            "foo=bar || asd=fasd",
            2,
            [
                'nwr["foo"="bar"]({{bbox}});',
                'nwr["asd"="fasd"]({{bbox}});',
            ],
        ),
        (
            "(foo=* or bar=*) and (asd=* or fasd=*)",
            4,
            [
                'nwr["foo"]["asd"]({{bbox}});',
                'nwr["foo"]["fasd"]({{bbox}});',
                'nwr["bar"]["asd"]({{bbox}});',
                'nwr["bar"]["fasd"]({{bbox}});',
            ],
        ),
    ],
)
def test_compile_boolean_operator_variants(
    compiler,
    search_string,
    expected_count,
    expected_snippets,
) -> None:
    compiled_query = compiler.compile(search_string)

    assert compiled_query.query_count == expected_count
    for expected_snippet in expected_snippets:
        assert expected_snippet in compiled_query.query


def test_compile_and_has_higher_precedence_than_or(compiler) -> None:
    compiled_query = compiler.compile("foo=bar or asd=fasd and baz=qux")

    assert compiled_query.query_count == 2
    assert 'nwr["foo"="bar"]({{bbox}});' in compiled_query.query
    assert 'nwr["asd"="fasd"]["baz"="qux"]({{bbox}});' in (
        compiled_query.query
    )


def test_compile_symbolic_boolean_operator_without_spaces(compiler) -> None:
    compiled_query = compiler.compile("foo=bar&&asd=fasd")

    assert compact_query(compiled_query.query) == (
        'nwr["foo"="bar"]["asd"="fasd"](bbox);out geom;'
    )


def test_compile_in_bbox_with_extra_inner_spacing(compiler) -> None:
    compiled_query = compiler.compile("type:node in   bbox")

    assert compact_query(compiled_query.query) == "node(bbox);out geom;"


def test_compile_mixed_case_type_remains_plain_substring(compiler) -> None:
    compiled_query = compiler.compile("Type:Node and type:way")

    assert compact_query(compiled_query.query) == (
        'way["Type"~"Node"](bbox);out geom;'
    )


@pytest.mark.parametrize(
    "search_string",
    [
        '"type":foo',
        'name="a\\x"',
    ],
)
def test_compile_rejects_invalid_upstream_inputs(
    compiler,
    wizard_modules,
    search_string,
) -> None:
    with pytest.raises(wizard_modules.exceptions.OsmInfoWizardParserError):
        compiler.compile(search_string)


@pytest.mark.parametrize(
    (
        "search_string",
        "expected_bounds",
        "expected_count",
        "expected_free_form",
        "expected_snippets",
    ),
    [
        (
            "amenity=drinking_water and type:node",
            "bbox",
            1,
            False,
            ['node["amenity"="drinking_water"]({{bbox}});'],
        ),
        (
            "(highway=primary or highway=secondary) and type:way",
            "bbox",
            2,
            False,
            [
                'way["highway"="primary"]({{bbox}});',
                'way["highway"="secondary"]({{bbox}});',
            ],
        ),
        (
            "tourism=hotel",
            "bbox",
            1,
            False,
            ['nwr["tourism"="hotel"]({{bbox}});'],
        ),
        (
            "tourism=museum in Vienna",
            "area",
            1,
            False,
            [
                "{{geocodeArea:Vienna}}->.searchArea;",
                'nwr["tourism"="museum"](area.searchArea);',
            ],
        ),
        (
            '"Drinking Water" in London',
            "area",
            1,
            True,
            [
                "{{geocodeArea:London}}->.searchArea;",
                'node["amenity"="drinking_water"](area.searchArea);',
            ],
        ),
    ],
)
def test_compile_documented_examples(
    compiler,
    search_string,
    expected_bounds,
    expected_count,
    expected_free_form,
    expected_snippets,
) -> None:
    compiled_query = compiler.compile(search_string)

    assert compiled_query.bounds.value == expected_bounds
    assert compiled_query.query_count == expected_count
    assert compiled_query.used_free_form is expected_free_form
    for expected_snippet in expected_snippets:
        assert expected_snippet in compiled_query.query


@pytest.mark.parametrize(
    (
        "search_string",
        "expected_bounds",
        "expected_count",
        "expected_snippets",
    ),
    [
        (
            "foo=bar and type:node",
            "bbox",
            1,
            ['node["foo"="bar"]({{bbox}});'],
        ),
        (
            "foo=bar and (type:node or type:way)",
            "bbox",
            2,
            [
                'node["foo"="bar"]({{bbox}});',
                'way["foo"="bar"]({{bbox}});',
            ],
        ),
        (
            "foo=bar and type:node global",
            "global",
            1,
            ['node["foo"="bar"];'],
        ),
        (
            "type:node",
            "bbox",
            1,
            ["node({{bbox}});"],
        ),
        (
            "type:node in bbox",
            "bbox",
            1,
            ["node({{bbox}});"],
        ),
        (
            "type:node in foobar",
            "area",
            1,
            [
                "{{geocodeArea:foobar}}->.searchArea;",
                "node(area.searchArea);",
            ],
        ),
        (
            "type:node around foobar",
            "around",
            1,
            ["node(around:{{radius}},{{geocodeCoords:foobar}});"],
        ),
        (
            'newer:"2000-01-01T01:01:01Z" and type:node',
            "bbox",
            1,
            ['node(newer:"2000-01-01T01:01:01Z")({{bbox}});'],
        ),
        (
            "newer:1day and type:node",
            "bbox",
            1,
            ['node(newer:"{{date:1day}}")({{bbox}});'],
        ),
        (
            "user:foo and type:node",
            "bbox",
            1,
            ['node(user:"foo")({{bbox}});'],
        ),
        (
            "uid:123 and type:node",
            "bbox",
            1,
            ["node(uid:123)({{bbox}});"],
        ),
        (
            "id:123 and type:node",
            "bbox",
            1,
            ["node(123)({{bbox}});"],
        ),
    ],
)
def test_compile_upstream_regions_and_meta_cases(
    compiler,
    search_string,
    expected_bounds,
    expected_count,
    expected_snippets,
) -> None:
    compiled_query = compiler.compile(search_string)

    assert compiled_query.bounds.value == expected_bounds
    assert compiled_query.query_count == expected_count
    for expected_snippet in expected_snippets:
        assert expected_snippet in compiled_query.query


@pytest.mark.parametrize(
    ("search_string", "expected_count", "expected_snippets"),
    [
        (
            "foo='' and type:way",
            1,
            ['way["foo"~"^$"]({{bbox}});'],
        ),
        (
            "''=bar and type:way",
            1,
            ['way[~"^$"~"^bar$"]({{bbox}});'],
        ),
        (
            "''='*' and type:way",
            1,
            ['way[~"^$"~"^\\\\*$"]({{bbox}});'],
        ),
        (
            "(''=* or ''~/.../) and type:way",
            2,
            [
                'way[~"^$"~".*"]({{bbox}});',
                'way[~"^$"~"..."]({{bbox}});',
            ],
        ),
        (
            "(foo='\\t' or foo='\\n' or asd='\\\\t') and type:way",
            3,
            [
                'way["foo"="\\t"]({{bbox}});',
                'way["foo"="\\n"]({{bbox}});',
                'way["asd"="\\\\t"]({{bbox}});',
            ],
        ),
    ],
)
def test_compile_special_case_conversions(
    compiler,
    search_string,
    expected_count,
    expected_snippets,
) -> None:
    compiled_query = compiler.compile(search_string)

    assert compiled_query.query_count == expected_count
    for expected_snippet in expected_snippets:
        assert expected_snippet in compiled_query.query


def test_compile_unknown_free_form_preset_raises(
    semantic_resolver,
    wizard_modules,
) -> None:
    compiler = wizard_modules.compiler.WizardQueryCompiler(
        semantic_resolver=semantic_resolver,
    )

    with pytest.raises(
        wizard_modules.exceptions.OsmInfoWizardFreeFormError,
        match="Unknown wizard preset: foo",
    ):
        compiler.compile("foo in Berlin")


def test_compile_unknown_plain_free_form_preset_raises(
    semantic_resolver,
    wizard_modules,
) -> None:
    compiler = wizard_modules.compiler.WizardQueryCompiler(
        semantic_resolver=semantic_resolver,
    )

    with pytest.raises(
        wizard_modules.exceptions.OsmInfoWizardFreeFormError,
        match="Unknown wizard preset: foo",
    ):
        compiler.compile("foo")


@pytest.mark.parametrize(
    ("search_string", "expected_query"),
    [
        ("Shelter", 'node["amenity"="shelter"](bbox);out geom;'),
        ("Hospital", 'nwr["amenity"="hospital"](bbox);out geom;'),
        ("Highway", 'way["highway"](bbox);out geom;'),
    ],
)
def test_compile_free_form_presets_with_stub_repository(
    semantic_resolver,
    wizard_modules,
    search_string,
    expected_query,
) -> None:
    compiler = wizard_modules.compiler.WizardQueryCompiler(
        semantic_resolver=semantic_resolver,
    )

    compiled_query = compiler.compile(search_string)

    assert compact_query(compiled_query.query) == expected_query


@pytest.mark.parametrize(
    ("search_string", "expected_snippet"),
    [
        ('ref~"[0-9]+"', 'nwr["ref"~"[0-9]+"]({{bbox}});'),
        ('~building~".*"', 'nwr[~"building"~".*"]({{bbox}});'),
        ('name not like "foo"', 'nwr["name"!~"foo"]({{bbox}});'),
        (
            '"addr:housenumber" is not null',
            'nwr["addr:housenumber"]({{bbox}});',
        ),
        (
            '"addr:housenumber" is null',
            'nwr["addr:housenumber"!~".*"]({{bbox}});',
        ),
        ('newer:"4 weeks"', 'nwr(newer:"{{date:4 weeks}}")({{bbox}});'),
        (
            'newer:"2013-11-24T19:01:00Z"',
            'nwr(newer:"2013-11-24T19:01:00Z")({{bbox}});',
        ),
        ("id:263621287", "nwr(263621287)({{bbox}});"),
        (
            "user:SomeonesUsername",
            'nwr(user:"SomeonesUsername")({{bbox}});',
        ),
        ("uid:12345", "nwr(uid:12345)({{bbox}});"),
        ("type:relation", "relation({{bbox}});"),
        (
            'amenity=drinking_water and newer:"4 weeks"',
            'nwr["amenity"="drinking_water"](newer:"{{date:4 weeks}}")({{bbox}});',
        ),
    ],
)
def test_compile_documented_selector_rules(
    compiler,
    search_string,
    expected_snippet,
) -> None:
    compiled_query = compiler.compile(search_string)

    assert expected_snippet in compiled_query.query


def test_compile_does_not_quote_complex_expression_fallback(
    compiler, wizard_modules
) -> None:
    with pytest.raises(wizard_modules.exceptions.OsmInfoWizardParserError):
        compiler.compile("Drinking Water in London")


def test_repair_search_uses_fuzzy_preset_matching(compiler) -> None:
    assert (
        compiler.repair_search("restarant in Berlin") == "Restaurant in Berlin"
    )


def test_invalid_type_raises_parser_error(compiler, wizard_modules) -> None:
    with pytest.raises(wizard_modules.exceptions.OsmInfoWizardParserError):
        compiler.compile("type:restaurant global")
