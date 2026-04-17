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

from typing import Optional

from qgis.PyQt.QtCore import (
    QEvent,
    QObject,
    Qt,
    QTimer,
    QUrl,
    pyqtSignal,
    pyqtSlot,
)
from qgis.PyQt.QtGui import QDesktopServices, QKeyEvent
from qgis.PyQt.QtWidgets import QComboBox, QLineEdit, QWidget

from osminfo.overpass.query_builder.wizard import PlaceholderBuilder
from osminfo.search.search_completer_model import OsmInfoSearchCompleter
from osminfo.search.search_history import SearchHistory
from osminfo.ui.icon import qgis_icon
from osminfo.utils import nextgis_domain, utm_tags


class OsmInfoSearchComboBox(QComboBox):
    """A combo box for entering search queries, with support for search history"""

    search_requested = pyqtSignal(str)
    clear_results = pyqtSignal()

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)

        self._open_help_action = None

        self.setToolTip(
            self.tr("Enter a search query. Examples:\n")
            + "- amenity=restaurant\n"
            "- park in Berlin\n"
            "- cafe around 'Eiffel Tower'\n"
            "- highway=bus_stop in Bern\n"
            + self.tr("Use the dropdown to see recent searches.")
        )

        self.setEditable(True)
        self.lineEdit().setClearButtonEnabled(True)

        placeholder_builder = PlaceholderBuilder()
        self.lineEdit().setPlaceholderText(placeholder_builder.build())

        self.__search_completer = OsmInfoSearchCompleter(self.lineEdit())
        self.setCompleter(self.__search_completer)
        self.__search_completer.popup().installEventFilter(self)

        self.lineEdit().textChanged.connect(self._on_text_changed)
        self.lineEdit().cursorPositionChanged.connect(
            lambda _old_position, _new_position: self._update_completer_state()
        )
        self.lineEdit().returnPressed.connect(self._emit_search_requested)

        history_items = SearchHistory().items
        self.addItems(history_items)
        self.__search_completer.search_model.set_history_items(history_items)

        self.lineEdit().clear()
        self._update_completer_state()

    def keyPressEvent(self, e: Optional[QKeyEvent]) -> None:
        if e.key() not in (
            Qt.Key.Key_Up,
            Qt.Key.Key_Down,
        ):
            return super().keyPressEvent(e)

        if len(self.search_text) == 0 and self.count() > 0:
            self.showPopup()
            e.accept()
            return

        return super().keyPressEvent(e)

    def eventFilter(  # pyright: ignore[reportIncompatibleMethodOverride]
        self, watched: Optional[QObject], event: Optional[QEvent]
    ) -> bool:
        if self._should_accept_completion_on_tab(watched, event):
            self._accept_current_completion()
            event.accept()
            return True

        return super().eventFilter(watched, event)

    @property
    def search_text(self) -> str:
        return self.currentText().strip()

    @search_text.setter
    def search_text(self, search_text: str) -> None:
        self.blockSignals(True)
        self.setCurrentText(search_text.strip())
        self.blockSignals(False)

    @pyqtSlot()
    def save_current_search(self) -> None:
        search_string = self.currentText().strip()
        if not search_string:
            return

        history = SearchHistory()
        history.add_item(search_string)
        self.clear()
        self.addItems(history.items)
        self.__search_completer.search_model.set_history_items(history.items)
        self._update_completer_state()

    @pyqtSlot()
    def _emit_search_requested(self) -> None:
        search_string = self.currentText()
        self.search_requested.emit(search_string)

    @pyqtSlot()
    def _on_text_changed(self) -> None:
        self._reset_if_empty()
        self._update_help_action_state()
        self._update_completer_state()

    def _reset_if_empty(self) -> None:
        if not self.search_text:
            self.clear_results.emit()

    def _should_accept_completion_on_tab(
        self, watched: Optional[QObject], event: Optional[QEvent]
    ) -> bool:
        popup = self.__search_completer.popup()
        if watched not in (self.lineEdit(), popup):
            return False

        if event.type() != QEvent.Type.KeyPress:
            return False

        if not isinstance(event, QKeyEvent):
            return False

        if event.key() != Qt.Key.Key_Tab:
            return False

        return popup.isVisible()

    def _accept_current_completion(self) -> None:
        popup = self.__search_completer.popup()
        current_index = popup.currentIndex()
        if not current_index.isValid():
            popup_model = popup.model()
            if popup_model is None or popup_model.rowCount() == 0:
                return

            current_index = popup_model.index(0, 0)

        completion_text = self.__search_completer.pathFromIndex(current_index)
        cursor_position = len(completion_text)

        popup.hide()
        self.lineEdit().setText(completion_text)
        self.lineEdit().setFocus()
        QTimer.singleShot(
            0,
            lambda: self._set_completion_cursor_position(cursor_position),
        )

    def _set_completion_cursor_position(self, cursor_position: int) -> None:
        self.lineEdit().setFocus()
        self.lineEdit().setCursorPosition(cursor_position)

    def _update_completer_state(self) -> None:
        if self.lineEdit().completer().popup().hasFocus():
            return

        self.__search_completer.update_completion_state(
            self.currentText(),
            self.lineEdit().cursorPosition(),
        )

    @pyqtSlot()
    def _update_help_action_state(self) -> None:
        if not len(self.search_text) and self._open_help_action is None:
            self._open_help_action = self.lineEdit().addAction(
                qgis_icon("mActionHelpContents.svg"),
                QLineEdit.ActionPosition.TrailingPosition,
            )
            self._open_help_action.setToolTip(
                self.tr("Open help in the browser")
            )

            self._open_help_action.triggered.connect(
                self._open_help_in_browser
            )

        elif self._open_help_action is not None:
            self._open_help_action.deleteLater()
            self._open_help_action = None

    @pyqtSlot()
    def _open_help_in_browser(self) -> None:
        domain = nextgis_domain("docs")
        utm = utm_tags("search_panel")
        QDesktopServices.openUrl(
            QUrl(f"{domain}/docs_ngqgis/source/osminfo.html?{utm}")
        )
