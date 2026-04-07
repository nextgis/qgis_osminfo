from pathlib import Path
from typing import Optional, Union

from qgis.PyQt.QtCore import QSize
from qgis.PyQt.QtGui import QIcon, QMovie
from qgis.PyQt.QtWidgets import QToolButton, QWidget


class LoadingToolButton(QToolButton):
    """Display an animated icon while a tool button is busy.

    Replace the current button icon with frames from a movie and restore
    the original icon when the loading state ends.
    """

    def __init__(
        self,
        animation_path: Union[str, Path],
        parent: Optional[QWidget] = None,
    ):
        """Initialize the loading button.

        :param animation_path: Point to the movie file used for animation.
        :param parent: Own the button widget.
        """
        super().__init__(parent)

        self._default_icon = QIcon()
        self._movie = QMovie(str(animation_path))

        self._movie.frameChanged.connect(self._update_icon)

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

        self.setIcon(self._default_icon)

    def _update_icon(self) -> None:
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
