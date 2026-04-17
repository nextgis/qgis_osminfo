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

# ruff: noqa: I001

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Optional, Sequence, Tuple

from qgis.PyQt.QtCore import QAbstractListModel, QModelIndex, QObject, Qt
from qgis.PyQt.QtWidgets import QComboBox, QCompleter, QLineEdit, QWidget

from osminfo.openstreetmap.preset_repository import (
    PresetDefinition,
    PresetRepository,
)
from osminfo.overpass.query_builder.wizard.free_form_syntax import (
    FREE_FORM_BOUNDS_KEYWORDS,
    FREE_FORM_LOGICAL_KEYWORDS,
    contains_reserved_free_form_syntax,
)


_SPECIAL_TOKEN_CHARACTERS = set("()=:~&|*/<>![]{}#+@$%?^.,")
_MULTI_CHARACTER_OPERATORS = (
    "&&",
    "||",
    "==",
    "!=",
    "<>",
    "!~",
    "=~",
    "~=",
)
_LOGICAL_KEYWORDS = set(FREE_FORM_LOGICAL_KEYWORDS)
_BOUNDS_KEYWORDS = set(FREE_FORM_BOUNDS_KEYWORDS)
_AREA_BOUND_KEYWORDS = set(FREE_FORM_BOUNDS_KEYWORDS)
_MINIMUM_PRESET_PREFIX_LENGTH = 2


@dataclass(frozen=True)
class SearchCompletionContext:
    prefix: str
    replacement_start: int
    replacement_end: int
    allow_preset_suggestions: bool
    quote_character: Optional[str] = None
    quote_is_closed: bool = True


class SearchCompletionReplaceMode(Enum):
    FRAGMENT = "fragment"
    FULL_TEXT = "full_text"


@dataclass(frozen=True)
class SearchCompletionEntry:
    display_text: str
    insert_text: str
    replace_mode: SearchCompletionReplaceMode


@dataclass(frozen=True)
class PresetCompletionItem:
    display_text: str
    terms: Tuple[str, ...]


class SearchTokenKind(Enum):
    SPACE = "space"
    QUOTED = "quoted"
    OPERATOR = "operator"
    WORD = "word"


@dataclass(frozen=True)
class _SearchToken:
    kind: SearchTokenKind
    text: str
    start: int
    end: int
    is_closed: bool = True


