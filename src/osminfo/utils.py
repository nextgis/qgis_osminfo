import platform
from typing import Union

from qgis.core import QgsApplication, QgsSettings
from qgis.PyQt.QtCore import QByteArray, QLocale, QMimeData
from qgis.PyQt.QtGui import QClipboard


def set_clipboard_data(
    mime_type: str, data: Union[QByteArray, bytes, bytearray], text: str
) -> None:
    """Sets the given data to the system clipboard

    :param mime_type: The MIME type of the data.
    :param data: The data to set in the clipboard, as a QByteArray or bytes-like object.
    :param text: Optional text to set in the clipboard alongside the data.
    """
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


def human_readable_size(size_in_kb: float) -> str:
    """Converts a file size in kilobytes to a human-readable format.
    :param size_in_kb: Size in kilobytes.
    :type size_in_kb: float
    :returns: Human-readable size string.
    :rtype: str
    """
    units = [
        QgsApplication.translate("SizeUnits", "KiB"),
        QgsApplication.translate("SizeUnits", "MiB"),
        QgsApplication.translate("SizeUnits", "GiB"),
        QgsApplication.translate("SizeUnits", "TiB"),
    ]
    size = size_in_kb
    unit_index = 0
    while size > 1024 and unit_index < len(units) - 1:
        size /= 1024
        unit_index += 1
    precision = 2 if size < 10 else 1
    return f"{size:.{precision}f} {units[unit_index]}"


def qgis_locale() -> str:
    """Returns the current QGIS locale code"""
    override_locale = QgsSettings().value(
        "locale/overrideFlag", defaultValue=False, type=bool
    )
    if not override_locale:
        locale_full_name = QLocale.system().name()
    else:
        locale_full_name = QgsSettings().value("locale/userLocale", "")
    locale = locale_full_name[0:2].lower()

    return locale if locale.lower() != "c" else "en"
