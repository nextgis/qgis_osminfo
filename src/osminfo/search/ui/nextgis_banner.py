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

from qgis.PyQt.QtWidgets import QWidget

from osminfo.core.utils import qgis_locale, utm_tags
from osminfo.ui_kit.buttons.news_banner import NewsBannerButton

BLACK_FRIDAY_2026_START = datetime(
    year=2026,
    month=11,
    day=9,
    hour=6,
    minute=0,
    tzinfo=timezone.utc,
)
BLACK_FRIDAY_2026_FINISH = {
    "ru": datetime(
        year=2026,
        month=11,
        day=27,
        hour=21,
        minute=0,
        tzinfo=timezone.utc,
    ),
    "default": datetime(
        year=2026,
        month=11,
        day=28,
        hour=6,
        minute=0,
        tzinfo=timezone.utc,
    ),
}
BLACK_FRIDAY_2026_LANDING_PAGES = {
    "ru": "https://nextgis.ru/extra/black-friday-2026/ru/",
    "en": "https://nextgis.com/extra/black-friday-2026/en/",
}
BLACK_FRIDAY_2026_BANNER_TEXTS = {
    "ru": ("23 – 27 ноября · <b>−50% на данные и подписки</b>",),
    "en": ("Nov 23 – 27 · <b>50% off data and subscriptions</b>",),
    "es": ("23–27 nov. · <b>50% de descuento en datos y suscripciones</b>",),
    "fr": (
        "23 - 27 novembre · <b>50% de reduction sur les données "
        "et les abonnements</b>",
        "23–27 nov. · <b>Données et abonnements à −50 %</b>",
    ),
    "bg": ("23 – 27 ноември · <b>50% отстъпка за данни и абонаменти</b>",),
    "cs": ("23. – 27. listopadu · <b>50% sleva na data a předplatné</b>",),
    "de": ("23. – 27. Nov. · <b>50 % Rabatt auf Daten und Abonnements</b>",),
    "it": ("23 – 27 nov. · <b>50% di sconto su dati e abbonamenti</b>",),
    "ja": (
        "11月23日～27日 · <b>データプランとサブスクリプションが50％オフ</b>",
    ),
    "zh": ("11月23日至27日 · <b>数据和订阅享五折优惠</b>",),
    "pl": ("23–27 listopada · <b>50% zniżki na dane i subskrypcje</b>",),
    "pt": (
        "23 a 27 de novembro · <b>50% de desconto em dados e assinaturas</b>",
        "23–27 nov. · <b>Dados e assinaturas −50%</b>",
    ),
}


@dataclass(frozen=True)
class _BannerCampaignContent:
    icon_path: str
    message: str
    compact_message: Optional[str]
    url: str


class _BannerCampaign(str, Enum):
    CONSTANT = "constant"
    BLACK_FRIDAY_2026 = "black-friday26"


class NextGisBannerWidget(NewsBannerButton):
    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)

        locale = qgis_locale()
        campaign = self._campaign_name(locale=locale)
        utm = utm_tags("banner", utm_campaign=campaign.value)
        content = self._campaign_content(campaign, locale, utm)
        self.set_banner_html(
            f'<img src="{content.icon_path}">{content.message}',
            content.url,
            content.compact_message,
        )

    def _campaign_content(
        self,
        campaign: _BannerCampaign,
        locale: str,
        utm: str,
    ) -> _BannerCampaignContent:
        if campaign == _BannerCampaign.BLACK_FRIDAY_2026:
            banner_locale = (
                locale if locale in BLACK_FRIDAY_2026_BANNER_TEXTS else "en"
            )
            texts = BLACK_FRIDAY_2026_BANNER_TEXTS.get(
                banner_locale,
                BLACK_FRIDAY_2026_BANNER_TEXTS["en"],
            )
            full_text = texts[0]
            compact_text = texts[1] if len(texts) > 1 else None
            landing_locale = "ru" if locale == "ru" else "en"
            landing_url = BLACK_FRIDAY_2026_LANDING_PAGES[landing_locale]

            return _BannerCampaignContent(
                icon_path=":/plugins/osminfo/icons/fire.png",
                message=full_text,
                compact_message=compact_text,
                url=f"{landing_url}?{utm}",
            )

        return _BannerCampaignContent(
            icon_path=":/plugins/osminfo/icons/news.png",
            message=self.tr("<b>Download geodata</b> for your project"),
            compact_message=None,
            url=f"https://data.nextgis.com/?{utm}",
        )

    def _campaign_name(
        self,
        now: Optional[datetime] = None,
        locale: Optional[str] = None,
    ) -> _BannerCampaign:
        if now is None:
            now = datetime.now(timezone.utc)
        if locale is None:
            locale = qgis_locale()

        finish = BLACK_FRIDAY_2026_FINISH.get(
            locale,
            BLACK_FRIDAY_2026_FINISH["default"],
        )
        is_black_friday = BLACK_FRIDAY_2026_START <= now < finish
        if is_black_friday:
            return _BannerCampaign.BLACK_FRIDAY_2026

        return _BannerCampaign.CONSTANT