class SearchCompletionParser:
    @classmethod
    def build_context(
        cls,
        search_text: str,
        cursor_position: Optional[int] = None,
    ) -> SearchCompletionContext:
        if cursor_position is None:
            cursor_position = len(search_text)

        cursor_position = max(0, min(cursor_position, len(search_text)))
        tokens = cls._tokenize_search_text(search_text)
        quoted_token = cls._quoted_token_at_cursor(tokens, cursor_position)
        if quoted_token is not None:
            return cls._build_quoted_context(
                search_text,
                cursor_position,
                tokens,
                quoted_token,
            )

        statement_start = cls._statement_start(tokens, cursor_position)
        statement_end = cls._statement_end(
            tokens,
            cursor_position,
            len(search_text),
        )
        replacement_start = cls._trim_leading_spaces(
            search_text,
            statement_start,
            statement_end,
        )
        replacement_end = cls._trim_trailing_spaces(
            search_text,
            statement_start,
            statement_end,
        )
        prefix_end = max(
            replacement_start,
            min(cursor_position, replacement_end),
        )
        prefix = search_text[replacement_start:prefix_end]
        statement_text = search_text[replacement_start:replacement_end]
        allow_preset_suggestions = cls._can_suggest_presets(
            statement_text,
            previous_keyword=cls._previous_keyword(tokens, statement_start),
            is_quoted=False,
        )

        return SearchCompletionContext(
            prefix=prefix,
            replacement_start=replacement_start,
            replacement_end=replacement_end,
            allow_preset_suggestions=allow_preset_suggestions,
        )

    @classmethod
    def apply_completion(
        cls,
        search_text: str,
        context: SearchCompletionContext,
        entry: SearchCompletionEntry,
    ) -> str:
        if entry.replace_mode is SearchCompletionReplaceMode.FULL_TEXT:
            return entry.insert_text

        replacement_text = cls._format_fragment_completion(
            entry.insert_text,
            context,
        )
        return (
            search_text[: context.replacement_start]
            + replacement_text
            + search_text[context.replacement_end :]
        )

    @staticmethod
    def normalize_completion_value(value: str) -> str:
        normalized_value = value.strip().lower()
        normalized_value = normalized_value.replace("_", " ")
        normalized_value = normalized_value.replace("/", " ")
        return " ".join(normalized_value.split())

    @classmethod
    def _build_quoted_context(
        cls,
        search_text: str,
        cursor_position: int,
        tokens: Sequence[_SearchToken],
        quoted_token: _SearchToken,
    ) -> SearchCompletionContext:
        statement_start = cls._statement_start(tokens, quoted_token.start)
        previous_keyword = cls._previous_keyword(tokens, statement_start)
        replacement_start = quoted_token.start + 1
        replacement_end = (
            quoted_token.end - 1
            if quoted_token.is_closed
            else quoted_token.end
        )
        prefix_end = max(
            replacement_start,
            min(cursor_position, replacement_end),
        )
        prefix = search_text[replacement_start:prefix_end]

        return SearchCompletionContext(
            prefix=prefix,
            replacement_start=replacement_start,
            replacement_end=replacement_end,
            allow_preset_suggestions=cls._can_suggest_presets(
                prefix,
                previous_keyword=previous_keyword,
                is_quoted=True,
            ),
            quote_character=quoted_token.text[:1],
            quote_is_closed=quoted_token.is_closed,
        )

    @staticmethod
    def _can_suggest_presets(
        statement_text: str,
        previous_keyword: Optional[str],
        *,
        is_quoted: bool,
    ) -> bool:
        if previous_keyword in _AREA_BOUND_KEYWORDS:
            return False

        normalized_statement = statement_text.strip()
        if len(normalized_statement) == 0:
            return False

        if is_quoted:
            return True

        if contains_reserved_free_form_syntax(normalized_statement):
            return False

        return True

    @classmethod
    def _format_fragment_completion(
        cls,
        value: str,
        context: SearchCompletionContext,
    ) -> str:
        if context.quote_character is not None:
            escaped_value = cls._escape_quoted_value(
                value,
                context.quote_character,
            )
            if context.quote_is_closed:
                return escaped_value

            return f"{escaped_value}{context.quote_character}"

        if cls._requires_quotes(value):
            escaped_value = cls._escape_quoted_value(value, '"')
            return f'"{escaped_value}"'

        return value

    @staticmethod
    def _escape_quoted_value(value: str, quote_character: str) -> str:
        escaped_value = value.replace("\\", "\\\\")
        return escaped_value.replace(quote_character, f"\\{quote_character}")

    @staticmethod
    def _requires_quotes(value: str) -> bool:
        if len(value.strip()) == 0:
            return True

        for character in value:
            if character.isspace() or character in _SPECIAL_TOKEN_CHARACTERS:
                return True

        return False

    @staticmethod
    def _quoted_token_at_cursor(
        tokens: Sequence[_SearchToken],
        cursor_position: int,
    ) -> Optional[_SearchToken]:
        for token in tokens:
            if token.kind is not SearchTokenKind.QUOTED:
                continue

            if token.start < cursor_position <= token.end:
                return token

            if cursor_position == token.start + 1:
                return token

        return None

    @staticmethod
    def _statement_start(
        tokens: Sequence[_SearchToken],
        cursor_position: int,
    ) -> int:
        statement_start = 0
        for token in tokens:
            if token.end > cursor_position:
                break

            if SearchCompletionParser._is_statement_separator(token):
                statement_start = token.end

        return statement_start

    @staticmethod
    def _statement_end(
        tokens: Sequence[_SearchToken],
        cursor_position: int,
        text_length: int,
    ) -> int:
        for token in tokens:
            if token.start < cursor_position:
                continue

            if SearchCompletionParser._is_statement_separator(token):
                return token.start

        return text_length

    @staticmethod
    def _previous_keyword(
        tokens: Sequence[_SearchToken],
        position: int,
    ) -> Optional[str]:
        for token in reversed(tokens):
            if token.end > position:
                continue

            if token.kind is SearchTokenKind.SPACE:
                continue

            if token.kind is SearchTokenKind.WORD:
                return token.text.casefold()

            return None

        return None

    @staticmethod
    def _is_statement_separator(token: _SearchToken) -> bool:
        if token.kind is SearchTokenKind.OPERATOR and token.text in (
            "&&",
            "||",
            "&",
            "|",
            "(",
            ")",
        ):
            return True

        if token.kind is not SearchTokenKind.WORD:
            return False

        keyword = token.text.casefold()
        return keyword in _LOGICAL_KEYWORDS or keyword in _BOUNDS_KEYWORDS

    @staticmethod
    def _trim_leading_spaces(
        search_text: str,
        start_index: int,
        end_index: int,
    ) -> int:
        trimmed_index = start_index
        while (
            trimmed_index < end_index and search_text[trimmed_index].isspace()
        ):
            trimmed_index += 1

        return trimmed_index

    @staticmethod
    def _trim_trailing_spaces(
        search_text: str,
        start_index: int,
        end_index: int,
    ) -> int:
        trimmed_index = end_index
        while (
            trimmed_index > start_index
            and search_text[trimmed_index - 1].isspace()
        ):
            trimmed_index -= 1

        return trimmed_index

    @classmethod
    def _tokenize_search_text(cls, search_text: str) -> List[_SearchToken]:
        tokens: List[_SearchToken] = []
        index = 0
        while index < len(search_text):
            character = search_text[index]
            if character.isspace():
                start_index = index
                while (
                    index < len(search_text) and search_text[index].isspace()
                ):
                    index += 1

                tokens.append(
                    _SearchToken(
                        kind=SearchTokenKind.SPACE,
                        text=search_text[start_index:index],
                        start=start_index,
                        end=index,
                    )
                )
                continue

            if character in ('"', "'"):
                token, index = cls._read_quoted_token(search_text, index)
                tokens.append(token)
                continue

            operator = cls._operator_at(search_text, index)
            if operator is not None:
                tokens.append(
                    _SearchToken(
                        kind=SearchTokenKind.OPERATOR,
                        text=operator,
                        start=index,
                        end=index + len(operator),
                    )
                )
                index += len(operator)
                continue

            start_index = index
            while index < len(search_text):
                current_character = search_text[index]
                if (
                    current_character.isspace()
                    or current_character in ('"', "'")
                    or current_character in _SPECIAL_TOKEN_CHARACTERS
                ):
                    break

                if cls._operator_at(search_text, index) is not None:
                    break

                index += 1

            tokens.append(
                _SearchToken(
                    kind=SearchTokenKind.WORD,
                    text=search_text[start_index:index],
                    start=start_index,
                    end=index,
                )
            )

        return tokens

    @staticmethod
    def _read_quoted_token(
        search_text: str,
        start_index: int,
    ) -> Tuple[_SearchToken, int]:
        quote_character = search_text[start_index]
        index = start_index + 1
        is_escaped = False
        while index < len(search_text):
            current_character = search_text[index]
            if is_escaped:
                is_escaped = False
                index += 1
                continue

            if current_character == "\\":
                is_escaped = True
                index += 1
                continue

            if current_character == quote_character:
                index += 1
                return (
                    _SearchToken(
                        kind=SearchTokenKind.QUOTED,
                        text=search_text[start_index:index],
                        start=start_index,
                        end=index,
                        is_closed=True,
                    ),
                    index,
                )

            index += 1

        return (
            _SearchToken(
                kind=SearchTokenKind.QUOTED,
                text=search_text[start_index:index],
                start=start_index,
                end=index,
                is_closed=False,
            ),
            index,
        )

    @staticmethod
    def _operator_at(search_text: str, index: int) -> Optional[str]:
        for operator in _MULTI_CHARACTER_OPERATORS:
            if search_text.startswith(operator, index):
                return operator

        character = search_text[index]
        if character in _SPECIAL_TOKEN_CHARACTERS:
            return character

        return None


