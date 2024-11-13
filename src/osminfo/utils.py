import platform
from typing import Union

from qgis.core import QgsApplication
from qgis.PyQt.QtCore import QByteArray, QMimeData
from qgis.PyQt.QtGui import QClipboard


def set_clipboard_data(
    mime_type: str, data: Union[QByteArray, bytes, bytearray], text: str
):
    mime_data = QMimeData()
    mime_data.setData(mime_type, data)
    if len(text) > 0:
        mime_data.setText(text)

    clipboard = QgsApplication.clipboard()
    assert clipboard is not None
    if platform.system() == "Linux":
        selection_mode = QClipboard.Mode.Selection
        clipboard.setMimeData(mime_data, selection_mode)
    clipboard.setMimeData(mime_data, QClipboard.Mode.Clipboard)
