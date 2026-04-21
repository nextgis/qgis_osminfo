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

import importlib
from importlib.util import find_spec
from typing import Any, Callable, Optional, cast

from osminfo.core.exceptions import (
    OsmInfoWizardDependencyError,
    OsmInfoWizardParserError,
)

from .models import (
    ConditionNode,
    ConditionQueryType,
    LogicalNode,
    LogicalOperator,
    MetaQueryType,
    OsmElementType,
    RegexValue,
    WizardBounds,
    WizardExpression,
    WizardSearch,
)


def _enable_packrat(parser_element_class: Any) -> None:
    enable_packrat = getattr(parser_element_class, "enable_packrat", None)
    if enable_packrat is not None:
        enable_packrat()
        return

    parser_element_class.enablePackrat()


def _set_parse_action(parser_element, action):
    setter = getattr(parser_element, "set_parse_action", None)
    if setter is not None:
        return setter(action)

    return parser_element.setParseAction(action)


class _PyparsingRuntime:
    def __init__(self, module: Any) -> None:
        self.Empty = module.Empty
        self.Keyword = module.Keyword
        self.Literal = module.Literal
        self.MatchFirst = module.MatchFirst
        self.ParseException = module.ParseException
        self.ParseFatalException = module.ParseFatalException
        self.ParserElement = module.ParserElement
        self.Regex = module.Regex
        self.StringEnd = module.StringEnd
        self.Suppress = module.Suppress
        self.infix_notation = getattr(module, "infix_notation", None)
        if self.infix_notation is None:
            self.infix_notation = module.infixNotation
        self.op_assoc = module.opAssoc


def _load_pyparsing_runtime() -> _PyparsingRuntime:
    if find_spec("pyparsing") is None:
        raise OsmInfoWizardDependencyError("pyparsing")

    module = importlib.import_module("pyparsing")

    runtime = _PyparsingRuntime(module)
    _enable_packrat(runtime.ParserElement)
    return runtime