class SearchCompletionSource(ABC):
    @abstractmethod
    def build_entries(
        self,
        search_text: str,
        context: SearchCompletionContext,
    ) -> List[SearchCompletionEntry]:
        raise NotImplementedError()


class PresetCompletionSource(SearchCompletionSource):
    def __init__(
        self,
        preset_items: Optional[Sequence[PresetCompletionItem]] = None,
        minimum_prefix_length: int = _MINIMUM_PRESET_PREFIX_LENGTH,
        repository: Optional[PresetRepository] = None,
    ) -> None:
        self._minimum_prefix_length = minimum_prefix_length
        self._preset_items = list(
            preset_items
            if preset_items is not None
            else self._load_preset_completion_items(repository)
        )

    @classmethod
    def _load_preset_completion_items(
        cls,
        repository: Optional[PresetRepository] = None,
    ) -> List[PresetCompletionItem]:
        preset_repository = repository or PresetRepository()
        try:
            presets = preset_repository.load()
        except Exception:
            return []

        preset_terms_by_name: Dict[str, List[str]] = {}
        display_names: Dict[str, str] = {}

        for preset in presets.values():
            if preset.searchable is False:
                continue

            display_text = cls._display_text_for_preset(preset)
            if display_text is None:
                continue

            normalized_key = display_text.casefold()
            display_names.setdefault(normalized_key, display_text)
            preset_terms = preset_terms_by_name.setdefault(
                normalized_key,
                [],
            )
            for term in cls._preset_terms(preset, display_text):
                if term in preset_terms:
                    continue
                preset_terms.append(term)

        completion_items: List[PresetCompletionItem] = []
        for normalized_key, preset_terms in preset_terms_by_name.items():
            completion_items.append(
                PresetCompletionItem(
                    display_text=display_names[normalized_key],
                    terms=tuple(preset_terms),
                )
            )

        completion_items.sort(key=lambda item: item.display_text.casefold())
        return completion_items

    def build_entries(
        self,
        search_text: str,
        context: SearchCompletionContext,
    ) -> List[SearchCompletionEntry]:
        if not context.allow_preset_suggestions:
            return []

        normalized_prefix = SearchCompletionParser.normalize_completion_value(
            context.prefix
        )
        if len(normalized_prefix) < self._minimum_prefix_length:
            return []

        return [
            SearchCompletionEntry(
                display_text=preset_item.display_text,
                insert_text=preset_item.display_text,
                replace_mode=SearchCompletionReplaceMode.FRAGMENT,
            )
            for preset_item in self._matching_preset_items(normalized_prefix)
        ]

    @staticmethod
    def _display_text_for_preset(
        preset: PresetDefinition,
    ) -> Optional[str]:
        for display_text in (preset.nameCased, preset.name):
            if display_text is None:
                continue

            stripped_text = display_text.strip()
            if len(stripped_text) > 0:
                return stripped_text

        return None

    @staticmethod
    def _preset_terms(
        preset: PresetDefinition,
        display_text: str,
    ) -> List[str]:
        preset_terms: List[str] = []
        for term in [display_text, preset.name, *preset.terms]:
            if not isinstance(term, str):
                continue

            normalized_term = (
                SearchCompletionParser.normalize_completion_value(term)
            )
            if len(normalized_term) == 0 or normalized_term in preset_terms:
                continue

            preset_terms.append(normalized_term)

        return preset_terms

    def _matching_preset_items(
        self,
        normalized_prefix: str,
    ) -> List[PresetCompletionItem]:
        ranked_items: List[
            Tuple[Tuple[int, int, str], PresetCompletionItem]
        ] = []
        for preset_item in self._preset_items:
            matching_indexes = [
                index
                for index, term in enumerate(preset_item.terms)
                if self._term_matches_prefix(term, normalized_prefix)
            ]
            if len(matching_indexes) == 0:
                continue

            ranking_key = (
                0
                if self._term_matches_prefix(
                    preset_item.terms[0],
                    normalized_prefix,
                )
                else 1,
                matching_indexes[0],
                preset_item.display_text.casefold(),
            )
            ranked_items.append((ranking_key, preset_item))

        ranked_items.sort(key=lambda item: item[0])
        return [preset_item for _, preset_item in ranked_items]

    @staticmethod
    def _term_matches_prefix(term: str, normalized_prefix: str) -> bool:
        if term.startswith(normalized_prefix):
            return True

        prefix_parts = normalized_prefix.split()
        term_parts = term.split()
        if len(prefix_parts) <= 1 or len(prefix_parts) > len(term_parts):
            return False

        return all(
            term_part.startswith(prefix_part)
            for prefix_part, term_part in zip(prefix_parts, term_parts)
        )


