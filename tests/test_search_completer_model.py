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

from typing import Any

from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtGui import QKeyEvent
from qgis.PyQt.QtWidgets import QApplication

import osminfo.search.search_completer_model as search_completer_model
from osminfo.search.search_completer_model import (
    HistoryCompletionSource,
    OsmInfoSearchCompleter,
    PresetCompletionItem,
    PresetCompletionSource,
    SearchCompletionEngine,
    SearchCompletionReplaceMode,
)
from osminfo.search.search_history import SearchHistory
from osminfo.search.ui.search_combobox import OsmInfoSearchComboBox


def _create_completion_engine(
    history_items,
    preset_items,
) -> SearchCompletionEngine:
    return SearchCompletionEngine(
        sources=[
            PresetCompletionSource(preset_items=preset_items),
            HistoryCompletionSource(history_items=history_items),
        ]
    )


def test_completion_entries_prioritize_presets_before_history() -> None:
    completion_engine = _create_completion_engine(
        history_items=["restaurant in berlin"],
        preset_items=[
            PresetCompletionItem(
                display_text="Restaurant",
                terms=("restaurant", "food"),
            ),
            PresetCompletionItem(
                display_text="Rest Area",
                terms=("rest area",),
            ),
        ],
    )
    completion_context, entries = completion_engine.build_entries(
        search_text="rest",
        cursor_position=4,
    )

    assert completion_context.allow_preset_suggestions is True
    assert [entry.display_text for entry in entries] == [
        "Rest Area",
        "Restaurant",
        "restaurant in berlin",
    ]
    assert [entry.replace_mode for entry in entries] == [
        SearchCompletionReplaceMode.FRAGMENT,
        SearchCompletionReplaceMode.FRAGMENT,
        SearchCompletionReplaceMode.FULL_TEXT,
    ]


def test_completion_entries_skip_duplicate_history_items() -> None:
    completion_engine = _create_completion_engine(
        history_items=["Restaurant", "restaurant in berlin"],
        preset_items=[
            PresetCompletionItem(
                display_text="Restaurant",
                terms=("restaurant",),
            )
        ],
    )
    completion_context, entries = completion_engine.build_entries(
        search_text="rest",
        cursor_position=4,
    )

    assert completion_context.allow_preset_suggestions is True
    assert [entry.display_text for entry in entries] == [
        "Restaurant",
        "restaurant in berlin",
    ]
    assert [entry.replace_mode for entry in entries] == [
        SearchCompletionReplaceMode.FRAGMENT,
        SearchCompletionReplaceMode.FULL_TEXT,
    ]


def test_completion_entries_skip_presets_after_selector_syntax() -> None:
    completion_engine = _create_completion_engine(
        history_items=["amenity=restaurant in berlin"],
        preset_items=[
            PresetCompletionItem(
                display_text="Restaurant",
                terms=("restaurant",),
            )
        ],
    )
    completion_context, entries = completion_engine.build_entries(
        search_text="amenity=rest",
        cursor_position=len("amenity=rest"),
    )

    assert completion_context.allow_preset_suggestions is False
    assert [entry.display_text for entry in entries] == [
        "amenity=restaurant in berlin"
    ]


def test_completion_entries_allow_presets_after_logical_operator() -> None:
    completion_engine = _create_completion_engine(
        history_items=[],
        preset_items=[
            PresetCompletionItem(
                display_text="Museum",
                terms=("museum",),
            ),
            PresetCompletionItem(
                display_text="Music Venue",
                terms=("music venue",),
            ),
        ],
    )
    completion_context, entries = completion_engine.build_entries(
        search_text="park or mus",
        cursor_position=len("park or mus"),
    )

    assert completion_context.prefix == "mus"
    assert completion_context.allow_preset_suggestions is True
    assert [entry.display_text for entry in entries] == [
        "Museum",
        "Music Venue",
    ]


def test_completion_entries_skip_presets_in_area_clause() -> None:
    completion_engine = _create_completion_engine(
        history_items=["park in berlin"],
        preset_items=[
            PresetCompletionItem(
                display_text="Berlin Park",
                terms=("berlin park",),
            )
        ],
    )
    completion_context, entries = completion_engine.build_entries(
        search_text="park in ber",
        cursor_position=len("park in ber"),
    )

    assert completion_context.prefix == "ber"
    assert completion_context.allow_preset_suggestions is False
    assert [entry.display_text for entry in entries] == ["park in berlin"]


