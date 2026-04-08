from pathlib import Path
from typing import Optional, Union

from qgis.PyQt.QtCore import QEvent, QSize, Qt, pyqtSignal
from qgis.PyQt.QtGui import QEnterEvent, QIcon, QMouseEvent, QMovie
from qgis.PyQt.QtWidgets import QToolButton, QWidget


class LoadingToolButton(QToolButton):
    """Display an animated icon while a tool button is busy.

    Replace the current button icon with frames from a movie and restore
    the original icon when the loading state ends.
    """

    cancelRequested = pyqtSignal()

    def __init__(
        self,
        animation_path: Union[str, Path],
        icon: Optional[QIcon] = None,
        cancel_icon: Optional[QIcon] = None,
        parent: Optional[QWidget] = None,
    ):
        """Initialize the loading button.

        :param animation_path: Point to the movie file used for animation.
        :param parent: Own the button widget.
        """
        super().__init__(parent)

        self._default_icon = QIcon() if icon is None else QIcon(icon)
        self.setIcon(self._default_icon)
        self._cancel_icon = (
            QIcon() if cancel_icon is None else QIcon(cancel_icon)
        )
        self._is_hovered = False
        self._is_loading = False
        self._movie = QMovie(str(animation_path))

        self._movie.frameChanged.connect(self._update_icon)

    def cancelIcon(self) -> QIcon:
        """Get the icon shown when the button is hovered while loading.

        :return: The cancel icon.
        """

        return QIcon(self._cancel_icon)

    def setCancelIcon(self, icon: QIcon) -> None:
        """Set the icon shown when the button is hovered while loading.

        :param icon: The cancel icon to apply.
        """

        self._cancel_icon = QIcon(icon)

    def start(self) -> None:
        """Start showing the loading animation.

        Preserve the current icon, scale the movie to the button icon size,
        and replace the icon with animated frames when the movie is valid.
        """
        if self._movie.fileName() == "":
            return

        if not self._movie.isValid():
            return

        if self._movie.state() == QMovie.MovieState.Running:
            return

        self._default_icon = self.icon()
        self._is_loading = True

        icon_size = self.iconSize()
        if not icon_size.isValid():
            icon_size = self.sizeHint()

        if icon_size.isValid():
            self._movie.setScaledSize(icon_size)

        self._movie.start()
        self._update_icon()

    def stop(self) -> None:
        """Stop showing the loading animation.

        Restore the icon that was displayed before the animation started.
        """
        if self._movie.state() != QMovie.MovieState.NotRunning:
            self._movie.stop()

        self._is_loading = False
        self.setIcon(self._default_icon)

    def enterEvent(self, a0: Optional[QEnterEvent]) -> None:
        self._is_hovered = True
        if self._is_loading and not self._cancel_icon.isNull():
            self.setIcon(self._cancel_icon)

        super().enterEvent(a0)

    def leaveEvent(self, a0: Optional[QEvent]) -> None:
        self._is_hovered = False
        if self._is_loading:
            self._update_icon()

        super().leaveEvent(a0)

    def mouseReleaseEvent(self, a0: Optional[QMouseEvent]) -> None:
        if a0 is None:
            return

        if self._is_loading and a0.button() == Qt.MouseButton.LeftButton:
            a0.accept()
            if self._cancel_icon.isNull():
                return

            if not self.isEnabled() or not self.rect().contains(a0.pos()):
                return

            self.cancelRequested.emit()
            return

        super().mouseReleaseEvent(a0)

    def _update_icon(self) -> None:
        if self._is_hovered and not self._cancel_icon.isNull():
            self.setIcon(self._cancel_icon)
            return

        current_pixmap = self._movie.currentPixmap()
        if current_pixmap.isNull():
            return

        self.setIcon(QIcon(current_pixmap))

    def setIconSize(self, size: QSize) -> None:  # noqa: N802
        """Resize the button icon and animation frames.

        :param size: Define the icon size to apply.
        """
        super().setIconSize(size)

        if not size.isValid():
            return

        self._movie.setScaledSize(size)
