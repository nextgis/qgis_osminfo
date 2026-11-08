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

"""Subset of the QuickMapServices NextGIS UI decorator.

The banner uses only these stable fallback design tokens. The upstream theme
file is optional and unavailable in packaged QuickMapServices releases.
"""

from dataclasses import dataclass
from enum import Enum

from qgis.PyQt.QtGui import QColor, QPalette


@dataclass(frozen=True)
class NextgisToken:
    """Store a fallback UI design token."""

    fallback: object


class NextgisBrandColor(Enum):
    """Represent NextGIS brand color fallbacks."""

    DEFAULT = NextgisToken("#0c65af")
    HOVER = NextgisToken("#0952a5")
    ACTIVE = NextgisToken("#063f80")
    ACCENT = NextgisToken("#0070c5")
    ON_BRAND = NextgisToken("#ffffff")


class NextgisRadius(Enum):
    """Represent NextGIS corner-radius fallbacks."""

    BUTTON = NextgisToken(4)


class NextgisSpacing(Enum):
    """Represent NextGIS spacing fallbacks."""

    SM = NextgisToken(8)
    LG = NextgisToken(16)


class NextgisSize(Enum):
    """Represent NextGIS control-size fallbacks."""

    CONTROL_COMPACT = NextgisToken(32)


def mix_colors(
    first_color: QColor,
    second_color: QColor,
    factor: float,
) -> QColor:
    """Mix two colors by a clamped factor."""

    clamped_factor = max(0.0, min(1.0, factor))
    inverse_factor = 1.0 - clamped_factor

    return QColor(
        round(
            first_color.red() * inverse_factor
            + second_color.red() * clamped_factor
        ),
        round(
            first_color.green() * inverse_factor
            + second_color.green() * clamped_factor
        ),
        round(
            first_color.blue() * inverse_factor
            + second_color.blue() * clamped_factor
        ),
        round(
            first_color.alpha() * inverse_factor
            + second_color.alpha() * clamped_factor
        ),
    )


class NextgisDecorator:
    """Provide the QuickMapServices button design-token interface."""

    @classmethod
    def brand_color(
        cls,
        color: NextgisBrandColor = NextgisBrandColor.DEFAULT,
    ) -> QColor:
        """Return a NextGIS brand color."""

        return QColor(str(color.value.fallback))

    @classmethod
    def brand_hover_color(cls) -> QColor:
        """Return the NextGIS hover color."""

        return cls.brand_color(NextgisBrandColor.HOVER)

    @classmethod
    def brand_active_color(cls) -> QColor:
        """Return the NextGIS pressed color."""

        return cls.brand_color(NextgisBrandColor.ACTIVE)

    @classmethod
    def brand_on_color(cls) -> QColor:
        """Return the foreground color for brand backgrounds."""

        return cls.brand_color(NextgisBrandColor.ON_BRAND)

    @classmethod
    def system_button_color(cls, palette: QPalette) -> QColor:
        """Return the system button color from a palette."""

        return QPalette(palette).color(QPalette.ColorRole.Button)

    @classmethod
    def spacing(cls, spacing: NextgisSpacing) -> int:
        """Return a spacing token in pixels."""

        return int(spacing.value.fallback)

    @classmethod
    def radius(cls, radius: NextgisRadius) -> int:
        """Return a radius token in pixels."""

        return int(radius.value.fallback)

    @classmethod
    def size(cls, size: NextgisSize) -> int:
        """Return a size token in pixels."""

        return int(size.value.fallback)

    @classmethod
    def as_rgba(cls, color: QColor) -> str:
        """Return a CSS rgba color string."""

        return (
            f"rgba({color.red()}, {color.green()}, {color.blue()}, "
            f"{color.alphaF():.3f})"
        )