class HistoryCompletionSource(SearchCompletionSource):
    def __init__(
        self,
        history_items: Optional[Sequence[str]] = None,
    ) -> None:
        self._history_items = list(history_items or [])

    def set_history_items(self, history_items: Sequence[str]) -> None:
        self._history_items = list(history_items)

    def build_entries(
        self,
        search_text: str,
        context: SearchCompletionContext,
    ) -> List[SearchCompletionEntry]:
        normalized_search_text = (
            SearchCompletionParser.normalize_completion_value(search_text)
        )
        if len(normalized_search_text) == 0:
            return []

        entries: List[SearchCompletionEntry] = []
        for history_item in self._history_items:
            normalized_history_item = (
                SearchCompletionParser.normalize_completion_value(history_item)
            )
            if not normalized_history_item.startswith(normalized_search_text):
                continue

            entries.append(
                SearchCompletionEntry(
                    display_text=history_item,
                    insert_text=history_item,
                    replace_mode=SearchCompletionReplaceMode.FULL_TEXT,
                )
            )

        return entries


class SearchCompletionEngine:
    def __init__(
        self,
        sources: Optional[Sequence[SearchCompletionSource]] = None,
    ) -> None:
        self._sources = list(sources or [])

    @classmethod
    def create_default(
        cls,
        history_items: Optional[Sequence[str]] = None,
        preset_items: Optional[Sequence[PresetCompletionItem]] = None,
    ) -> "SearchCompletionEngine":
        return cls(
            sources=[
                PresetCompletionSource(preset_items=preset_items),
                HistoryCompletionSource(history_items=history_items),
            ]
        )

    def set_history_items(self, history_items: Sequence[str]) -> None:
        for source in self._sources:
            if isinstance(source, HistoryCompletionSource):
                source.set_history_items(history_items)

    def build_context(
        self,
        search_text: str,
        cursor_position: Optional[int] = None,
    ) -> SearchCompletionContext:
        return SearchCompletionParser.build_context(
            search_text,
            cursor_position,
        )

    def build_entries(
        self,
        search_text: str,
        cursor_position: Optional[int],
    ) -> Tuple[SearchCompletionContext, List[SearchCompletionEntry]]:
        context = self.build_context(search_text, cursor_position)
        entries: List[SearchCompletionEntry] = []
        seen_display_texts = set()

        for source in self._sources:
            for entry in source.build_entries(search_text, context):
                normalized_display_text = entry.display_text.casefold()
                if normalized_display_text in seen_display_texts:
                    continue

                entries.append(entry)
                seen_display_texts.add(normalized_display_text)

        return context, entries

    def apply_completion(
        self,
        search_text: str,
        context: SearchCompletionContext,
        entry: SearchCompletionEntry,
    ) -> str:
        return SearchCompletionParser.apply_completion(
            search_text,
            context,
            entry,
        )


