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

"""Primary buttons derived from the QuickMapServices UI kit."""

from typing import Optional

from qgis.PyQt.QtGui import QPalette
from qgis.PyQt.QtWidgets import QWidget

from osminfo.ui_kit.buttons.animated import (
    AnimatedButtonBase,
    ButtonVisualState,
)
from osminfo.ui_kit.graphics.decorator import (
    NextgisBrandColor,
    NextgisDecorator,
    mix_colors,
)


class PrimaryButton(AnimatedButtonBase):
    """Show the primary NextGIS action button."""

    def __init__(
        self,
        text: str = "",
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(text, parent)

    def _normal_state(self) -> ButtonVisualState:
        color = NextgisDecorator.brand_color()

        return ButtonVisualState(
            background=color,
            border=color,
            text=NextgisDecorator.brand_on_color(),
        )

    def _hover_state(self) -> ButtonVisualState:
        hover_color = NextgisDecorator.brand_hover_color()

        return ButtonVisualState(
            background=hover_color,
            border=hover_color,
            text=NextgisDecorator.brand_on_color(),
        )

    def _pressed_state(self) -> ButtonVisualState:
        color = NextgisDecorator.brand_active_color()

        return ButtonVisualState(
            background=color,
            border=color,
            text=NextgisDecorator.brand_on_color(),
        )

    def _disabled_state(self) -> ButtonVisualState:
        palette = QPalette(self.palette())
        base_color = NextgisDecorator.system_button_color(palette)
        disabled_color = mix_colors(
            NextgisDecorator.brand_color(NextgisBrandColor.DEFAULT),
            base_color,
            0.50,
        )
        text_color = mix_colors(
            NextgisDecorator.brand_on_color(),
            disabled_color,
            0.40,
        )

        return ButtonVisualState(
            background=disabled_color,
            border=disabled_color,
            text=text_color,
        )
