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

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtWidgets import QFrame, QLabel, QVBoxLayout, QWidget

from osminfo.core.utils import utm_tags


@dataclass(frozen=True)
class _BannerCampaignContent:
    icon_path: str
    message_html: str


class _BannerCampaign(str, Enum):
    CONSTANT = "constant"
    BLACK_FRIDAY_2025 = "black-friday25"


class NextGisBannerWidget(QFrame):
    BLACK_FRIDAY_2025_START = datetime(
        year=2025,
        month=12,
        day=1,
        hour=6,
        minute=1,
        tzinfo=timezone.utc,
    )
    BLACK_FRIDAY_2025_FINISH = datetime(
        year=2025,
        month=12,
        day=6,
        hour=5,
        minute=59,
        tzinfo=timezone.utc,
    )

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)

        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setFrameShadow(QFrame.Shadow.Raised)

        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 6, 0, 6)

        self._label = QLabel(self)
        self._label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._label.setOpenExternalLinks(True)
        self._label.setTextFormat(Qt.TextFormat.RichText)
        self._label.setWordWrap(True)
        self._layout.addWidget(self._label)

        self.refresh_content()

    def refresh_content(self) -> None:
        campaign = self._campaign_name()
        utm = utm_tags("banner", utm_campaign=campaign.value)
        content = self._campaign_content(campaign, utm)

        html = f"""
            <html>
            <head></head>
            <body>
                <center>
                    <table>
                        <tr>
                            <td><img src=\"{content.icon_path}\"></td>
                            <td>&nbsp;{content.message_html}</td>
                        </tr>
                    </table>
                </center>
            </body>
            </html>
        """
        self._label.setText(html)

    def _campaign_content(
        self,
        campaign: _BannerCampaign,
        utm: str,
    ) -> _BannerCampaignContent:
        if campaign == _BannerCampaign.BLACK_FRIDAY_2025:
            return _BannerCampaignContent(
                icon_path=":/plugins/osminfo/icons/fire.png",
                message_html=self.tr(
                    '<a href="https://data.nextgis.com/?{utm}">'
                    "Fresh geodata</a> for your project <b>(50% off!)</b>"
                ).format(utm=utm),
            )

        return _BannerCampaignContent(
            icon_path=":/plugins/osminfo/icons/news.png",
            message_html=self.tr(
                '<a href="https://data.nextgis.com/?{utm}">'
                "Download geodata</a> for your project"
            ).format(utm=utm),
        )

    def _campaign_name(self) -> _BannerCampaign:
        now = datetime.now(timezone.utc)
        is_black_friday = (
            self.BLACK_FRIDAY_2025_START
            <= now
            <= self.BLACK_FRIDAY_2025_FINISH
        )
        if is_black_friday:
            return _BannerCampaign.BLACK_FRIDAY_2025

        return _BannerCampaign.CONSTANT