def test_apply_search_completion_quotes_multi_word_preset() -> None:
    completion_engine = _create_completion_engine(
        history_items=[],
        preset_items=[
            PresetCompletionItem(
                display_text="Drinking Water",
                terms=("drinking water",),
            )
        ],
    )
    completion_context, entries = completion_engine.build_entries(
        search_text="drink wa",
        cursor_position=len("drink wa"),
    )

    completed_search = completion_engine.apply_completion(
        "drink wa",
        completion_context,
        entries[0],
    )

    assert completed_search == '"Drinking Water"'


def test_apply_search_completion_closes_open_quote() -> None:
    search_text = 'park or "drink wa'
    completion_engine = _create_completion_engine(
        history_items=[],
        preset_items=[
            PresetCompletionItem(
                display_text="Drinking Water",
                terms=("drinking water",),
            )
        ],
    )
    completion_context, entries = completion_engine.build_entries(
        search_text=search_text,
        cursor_position=len(search_text),
    )

    completed_search = completion_engine.apply_completion(
        search_text,
        completion_context,
        entries[0],
    )

    assert completed_search == 'park or "Drinking Water"'


def test_apply_search_completion_replaces_full_text_for_history() -> None:
    search_text = "rest"
    completion_engine = _create_completion_engine(
        history_items=["restaurant in berlin"],
        preset_items=[],
    )
    completion_context, entries = completion_engine.build_entries(
        search_text=search_text,
        cursor_position=len(search_text),
    )

    completed_search = completion_engine.apply_completion(
        search_text,
        completion_context,
        entries[0],
    )

    assert completed_search == "restaurant in berlin"


def test_history_completion_entries_require_case_sensitive_match() -> None:
    completion_engine = _create_completion_engine(
        history_items=["Building=*"],
        preset_items=[],
    )

    _, entries = completion_engine.build_entries(
        search_text="building=*",
        cursor_position=len("building=*"),
    )

    assert entries == []

    _, entries = completion_engine.build_entries(
        search_text="Building=*",
        cursor_position=len("Building=*"),
    )

    assert [entry.display_text for entry in entries] == ["Building=*"]


def test_split_path_uses_combo_line_edit_state(monkeypatch) -> None:
    class FakeLineEdit:
        def __init__(self, text: str) -> None:
            self._text = text

        def text(self) -> str:
            return self._text

        def cursorPosition(self) -> int:
            return len(self._text)

    class FakeComboBox:
        def __init__(self, line_edit: FakeLineEdit) -> None:
            self._line_edit = line_edit

        def lineEdit(self) -> FakeLineEdit:
            return self._line_edit

    monkeypatch.setattr(search_completer_model, "QLineEdit", FakeLineEdit)
    monkeypatch.setattr(search_completer_model, "QComboBox", FakeComboBox)

    class FakeSearchCompleter(OsmInfoSearchCompleter):
        def widget(self) -> Any:
            return FakeComboBox(FakeLineEdit("park or mus"))

    completer = FakeSearchCompleter()
    completer.search_model.set_history_items([])

    split_path = completer.splitPath(None)

    assert split_path == ["mus"]


def test_return_keeps_user_text_when_history_differs_by_case(qgis_app) -> None:
    del qgis_app

    history = SearchHistory()
    history.clear()

    combo_box = None
    try:
        history.add_item("Building=*")
        combo_box = OsmInfoSearchComboBox()
        combo_box.lineEdit().setText("building=*")

        emitted_values = []
        combo_box.search_requested.connect(emitted_values.append)

        assert combo_box.completer().popup().isVisible() is False

        event = QKeyEvent(
            QKeyEvent.Type.KeyPress,
            Qt.Key.Key_Return,
            Qt.KeyboardModifier.NoModifier,
        )
        combo_box.show()

        assert QApplication.sendEvent(combo_box, event) is True

        assert combo_box.lineEdit().text() == "building=*"
        assert combo_box.currentText() == "building=*"
        assert emitted_values == ["building=*"]
    finally:
        if combo_box is not None:
            combo_box.deleteLater()
        history.clear()
