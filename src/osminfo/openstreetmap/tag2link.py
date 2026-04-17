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

import json
import re
from pathlib import Path
from typing import Dict, Iterable, List, NamedTuple, Optional, Tuple
from urllib.parse import quote


class TagLink(NamedTuple):
    title: str
    url: str


class TagLinkResolver:
    """Resolve OSM tag values into external links.

    Port the relevant link resolution rules from the
    openstreetmap-website Ruby code into Python and expose a compact
    API that returns immutable link tuples.

    The original sources are available at:
    https://github.com/openstreetmap/openstreetmap-website

    :ivar _secondary_wikipedia_pattern: Match secondary Wikipedia tag keys.
    :ivar _secondary_wikidata_pattern: Match secondary Wikidata tag keys.
    :ivar _wikipedia_key_pattern: Match language-specific Wikipedia keys.
    :ivar _wikipedia_value_pattern: Match embedded language prefixes in values.
    :ivar _wikidata_single_pattern: Match a single Wikidata identifier.
    :ivar _wikidata_multiple_pattern: Match multiple Wikidata identifiers.
    :ivar _wikimedia_commons_pattern: Match Wikimedia Commons references.
    :ivar _http_pattern: Match absolute HTTP or HTTPS URLs.
    :ivar _phone_pattern: Match telephone numbers accepted for tel links.
    :ivar _dictionary_url_pattern: Match supported dictionary URL templates.
    :ivar _email_keys: Store tag keys that may contain email addresses.
    """

    _secondary_wikipedia_pattern = re.compile(
        r"^(architect|artist|brand|buried|flag|genus|manufacturer|model|"
        r"name:etymology|network|operator|species|subject):wikipedia$"
    )
    _secondary_wikidata_pattern = re.compile(
        r"^(architect|artist|brand|buried|flag|genus|manufacturer|model|"
        r"name:etymology|network|operator|species|subject):wikidata$"
    )
    _wikipedia_key_pattern = re.compile(r"^wikipedia:(\S+)$")
    _wikipedia_value_pattern = re.compile(r"^([a-z-]{2,12}):(.+)$", re.I)
    _wikidata_single_pattern = re.compile(r"^[Qq][1-9][0-9]*$")
    _wikidata_multiple_pattern = re.compile(
        r"^[Qq][1-9][0-9]*(\s*;\s*[Qq][1-9][0-9]*)*$"
    )
    _wikimedia_commons_pattern = re.compile(r"^(file|category):([^#]+)", re.I)
    _http_pattern = re.compile(r"^https?://", re.I)
    _phone_pattern = re.compile(
        r"^\s*\+[\d\s()/.-]{6,25}\s*(;\s*\+[\d\s()/.-]{6,25}\s*)*$"
    )
    _dictionary_url_pattern = re.compile(r"^https?://[^$]", re.I)
    _email_keys = frozenset({"email", "contact:email"})

    def __init__(self) -> None:
        self.__cache: Dict[Tuple[str, str, str], Tuple[TagLink, ...]] = {}
        self.__dictionary: Optional[Dict[str, str]] = None

    def resolve(
        self, key: str, value: str, locale: str = "en"
    ) -> Tuple[TagLink, ...]:
        """Resolve links for a tag key and value pair.

        :param key: Tag key to inspect.
        :param value: Raw tag value to convert into links.
        :param locale: Locale used in generated wiki-related URLs.
        :return: Immutable collection of resolved links.
        """

        cache_key = (key, value, locale or "en")
        cached_links = self.__cache.get(cache_key)
        if cached_links is not None:
            return cached_links

        resolved_links = self._resolve_uncached(*cache_key)
        self.__cache[cache_key] = resolved_links
        return resolved_links

    def _resolve_uncached(
        self, key: str, value: str, locale: str
    ) -> Tuple[TagLink, ...]:
        if not key or not value:
            return tuple()

        wikipedia_links = self._wikipedia_links(key, value, locale)
        if wikipedia_links:
            return wikipedia_links

        wikidata_links = self._wikidata_links(key, value, locale)
        if wikidata_links:
            return wikidata_links

        wikimedia_commons_link = self._wikimedia_commons_link(
            key, value, locale
        )
        if wikimedia_commons_link is not None:
            return (wikimedia_commons_link,)

        email_link = self._email_link(key, value)
        if email_link is not None:
            return (email_link,)

        telephone_links = self._telephone_links(value)
        if telephone_links:
            return telephone_links

        generic_links = self._generic_tag_links(key, value)
        if generic_links:
            return generic_links

        return self._direct_url_links(value)

    def _dictionary(self) -> Dict[str, str]:
        if self.__dictionary is None:
            self.__dictionary = self._load_dictionary()

        return self.__dictionary

    def _load_dictionary(self) -> Dict[str, str]:
        dictionary_path = (
            Path(__file__).resolve().parent.parent
            / "resources"
            / "tag2link"
            / "index.json"
        )
        with dictionary_path.open("r", encoding="utf-8") as file_handle:
            raw_data = json.load(file_handle)

        return self._build_dictionary(raw_data)

    def _build_dictionary(
        self, data: Iterable[Dict[str, str]]
    ) -> Dict[str, str]:
        """Build a lookup table from raw tag2link records.

        Normalize the upstream JSON dataset into a mapping from OSM key
        to URL template, skipping entries that are deprecated,
        unsupported, or ambiguous.

        :param data: Raw records loaded from the tag2link dataset.
        :return: Mapping from normalized OSM keys to URL templates.
        """

        grouped_items: Dict[str, List[Dict[str, str]]] = {}
        for item in data:
            rank = item.get("rank")
            source = item.get("source")
            url = item.get("url", "")

            # Keep only entries that may produce user-facing HTTP links.
            # The upstream dataset also contains deprecated definitions,
            # third-party sources, and placeholders that are not usable as
            # link templates in the plugin UI.
            if rank == "deprecated":
                continue
            if source == "wikidata:P3303":
                continue
            if not self._dictionary_url_pattern.match(url):
                continue

            key = item.get("key", "")
            if key.startswith("Key:"):
                key = key[4:]

            # Several dataset rows may describe the same OSM key. Collect
            # them first and defer the final choice to _choose_best_item,
            # which applies the preference rules ported from Ruby.
            grouped_items.setdefault(key, []).append(item)

        result: Dict[str, str] = {}
        for key, items in grouped_items.items():
            selected_item = self._choose_best_item(items)
            if selected_item is None:
                continue

            # Only the URL template is needed at runtime. The rest of the
            # record metadata is used exclusively while resolving conflicts.
            result[key] = selected_item["url"]

        return result

    def _choose_best_item(
        self, items: List[Dict[str, str]]
    ) -> Optional[Dict[str, str]]:
        """Choose the most suitable tag2link record for a single OSM key.

        :param items: Candidate records that describe the same key.
        :return: Selected record or None if the candidates stay ambiguous.
        """

        if len(items) == 0:
            return None

        if len(items) == 1:
            return items[0]

        ranked_items = sorted(
            items,
            key=lambda item: 0 if item.get("rank") == "preferred" else 1,
        )

        unique_items: List[Dict[str, str]] = []
        seen_urls = set()
        for item in ranked_items:
            url = item.get("url")
            if url in seen_urls:
                continue
            seen_urls.add(url)
            unique_items.append(item)

        # Compare only the strongest rank level that is present after URL
        # deduplication. Lower-ranked alternatives are ignored once a better
        # ranked candidate exists.
        top_rank = unique_items[0].get("rank")
        top_items = [
            item for item in unique_items if item.get("rank") == top_rank
        ]

        if len(top_items) == 1:
            return top_items[0]

        grouped_items: Dict[str, List[Dict[str, str]]] = {}
        for item in top_items:
            source = item.get("source", "")
            grouped_items.setdefault(source, []).append(item)

        # More than two distinct sources means there is no clear equivalent
        # to the Ruby helper's fallback logic, so keep the result unresolved.
        if len(grouped_items) > 2:
            return None

        # If each source contributes exactly one top-ranked candidate,
        # prefer osmwiki when present and otherwise keep the first candidate.
        if all(len(values) == 1 for values in grouped_items.values()):
            osm_wiki_items = grouped_items.get("osmwiki:P8")
            if osm_wiki_items:
                return osm_wiki_items[0]
            return top_items[0]

        # If one source produced a single candidate while another produced
        # multiple competing variants, prefer the unambiguous source.
        for values in grouped_items.values():
            if len(values) == 1:
                return values[0]

        return None

    def _wikipedia_links(
        self, key: str, value: str, locale: str
    ) -> Tuple[TagLink, ...]:
        # Some k/v's are wikipedia=http://en.wikipedia.org/wiki/Full%20URL
        if self._http_pattern.match(value):
            return tuple()

        language = self._wikipedia_language_for_key(key)
        if language is None:
            return tuple()

        # Value could be a semicolon-separated list of Wikipedia pages
        links: List[TagLink] = []
        for raw_value in value.split(";"):
            wiki_value = raw_value.strip()
            if len(wiki_value) == 0:
                continue

            # This regex should match Wikipedia language codes, everything
            # from de to zh-classical
            value_match = self._wikipedia_value_pattern.match(wiki_value)
            if value_match is None:
                page_language = language
                title_section = wiki_value
            else:
                page_language = value_match.group(1)
                title_section = value_match.group(2)

            title, separator, section = title_section.partition("#")
            encoded_title = self._wiki_encode(title)
            url = (
                f"https://{page_language}.wikipedia.org/wiki/"
                f"{encoded_title}?uselang={locale}"
            )
            if separator:
                url = f"{url}#{self._wiki_encode(section)}"

            links.append(TagLink(title=wiki_value, url=url))

        return tuple(links)

    def _wikipedia_language_for_key(self, key: str) -> Optional[str]:
        if key == "wikipedia" or self._secondary_wikipedia_pattern.match(key):
            return "en"

        key_match = self._wikipedia_key_pattern.match(key)
        if key_match is None:
            return None

        return key_match.group(1)

    def _wikidata_links(
        self, key: str, value: str, locale: str
    ) -> Tuple[TagLink, ...]:
        # The simple wikidata-tag (this is limited to only one value)
        if key == "wikidata" and self._wikidata_single_pattern.match(value):
            identifier = value.strip()
            return (
                TagLink(
                    title=identifier,
                    url=(
                        "https://www.wikidata.org/entity/"
                        f"{identifier}?uselang={locale}"
                    ),
                ),
            )

        # Key has to be one of the accepted wikidata-tags
        if not self._secondary_wikidata_pattern.match(key):
            return tuple()

        # Value has to be a semicolon-separated list of wikidata-IDs (whitespaces allowed before and after semicolons)
        if not self._wikidata_multiple_pattern.match(value):
            return tuple()

        # Splitting at every semicolon to get a separate hash for each wikidata-ID
        links: List[TagLink] = []
        for raw_identifier in value.split(";"):
            identifier = raw_identifier.strip()
            if len(identifier) == 0:
                continue
            links.append(
                TagLink(
                    title=identifier,
                    url=(
                        "https://www.wikidata.org/entity/"
                        f"{identifier}?uselang={locale}"
                    ),
                )
            )

        return tuple(links)

    def _wikimedia_commons_link(
        self, key: str, value: str, locale: str
    ) -> Optional[TagLink]:
        if key != "wikimedia_commons":
            return None

        value_match = self._wikimedia_commons_pattern.match(value.strip())
        if value_match is None:
            return None

        namespace = value_match.group(1)
        title = value_match.group(2)
        url = (
            "https://commons.wikimedia.org/wiki/"
            f"{namespace}:{self._wiki_encode(title)}?uselang={locale}"
        )
        return TagLink(title=value, url=url)

    def _email_link(self, key: str, value: str) -> Optional[TagLink]:
        # Avoid converting conditional tags into emails
        if key not in self._email_keys:
            return None

        # Does the value look like an email? eg "someone@domain.tld"

        email = value.strip()
        if len(email) == 0 or "@" not in email:
            return None

        if email.count("@") != 1:
            return None

        local_part, domain = email.split("@", 1)
        if len(local_part) == 0 or len(domain) < 3 or "." not in domain:
            return None

        return TagLink(title=email, url=f"mailto:{email}")

    def _telephone_links(self, value: str) -> Tuple[TagLink, ...]:
        # Does it look like a global phone number? eg "+1 (234) 567-8901 "
        # or a list of alternate numbers separated by ;
        #
        # Per RFC 3966, this accepts the visual separators -.() within the number,
        # which are displayed and included in the tel: URL, and accepts whitespace,
        # which is displayed but not included in the tel: URL.
        #  (see: http://tools.ietf.org/html/rfc3966#section-5.1.1)
        #
        # Also accepting / as a visual separator although not given in RFC 3966,
        # because it is used as a visual separator in OSM data in some countries.

        if not self._phone_pattern.match(value):
            return tuple()

        links: List[TagLink] = []
        for raw_phone_number in value.split(";"):
            # for display, remove leading and trailing whitespace
            phone_number = raw_phone_number.strip()
            if len(phone_number) == 0:
                continue

            # for tel: URL, remove all whitespace
            # "+1 (234) 567-8901 " -> "tel:+1(234)567-8901"
            phone_no_whitespace = re.sub(r"\s+", "", phone_number)
            links.append(
                TagLink(
                    title=phone_number,
                    url=f"tel:{phone_no_whitespace}",
                )
            )

        return tuple(links)

    def _generic_tag_links(self, key: str, value: str) -> Tuple[TagLink, ...]:
        template = self._dictionary().get(key)
        if template is None:
            return tuple()

        links: List[TagLink] = []
        for raw_value in value.split(";"):
            item_value = raw_value.strip()
            if len(item_value) == 0:
                continue
            if self._http_pattern.match(item_value):
                continue

            url = template.replace("$1", item_value.lstrip("#"))
            links.append(TagLink(title=item_value, url=url))

        return tuple(links)

    def _direct_url_links(self, value: str) -> Tuple[TagLink, ...]:
        links: List[TagLink] = []
        for raw_value in value.split(";"):
            item_value = raw_value.strip()
            if not self._http_pattern.match(item_value):
                continue
            links.append(TagLink(title=item_value, url=item_value))

        return tuple(links)

    def _wiki_encode(self, value: str) -> str:
        return quote(value.replace(" ", "_"), safe="")
