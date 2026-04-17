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

from datetime import datetime, timezone
from typing import Optional

from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtWidgets import QFrame, QLabel, QVBoxLayout, QWidget

from osminfo.core.utils import utm_tags


class NextGisBannerWidget(QFrame):
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
        utm = utm_tags("banner", utm_campaign=campaign)

        info = {
            "constant": self.tr(
                '<a href="https://data.nextgis.com/?{utm}">'
                "Download geodata</a> for your project"
            ).format(utm=utm),
            "black-friday25": self.tr(
                '<a href="https://data.nextgis.com/?{utm}">'
                "Fresh geodata</a> for your project <b>(50% off!)</b>"
            ).format(utm=utm),
        }
        icon = {
            "constant": ":/plugins/osminfo/icons/news.png",
            "black-friday25": ":/plugins/osminfo/icons/fire.png",
        }

        html = f"""
            <html>
            <head></head>
            <body>
                <center>
                    <table>
                        <tr>
                            <td><img src=\"{icon[campaign]}\"></td>
                            <td>&nbsp;{info[campaign]}</td>
                        </tr>
                    </table>
                </center>
            </body>
            </html>
        """
        self._label.setText(html)

    def _campaign_name(self) -> str:
        black_friday_start = datetime(
            year=2025,
            month=12,
            day=1,
            hour=6,
            minute=1,
            tzinfo=timezone.utc,
        ).timestamp()
        black_friday_finish = datetime(
            year=2025,
            month=12,
            day=6,
            hour=5,
            minute=59,
            tzinfo=timezone.utc,
        ).timestamp()
        now = datetime.now().timestamp()

        is_black_friday = black_friday_start <= now <= black_friday_finish
        return "black-friday25" if is_black_friday else "constant"
