from pathlib import Path
from typing import Dict, Optional, Union

from qgis.core import QgsApplication
from qgis.PyQt.QtCore import (
    QBuffer,
    QByteArray,
    QFile,
    QIODevice,
    QRectF,
    QSize,
    Qt,
)
from qgis.PyQt.QtGui import QIcon, QPainter, QPixmap
from qgis.PyQt.QtSvg import QSvgRenderer
from qgis.PyQt.QtWidgets import QLabel

from osminfo.core.constants import PACKAGE_NAME
from osminfo.logging import logger

_plugin_path = Path(__file__).parents[1]


def qgis_icon(icon_name: str) -> QIcon:
    """Return a QGIS theme icon by name.

    :param icon_name: Name of the icon.
    :type icon_name: str
    :returns: QIcon instance for the QGIS theme icon.
    :rtype: QIcon
    """
    icon = QgsApplication.getThemeIcon(icon_name)
    if icon.isNull():
        icon = QIcon(f":images/themes/default/{icon_name}")
    if icon.isNull():
        icon = QIcon(f":images/themes/default/propertyicons/{icon_name}")
    return icon


def plugin_icon(
    icon_path: Union[Path, str, None] = None,
    color: Optional[str] = None,
    size: Optional[int] = None,
    replacements: Optional[Dict[str, str]] = None,
) -> QIcon:
    """Return the plugin icon as QIcon.

    :param icon_path: Path or name of the icon file.
    :type icon_path: Union[Path, str, None]
    :param color: Color to apply instead of white fill for SVG icons.
        If None, keep the original fills unchanged.
    :type color: Optional[str]
    :returns: QIcon instance for the plugin icon.
    :rtype: QIcon
    """
    icons_path = _plugin_path / "icons"
    if icon_path is None:
        icon_path = f"{PACKAGE_NAME}_logo.svg"

    result_path: Optional[str] = None
    filesystem_path = icons_path / icon_path
    qrc_path = f":/plugins/{PACKAGE_NAME}/icons/{icon_path}"

    if filesystem_path.exists():
        result_path = str(filesystem_path)
    elif QFile(qrc_path).exists():
        result_path = qrc_path

    if result_path is None:
        logger.warning(f"Icon {icon_path} does not exist")
        return QIcon(str(filesystem_path))

    # Repaint only when needed and only for SVG icons
    if result_path.lower().endswith(".svg") and (
        color is not None or size is not None or replacements is not None
    ):
        return render_svg_icon(
            result_path, color=color, size=size, replacements=replacements
        )

    return QIcon(result_path)


def material_icon(
    name: str, *, color: str = "", size: Optional[int] = None
) -> QIcon:
    """Return a material icon as QIcon, optionally recolored and resized.

    :param name: Name of the material icon (without .svg extension).
    :type name: str
    :param color: Color to apply to the icon (hex string).
    :type color: str
    :param size: Size of the icon in pixels.
    :type size: Optional[int]
    :returns: QIcon instance for the material icon.
    :rtype: QIcon
    :raises FileNotFoundError: If the SVG file is not found.
    :raises ValueError: If the SVG cannot be loaded.
    """
    material_icons_path = _plugin_path / "icons" / "material"

    svg_path = None
    for path in material_icons_path.glob(f"{name}*"):
        if not path.is_file() or not path.suffix.lower() == ".svg":
            continue

        next_char = path.name[len(name)]
        next_next_char = path.name[len(name) + 1]
        if next_char != "." and not next_next_char.isdigit():
            continue

        svg_path = path
        break

    if svg_path is None:
        message = f"SVG file not found: {name}"
        raise FileNotFoundError(message)

    effective_color = color or QgsApplication.palette().text().color().name()
    return render_svg_icon(svg_path, color=effective_color, size=size)


def render_svg_icon(
    svg_path: Union[Path, str],
    *,
    color: Optional[str] = None,
    size: Optional[int] = None,
    replacements: Optional[Dict[str, str]] = None,
) -> QIcon:
    """Render an SVG file into a QIcon with optional recolor and resize.

    :param svg_path: Filesystem path to the SVG file.
    :type svg_path: Path
    :param color: Color to apply instead of white fill. If None, keep the
        original fills unchanged.
    :type color: Optional[str]
    :param size: Output icon size in pixels. If None, use SVG default size.
    :type size: Optional[int]
    :returns: Rendered QIcon.
    :rtype: QIcon
    :raises ValueError: If the SVG cannot be loaded.
    """
    if isinstance(svg_path, Path):
        svg_content = svg_path.read_text(encoding="utf-8")
    else:
        file = QFile(svg_path)
        if not file.open(
            QIODevice.OpenModeFlag.ReadOnly | QIODevice.OpenModeFlag.Text
        ):
            message = f"Failed to open SVG file: {svg_path}"
            raise ValueError(message)
        svg_content = file.readAll().data().decode("utf-8")
        file.close()

    # Replace only pure white fills to preserve multi-colored icons
    if color:
        modified_svg = svg_content.replace('fill="#ffffff"', f'fill="{color}"')
        modified_svg = modified_svg.replace("fill:#ffffff", f"fill:{color}")
    else:
        modified_svg = svg_content

    if replacements:
        for key, value in replacements.items():
            modified_svg = modified_svg.replace(key, value)

    byte_array = QByteArray(modified_svg.encode("utf-8"))
    renderer = QSvgRenderer()
    if not renderer.load(byte_array):
        message = f"Failed to load SVG: {svg_path}"
        raise ValueError(message)

    target_size = renderer.defaultSize() if size is None else QSize(size, size)
    pixmap = QPixmap(target_size)
    pixmap.fill(Qt.GlobalColor.transparent)

    painter = QPainter(pixmap)
    renderer.render(
        painter,
        QRectF(0, 0, target_size.width(), target_size.height()),
    )
    painter.end()

    return QIcon(pixmap)


def draw_icon(label: QLabel, icon: QIcon, *, size: int = 24) -> None:
    """Draw an icon on a QLabel with specified size.

    :param label: QLabel to draw the icon on.
    :type label: QLabel
    :param icon: QIcon to be drawn.
    :type icon: QIcon
    :param size: Size of the icon in pixels.
    :type size: int
    """
    pixmap = icon.pixmap(icon.actualSize(QSize(size, size)))
    label.setPixmap(pixmap)
    label.setAlignment(Qt.AlignmentFlag.AlignCenter)


def icon_to_base64(icon: QIcon, size: Optional[int] = None) -> str:
    """Convert a QIcon to a base64-encoded PNG string.

    :param icon: QIcon to convert.
    :type icon: QIcon
    :param size: Size of the icon in pixels. If None, use 32x32.
    :type size: Optional[int]
    :return: Base64-encoded PNG string of the icon.
    :rtype: str
    """
    icon_size = QSize(32, 32) if size is None else QSize(size, size)
    pixmap = icon.pixmap(icon_size)

    buffer = QByteArray()
    qbuffer = QBuffer(buffer)
    qbuffer.open(QIODevice.OpenModeFlag.WriteOnly)
    pixmap.save(qbuffer, "PNG")
    qbuffer.close()

    data = buffer.toBase64().data()
    if not isinstance(data, str):
        data = data.decode("utf-8")

    return "data:image/png;base64, " + data