class WizardSyntaxParser:
    """Parse wizard search text into the internal abstract syntax tree.

    Build and execute the pyparsing grammar that recognizes wizard bounds,
    predicates, and boolean expressions.
    """

    _STRING_PATTERN = r"[^'\" ()~=!*/:<>&|\[\]{}#+@$%?^.,]+"
    _KEY_PATTERN = r"[a-zA-Z0-9_:-]+"
    _DOUBLE_QUOTED_PATTERN = r'"(?:[^"\\]|\\.)*"'
    _SINGLE_QUOTED_PATTERN = r"'(?:[^'\\]|\\.)*'"
    _REGEX_PATTERN = r"/(?:[^/\\]|\\.)+/i?"
    _ESCAPE_MAP = {
        "b": "\b",
        "f": "\f",
        "n": "\n",
        "r": "\r",
        "t": "\t",
        "v": "\x0b",
        "\\": "\\",
        '"': '"',
        "'": "'",
    }

    def __init__(self) -> None:
        self._runtime: Optional[_PyparsingRuntime] = None
        self._grammar: Optional[Any] = None

    def parse(self, search_string: str) -> WizardSearch:
        runtime = self._ensure_runtime()
        grammar = self._ensure_grammar()
        try:
            parse_string = getattr(grammar, "parse_string", None)
            if parse_string is not None:
                parsed = parse_string(search_string, parse_all=True)
            else:
                parsed = grammar.parseString(
                    search_string,
                    parseAll=True,
                )
        except (
            runtime.ParseException,
            runtime.ParseFatalException,
        ) as error:
            raise OsmInfoWizardParserError(error.msg, error.loc) from error

        return cast(WizardSearch, parsed[0])

    def _ensure_runtime(self) -> _PyparsingRuntime:
        if self._runtime is None:
            self._runtime = _load_pyparsing_runtime()

        return self._runtime

    def _ensure_grammar(self):
        if self._grammar is None:
            self._grammar = self._build_grammar()

        return self._grammar

    def _build_grammar(self):
        runtime = self._ensure_runtime()
        string_value, key_value, string_or_regex = self._build_value_grammar()
        statement = self._build_statement_grammar(
            string_value,
            key_value,
            string_or_regex,
        )
        expression = self._build_expression_grammar(statement)
        geo_query = self._build_geo_query_grammar(expression, string_value)
        return geo_query + runtime.StringEnd()

    @staticmethod
    def _runtime_keyword(runtime: _PyparsingRuntime, word: str):
        return runtime.MatchFirst(
            [runtime.Keyword(word), runtime.Keyword(word.upper())]
        )

    def _exact_keyword(self, word: str):
        return self._ensure_runtime().Keyword(word)

    def _keyword(self, word: str):
        runtime = self._ensure_runtime()
        return self._runtime_keyword(runtime, word)

    def _phrase(self, *words: str):
        runtime = self._ensure_runtime()
        lower_phrase = self._runtime_keyword(runtime, words[0])
        upper_phrase = self._runtime_keyword(runtime, words[0].upper())

        for word in words[1:]:
            lower_phrase += self._runtime_keyword(runtime, word)
            upper_phrase += self._runtime_keyword(runtime, word.upper())

        return runtime.MatchFirst([lower_phrase, upper_phrase])

    def _build_value_grammar(self):
        runtime = self._ensure_runtime()
        quoted_string = runtime.MatchFirst(
            [
                runtime.Regex(self._DOUBLE_QUOTED_PATTERN),
                runtime.Regex(self._SINGLE_QUOTED_PATTERN),
            ]
        )
        quoted_string = _set_parse_action(
            quoted_string,
            self._parse_quoted_string,
        )
        simple_string = runtime.Regex(self._STRING_PATTERN)
        string_value = quoted_string | simple_string
        key_value = quoted_string | runtime.Regex(self._KEY_PATTERN)
        regex_value = _set_parse_action(
            runtime.Regex(self._REGEX_PATTERN),
            self._parse_regex_string,
        )
        string_or_regex = regex_value | string_value

        return string_value, key_value, string_or_regex

    def _build_statement_grammar(
        self,
        string_value,
        key_value,
        string_or_regex,
    ):
        runtime = self._ensure_runtime()
        colon = runtime.Suppress(":")
        equals = runtime.Suppress(runtime.Literal("==") | runtime.Literal("="))
        not_equals = runtime.Suppress(
            runtime.Literal("!=") | runtime.Literal("<>")
        )
        like_operator = runtime.Suppress(
            runtime.Literal("~=")
            | runtime.Literal("=~")
            | runtime.Literal("~")
        )
        not_like_operator = runtime.Suppress(runtime.Literal("!~"))
        wildcard = runtime.Suppress(runtime.Literal("*"))

        type_statement = self._build_type_statement(colon)
        meta_statement = self._build_meta_statement(string_value, colon)
        key_eq_value = self._build_binary_condition(
            key_value,
            string_value,
            equals,
            ConditionQueryType.EQ,
        )
        key_not_eq_value = self._build_binary_condition(
            key_value,
            string_value,
            not_equals,
            ConditionQueryType.NEQ,
        )
        key_present = self._build_key_presence_statement(
            key_value,
            string_value,
            equals,
            wildcard,
            positive=True,
        )
        key_not_present = self._build_key_presence_statement(
            key_value,
            string_value,
            not_equals,
            wildcard,
            positive=False,
        )
        key_like_value = self._build_like_statement(
            key_value,
            string_value,
            string_or_regex,
            like_operator,
            positive=True,
        )
        like_key_like_value = (
            runtime.Suppress(runtime.Literal("~"))
            + string_value("key")
            + like_operator
            + string_or_regex("val")
        )
        like_key_like_value = _set_parse_action(
            like_key_like_value,
            self._build_condition(ConditionQueryType.LIKE_LIKE),
        )
        key_not_like_value = self._build_like_statement(
            key_value,
            string_value,
            string_or_regex,
            not_like_operator,
            positive=False,
        )
        key_substr_value = string_value("key") + colon + string_value("val")
        key_substr_value = _set_parse_action(
            key_substr_value,
            self._build_substr_condition,
        )
        free_form = _set_parse_action(
            string_value("free"), self._build_free_form_condition
        )

        return runtime.MatchFirst(
            [
                type_statement,
                meta_statement,
                key_eq_value,
                key_not_eq_value,
                key_present,
                key_not_present,
                key_like_value,
                like_key_like_value,
                key_not_like_value,
                key_substr_value,
                free_form,
            ]
        )

    def _build_expression_grammar(self, statement):
        runtime = self._ensure_runtime()
        left_paren = runtime.Suppress(runtime.Literal("("))
        right_paren = runtime.Suppress(runtime.Literal(")"))
        logical_and = (
            runtime.Literal("&&") | runtime.Literal("&") | self._keyword("and")
        )
        logical_or = (
            runtime.Literal("||") | runtime.Literal("|") | self._keyword("or")
        )

        return runtime.infix_notation(
            statement,
            [
                (
                    logical_and,
                    2,
                    runtime.op_assoc.LEFT,
                    self._build_logical_node(LogicalOperator.AND),
                ),
                (
                    logical_or,
                    2,
                    runtime.op_assoc.LEFT,
                    self._build_logical_node(LogicalOperator.OR),
                ),
            ],
            lpar=left_paren,
            rpar=right_paren,
        )

    def _build_geo_query_grammar(self, expression, string_value):
        runtime = self._ensure_runtime()
        in_bbox_keywords = self._phrase("in", "bbox").suppress()
        in_keyword = self._keyword("in").suppress()
        around_keyword = self._keyword("around").suppress()
        global_keyword = self._keyword("global").suppress()
        in_bbox = expression("query") + in_bbox_keywords
        in_bbox = _set_parse_action(
            in_bbox, self._build_search_with_bounds(WizardBounds.BBOX)
        )

        in_area = expression("query") + in_keyword + string_value("area")
        in_area = _set_parse_action(
            in_area, self._build_search_with_bounds(WizardBounds.AREA)
        )

        around_area = (
            expression("query") + around_keyword + string_value("area")
        )
        around_area = _set_parse_action(
            around_area, self._build_search_with_bounds(WizardBounds.AROUND)
        )

        global_query = expression("query") + global_keyword
        global_query = _set_parse_action(
            global_query, self._build_search_with_bounds(WizardBounds.GLOBAL)
        )

        default_query = _set_parse_action(
            expression("query"),
            self._build_search_with_bounds(WizardBounds.BBOX),
        )

        return runtime.MatchFirst(
            [in_bbox, in_area, around_area, global_query, default_query]
        )

    def _build_type_statement(self, colon):
        runtime = self._ensure_runtime()
        type_keyword = self._exact_keyword("type").suppress()

        osm_type = runtime.MatchFirst(
            [
                self._exact_keyword(OsmElementType.NODE.value),
                self._exact_keyword(OsmElementType.WAY.value),
                self._exact_keyword(OsmElementType.RELATION.value),
                self._exact_keyword(OsmElementType.CLOSED_WAY.value),
            ]
        )

        type_prefix = type_keyword + colon
        return runtime.MatchFirst(
            [
                _set_parse_action(
                    type_prefix + osm_type("type"),
                    self._build_type_condition,
                ),
                _set_parse_action(
                    type_prefix + runtime.Empty(),
                    self._fatal_parser("Unknown OSM type"),
                ),
            ]
        )

    def _build_meta_statement(self, string_value, colon):
        runtime = self._ensure_runtime()
        meta_type = runtime.MatchFirst(
            [self._exact_keyword(meta.value) for meta in MetaQueryType]
        )

        return _set_parse_action(
            meta_type("meta") + colon + string_value("val"),
            self._build_meta_condition,
        )

    def _build_binary_condition(
        self,
        key_value,
        string_value,
        operator,
        query_type: ConditionQueryType,
    ):
        return _set_parse_action(
            key_value("key") + operator + string_value("val"),
            self._build_condition(query_type),
        )

    def _build_key_presence_statement(
        self,
        key_value,
        string_value,
        operator,
        wildcard,
        *,
        positive: bool,
    ):
        query_type = (
            ConditionQueryType.KEY if positive else ConditionQueryType.NO_KEY
        )
        runtime = self._ensure_runtime()
        null_phrase = (
            runtime.MatchFirst(
                [
                    self._phrase("is", "not", "null").suppress(),
                    self._phrase("IS", "NOT", "NULL").suppress(),
                ]
            )
            if positive
            else runtime.MatchFirst(
                [
                    self._phrase("is", "null").suppress(),
                    self._phrase("IS", "NULL").suppress(),
                ]
            )
        )

        return runtime.MatchFirst(
            [
                _set_parse_action(
                    key_value("key") + operator + wildcard,
                    self._build_condition(query_type),
                ),
                _set_parse_action(
                    string_value("key") + null_phrase,
                    self._build_condition(query_type),
                ),
            ]
        )

    def _build_like_statement(
        self,
        key_value,
        string_value,
        string_or_regex,
        operator,
        *,
        positive: bool,
    ):
        query_type = (
            ConditionQueryType.LIKE
            if positive
            else ConditionQueryType.NOT_LIKE
        )
        runtime = self._ensure_runtime()

        if positive:
            textual_operator = self._keyword("like").suppress()
            textual_expression = (
                string_value("key") + textual_operator + string_or_regex("val")
            )
        else:
            not_like_phrase = runtime.MatchFirst(
                [
                    self._phrase("not", "like").suppress(),
                    self._phrase("NOT", "LIKE").suppress(),
                ]
            )
            textual_expression = (
                string_value("key") + not_like_phrase + string_or_regex("val")
            )

        return runtime.MatchFirst(
            [
                _set_parse_action(
                    key_value("key") + operator + string_or_regex("val"),
                    self._build_condition(query_type),
                ),
                _set_parse_action(
                    textual_expression, self._build_condition(query_type)
                ),
            ]
        )

    def _build_search_with_bounds(self, bounds: WizardBounds):
        def build(tokens):
            return WizardSearch(
                bounds=bounds,
                query=tokens["query"],
                area=tokens.get("area"),
            )

        return build

    def _build_condition(
        self,
        query_type: ConditionQueryType,
    ) -> Callable[[Any], ConditionNode]:
        def build(tokens):
            return ConditionNode(
                query=query_type,
                key=tokens.get("key"),
                val=tokens.get("val"),
            )

        return build

    def _build_type_condition(self, tokens):
        return ConditionNode(
            query=ConditionQueryType.TYPE,
            type=OsmElementType(tokens["type"].lower()),
        )

    def _build_meta_condition(self, tokens):
        return ConditionNode(
            query=ConditionQueryType.META,
            meta=MetaQueryType(tokens["meta"].lower()),
            val=tokens["val"],
        )

    def _build_substr_condition(self, source, location, tokens):
        runtime = self._ensure_runtime()
        if tokens["key"] == ConditionQueryType.TYPE.value:
            raise runtime.ParseFatalException(
                source,
                location,
                "Reserved key cannot be used with substring operator",
            )

        return ConditionNode(
            query=ConditionQueryType.SUBSTR,
            key=tokens["key"],
            val=tokens["val"],
        )

    def _build_free_form_condition(self, tokens):
        return ConditionNode(
            query=ConditionQueryType.FREE_FORM,
            free=tokens["free"],
        )

    def _build_logical_node(
        self,
        operator: LogicalOperator,
    ) -> Callable[[Any], WizardExpression]:
        def build(tokens):
            items = tokens[0]
            node = items[0]
            for index in range(2, len(items), 2):
                node = LogicalNode(
                    logical=operator,
                    queries=[node, items[index]],
                )
            return node

        return build

    def _fatal_parser(
        self,
        message: str,
    ) -> Callable[[str, int, Any], None]:
        runtime = self._ensure_runtime()

        def raise_error(source: str, location: int, tokens) -> None:
            raise runtime.ParseFatalException(source, location, message)

        return raise_error

    def _parse_quoted_string(self, source, location, tokens):
        runtime = self._ensure_runtime()
        raw_value = tokens[0]
        quote_character = raw_value[0]
        value = raw_value[1:-1]
        characters = []
        index = 0

        while index < len(value):
            character = value[index]
            if character != "\\":
                characters.append(character)
                index += 1
                continue

            index += 1
            if index >= len(value):
                raise runtime.ParseFatalException(
                    source,
                    location + len(raw_value) - 1,
                    "Invalid escape sequence",
                )

            escaped = value[index]
            if escaped not in self._ESCAPE_MAP:
                raise runtime.ParseFatalException(
                    source,
                    location + index + 1,
                    f"Invalid escape sequence: \\\\{escaped}",
                )

            characters.append(self._ESCAPE_MAP[escaped])
            index += 1

        if quote_character not in ('"', "'"):
            raise AssertionError("Unsupported quote character")

        return "".join(characters)

    def _parse_regex_string(self, tokens):
        raw_value = tokens[0]
        modifier = "i" if raw_value.endswith("/i") else ""
        end_index = -2 if modifier else -1
        regex = raw_value[1:end_index].replace("\\/", "/")
        return RegexValue(regex=regex, modifier=modifier)