class OsmInfoSearchCompleterModel(QAbstractListModel):
    def __init__(
        self,
        history_items: Optional[Sequence[str]] = None,
        preset_items: Optional[Sequence[PresetCompletionItem]] = None,
        completion_engine: Optional[SearchCompletionEngine] = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._completion_engine = (
            completion_engine
            or SearchCompletionEngine.create_default(
                history_items=history_items,
                preset_items=preset_items,
            )
        )
        if completion_engine is not None and history_items is not None:
            self._completion_engine.set_history_items(history_items)

        self._completion_context = self._completion_engine.build_context("")
        self._entries: List[SearchCompletionEntry] = []

    @property
    def completion_context(self) -> SearchCompletionContext:
        return self._completion_context

    @property
    def completion_engine(self) -> SearchCompletionEngine:
        return self._completion_engine

    def set_history_items(self, history_items: Sequence[str]) -> None:
        self._completion_engine.set_history_items(history_items)

    def set_search_text(
        self,
        search_text: str,
        cursor_position: Optional[int] = None,
    ) -> None:
        completion_context, entries = self._completion_engine.build_entries(
            search_text,
            cursor_position,
        )
        self.beginResetModel()
        self._completion_context = completion_context
        self._entries = entries
        self.endResetModel()

    def entry_at(self, row_index: int) -> Optional[SearchCompletionEntry]:
        if row_index < 0 or row_index >= len(self._entries):
            return None

        return self._entries[row_index]

    def rowCount(self, parent: Optional[QModelIndex] = None) -> int:
        if parent is not None and parent.isValid():
            return 0

        return len(self._entries)

    def data(
        self,
        index: QModelIndex,
        role: int = Qt.ItemDataRole.DisplayRole,
    ):
        if not index.isValid():
            return None

        entry = self.entry_at(index.row())
        if entry is None:
            return None

        if role in (
            Qt.ItemDataRole.DisplayRole,
            Qt.ItemDataRole.EditRole,
        ):
            return entry.display_text

        return None


class OsmInfoSearchCompleter(QCompleter):
    def __init__(
        self,
        parent: Optional[QObject] = None,
        completion_engine: Optional[SearchCompletionEngine] = None,
    ) -> None:
        self._search_model = OsmInfoSearchCompleterModel(
            parent=parent,
            completion_engine=completion_engine,
        )
        super().__init__(self._search_model, parent)
        self._search_text = ""
        self._cursor_position = 0
        self.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.setCompletionMode(QCompleter.CompletionMode.PopupCompletion)

    @property
    def search_model(self) -> OsmInfoSearchCompleterModel:
        return self._search_model

    def update_completion_state(
        self,
        search_text: str,
        cursor_position: Optional[int] = None,
    ) -> None:
        self._search_text = search_text
        if cursor_position is None:
            cursor_position = len(search_text)

        self._cursor_position = cursor_position
        self._search_model.set_search_text(search_text, cursor_position)

    def splitPath(self, path: Optional[str]) -> List[str]:
        widget = self.widget()

        if widget is not None:
            search_text, cursor_position = (
                self._widget_text_and_cursor_position(widget)
            )
            self.update_completion_state(
                search_text,
                cursor_position,
            )
            return [self._search_model.completion_context.prefix]

        if path is None:
            path = ""

        self.update_completion_state(path, len(path))
        return [self._search_model.completion_context.prefix]

    def pathFromIndex(self, index) -> str:
        entry = self._search_model.entry_at(index.row())
        if entry is None:
            return self._search_text

        return self._search_model.completion_engine.apply_completion(
            self._search_text,
            self._search_model.completion_context,
            entry,
        )

    @staticmethod
    def _widget_text_and_cursor_position(widget: QWidget) -> Tuple[str, int]:
        if isinstance(widget, QComboBox):
            line_edit = widget.lineEdit()
        elif isinstance(widget, QLineEdit):
            line_edit = widget
        else:
            raise TypeError("Unsupported widget type for search completer")

        return line_edit.text(), line_edit.cursorPosition()
