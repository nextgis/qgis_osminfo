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
from typing import Dict, Iterable, Optional, Tuple

from qgis.core import QgsApplication

from osminfo.openstreetmap.preset_repository import (
    PresetDefinition,
    PresetRepository,
)

STRONG_NAME_FIELDS = (
    "name:{locale}",
    "name",
    "official_name:{locale}",
    "official_name",
    "short_name:{locale}",
    "short_name",
)

MEDIUM_NAME_FIELDS = (
    "brand:{locale}",
    "brand",
    "operator:{locale}",
    "operator",
    "network:{locale}",
    "network",
)

WEAK_NAME_FIELDS = (
    "ref",
    "local_ref",
)

NAME_FIELDS = STRONG_NAME_FIELDS + MEDIUM_NAME_FIELDS + WEAK_NAME_FIELDS

FALLBACK_TYPE_KEYS = (
    "amenity",
    "shop",
    "tourism",
    "leisure",
    "historic",
    "office",
    "emergency",
    "healthcare",
    "building",
    "highway",
    "railway",
    "public_transport",
    "route",
    "man_made",
    "landuse",
    "natural",
    "waterway",
    "place",
    "boundary",
)

DETAIL_PRIORITIES = {
    ("route", None): ("ref", "network", "operator", "brand"),
    ("boundary", "postal_code"): ("postal_code", "note", "ref"),
    ("highway", "bus_stop"): (
        "ref",
        "local_ref",
        "network",
        "operator",
    ),
    ("public_transport", "platform"): (
        "ref",
        "local_ref",
        "network",
        "operator",
    ),
    ("amenity", "restaurant"): (
        "cuisine",
        "brand",
        "operator",
        "ref",
    ),
    ("amenity", "cafe"): ("cuisine", "brand", "operator", "ref"),
    ("amenity", "fast_food"): (
        "cuisine",
        "brand",
        "operator",
        "ref",
    ),
    ("amenity", "place_of_worship"): (
        "denomination",
        "religion",
        "operator",
        "ref",
    ),
    ("building", "church"): (
        "denomination",
        "religion",
        "operator",
        "ref",
    ),
}

GENERIC_DETAIL_PRIORITY = (
    "ref",
    "brand",
    "operator",
    "network",
    "cuisine",
    "denomination",
    "religion",
)

DETAIL_SUFFIXES = {
    "cuisine": "cuisine",
}


@dataclass(frozen=True)
class _TypeInfo:
    label: Optional[str]
    tag_key: Optional[str]
    tag_value: Optional[str]


@dataclass(frozen=True)
class _NameInfo:
    key: Optional[str]
    value: Optional[str]
    quality: Optional[str]


@dataclass(frozen=True)
class _DetailInfo:
    key: Optional[str]
    value: Optional[str]


class OsmElementTitleBuilder:
    def __init__(
        self,
        locale_name: str = "en",
        repository: Optional[PresetRepository] = None,
    ) -> None:
        self._locale_name = locale_name or "en"
        self._repository = repository or PresetRepository(
            locale_name=self._locale_name
        )
        self._presets = self._load_presets()

    def build(
        self,
        tags: Dict[str, str],
        osm_id: int,
        geometry_type: Optional[str] = None,
    ) -> str:
        type_info = self._resolve_type(tags, geometry_type)
        best_name = self._best_name(tags)
        short_address = self._short_address(tags)
        best_detail = self._best_detail(
            tags,
            type_info,
            best_name.key,
            best_name.value,
        )

        if (
            best_name.quality == "strong"
            and best_name.value is not None
            and type_info.label is not None
        ):
            if self._name_contains_type(best_name.value, type_info.label):
                return best_name.value

            return f"{best_name.value} · {type_info.label}"

        if best_name.quality == "strong" and best_name.value is not None:
            return best_name.value

        if best_name.quality == "medium" and best_name.value is not None:
            if short_address is not None:
                return f"{best_name.value} · {short_address}"

        if type_info.label is not None and short_address is not None:
            return f"{type_info.label} · {short_address}"

        if (
            type_info.label is not None
            and best_detail.value is not None
            and not (
                best_name.quality == "medium"
                and best_name.value is not None
                and best_detail.key in MEDIUM_NAME_FIELDS
            )
        ):
            return f"{type_info.label} · {best_detail.value}"

        if best_name.quality == "medium" and best_name.value is not None:
            if type_info.label is not None:
                return f"{best_name.value} · {type_info.label}"

            return best_name.value

        if best_name.quality == "weak" and best_name.value is not None:
            if type_info.label is not None:
                return f"{type_info.label} · {best_name.value}"

            return best_name.value

        if short_address is not None:
            return short_address

        if type_info.label is not None:
            return type_info.label

        return f"object #{osm_id}"

    def _load_presets(self) -> Tuple[PresetDefinition, ...]:
        try:
            presets = self._repository.load()
        except Exception:
            return tuple()

        return tuple(
            preset
            for preset in presets.values()
            if preset.searchable is not False and len(preset.tags) > 0
        )

    def _resolve_type(
        self,
        tags: Dict[str, str],
        geometry_type: Optional[str] = None,
    ) -> _TypeInfo:
        preset_type = self._preset_type(tags, geometry_type)
        specialized_boundary_type = self._specialized_boundary_type(
            tags,
            preset_type,
        )
        if specialized_boundary_type is not None:
            return specialized_boundary_type

        if preset_type.label is not None:
            return preset_type

        return self._fallback_type(tags)

    def _specialized_boundary_type(
        self,
        tags: Dict[str, str],
        preset_type: _TypeInfo,
    ) -> Optional[_TypeInfo]:
        boundary_value = self._clean_text(tags.get("boundary"))
        if boundary_value == "administrative":
            boundary_level = self._clean_text(tags.get("admin_level"))

            if boundary_level == "2":
                label = self.tr("country")
            elif preset_type.label is not None:
                label = preset_type.label
            else:
                label = self._normalize_type_label(boundary_value)

            return _TypeInfo(
                label=label,
                tag_key="boundary",
                tag_value=boundary_value,
            )

        if (
            preset_type.tag_key != "type"
            or preset_type.tag_value != "boundary"
        ):
            return None

        if boundary_value is None:
            return None

        return _TypeInfo(
            label=self._normalize_type_label(boundary_value),
            tag_key="boundary",
            tag_value=boundary_value,
        )

    def _preset_type(
        self,
        tags: Dict[str, str],
        geometry_type: Optional[str],
    ) -> _TypeInfo:
        best_match: Optional[Tuple[int, int, int, float, int, _TypeInfo]] = (
            None
        )
        for preset in self._presets:
            if not self._geometry_matches_preset(geometry_type, preset):
                continue

            match = self._match_preset(tags, preset)
            if match is None:
                continue

            exact_matches, wildcard_matches, matched_key = match
            label = self._preset_label(preset)
            if label is None:
                continue

            type_info = _TypeInfo(
                label=label,
                tag_key=matched_key,
                tag_value=tags.get(matched_key) if matched_key else None,
            )
            sort_key = (
                self._type_key_priority(matched_key),
                exact_matches,
                wildcard_matches,
                float(preset.matchScore or 0.0),
                len(preset.tags),
                type_info,
            )
            if best_match is None or sort_key[:-1] > best_match[:-1]:
                best_match = sort_key

        if best_match is None:
            return _TypeInfo(None, None, None)

        return best_match[-1]

    def _match_preset(
        self,
        tags: Dict[str, str],
        preset: PresetDefinition,
    ) -> Optional[Tuple[int, int, Optional[str]]]:
        exact_matches = 0
        wildcard_matches = 0
        matched_key: Optional[str] = None
        for key, value in preset.tags.items():
            actual_value = tags.get(key)
            if actual_value is None:
                return None

            if value == "*":
                wildcard_matches += 1
                matched_key = self._prefer_type_key(matched_key, key)
                continue

            if actual_value != value:
                return None

            exact_matches += 1
            matched_key = self._prefer_type_key(matched_key, key)

        return exact_matches, wildcard_matches, matched_key

    def _preset_label(self, preset: PresetDefinition) -> Optional[str]:
        for value in (preset.nameCased, preset.name):
            if value is None:
                continue

            normalized_value = self._normalize_type_label(value)
            if len(normalized_value) > 0:
                return normalized_value

        return None

    def _fallback_type(self, tags: Dict[str, str]) -> _TypeInfo:
        for key in FALLBACK_TYPE_KEYS:
            value = self._clean_text(tags.get(key))
            if value is None:
                continue

            if key == "route":
                return _TypeInfo("route", key, value)

            if value in ("yes", "true", "1"):
                return _TypeInfo(self._normalize_type_label(key), key, value)

            return _TypeInfo(self._normalize_type_label(value), key, value)

        return _TypeInfo(None, None, None)

    def _type_key_priority(self, key: Optional[str]) -> int:
        if key is None:
            return -1

        try:
            return len(FALLBACK_TYPE_KEYS) - FALLBACK_TYPE_KEYS.index(key)
        except ValueError:
            return 0

    def _prefer_type_key(
        self,
        current_key: Optional[str],
        candidate_key: str,
    ) -> str:
        if current_key is None:
            return candidate_key

        if self._type_key_priority(candidate_key) > self._type_key_priority(
            current_key
        ):
            return candidate_key

        return current_key

    def _best_name(self, tags: Dict[str, str]) -> _NameInfo:
        for raw_key in NAME_FIELDS:
            key = raw_key.format(locale=self._locale_name)
            value = self._clean_text(tags.get(key))
            if value is None:
                continue

            return _NameInfo(key, value, self._name_quality(raw_key))

        return _NameInfo(None, None, None)

    def _short_address(self, tags: Dict[str, str]) -> Optional[str]:
        street = self._clean_text(tags.get("addr:street"))
        house_number = self._clean_text(tags.get("addr:housenumber"))
        place = self._clean_text(tags.get("addr:place"))
        house_name = self._clean_text(tags.get("addr:housename"))

        if street is not None and house_number is not None:
            return f"{street}, {house_number}"

        if place is not None and house_number is not None:
            return f"{place}, {house_number}"

        for value in (house_name, street, place, house_number):
            if value is not None:
                return value

        return None

    def _best_detail(
        self,
        tags: Dict[str, str],
        type_info: _TypeInfo,
        best_name_key: Optional[str],
        best_name: Optional[str],
    ) -> _DetailInfo:
        detail_keys = self._detail_keys(type_info)
        for key in detail_keys:
            value = self._clean_text(tags.get(key))
            if value is None:
                continue

            if best_name_key == key:
                continue

            formatted_value = self._format_detail(key, value)
            if formatted_value is None:
                continue

            if best_name is not None and (
                self._is_equivalent(value, best_name)
                or self._is_equivalent(formatted_value, best_name)
            ):
                continue

            if type_info.label is not None and self._is_equivalent(
                formatted_value,
                type_info.label,
            ):
                continue

            return _DetailInfo(key, formatted_value)

        return _DetailInfo(None, None)

    def _detail_keys(self, type_info: _TypeInfo) -> Iterable[str]:
        if type_info.tag_key is not None:
            tag_specific = DETAIL_PRIORITIES.get(
                (type_info.tag_key, type_info.tag_value)
            )
            if tag_specific is not None:
                return tag_specific

            key_specific = DETAIL_PRIORITIES.get((type_info.tag_key, None))
            if key_specific is not None:
                return key_specific

        return GENERIC_DETAIL_PRIORITY

    def _format_detail(self, key: str, value: str) -> Optional[str]:
        normalized_value = self._detail_value(key, value)
        if normalized_value is None:
            return None

        suffix = DETAIL_SUFFIXES.get(key)
        if suffix is None:
            return normalized_value

        return f"{normalized_value} {suffix}"

    def _detail_value(self, key: str, value: str) -> Optional[str]:
        raw_value = value.split(";", 1)[0].strip()
        if len(raw_value) == 0:
            return None

        if key in ("cuisine", "religion", "denomination"):
            return self._normalize_type_label(raw_value)

        return raw_value

    def _name_contains_type(self, best_name: str, type_label: str) -> bool:
        normalized_name = self._normalize_for_compare(best_name)
        normalized_type = self._normalize_for_compare(type_label)
        type_tokens = tuple(
            token for token in normalized_type.split(" ") if len(token) > 0
        )
        if len(type_tokens) == 0:
            return False

        name_tokens = tuple(
            token for token in normalized_name.split(" ") if len(token) > 0
        )
        return all(token in name_tokens for token in type_tokens)

    def _name_quality(self, raw_key: str) -> Optional[str]:
        if raw_key in STRONG_NAME_FIELDS:
            return "strong"

        if raw_key in MEDIUM_NAME_FIELDS:
            return "medium"

        if raw_key in WEAK_NAME_FIELDS:
            return "weak"

        return None

    def _geometry_matches_preset(
        self,
        geometry_type: Optional[str],
        preset: PresetDefinition,
    ) -> bool:
        if geometry_type is None or len(preset.geometry) == 0:
            return True

        geometry_aliases = {
            "point": ("point", "vertex"),
            "line": ("line",),
            "area": ("area", "relation"),
            "relation": ("relation",),
        }
        allowed_geometries = geometry_aliases.get(
            geometry_type.lower(),
            (geometry_type.lower(),),
        )
        return any(item in allowed_geometries for item in preset.geometry)

    def _is_equivalent(self, left: str, right: str) -> bool:
        return self._normalize_for_compare(
            left
        ) == self._normalize_for_compare(right)

    def _normalize_type_label(self, value: str) -> str:
        normalized_value = value.strip().replace("_", " ")
        normalized_value = normalized_value.replace("/", " ")
        normalized_value = " ".join(normalized_value.split())
        return normalized_value.lower()

    def _normalize_for_compare(self, value: str) -> str:
        normalized_value = self._normalize_type_label(value)
        normalized_value = normalized_value.replace(",", " ")
        normalized_value = normalized_value.replace(".", " ")
        return " ".join(normalized_value.split())

    def _clean_text(self, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None

        stripped_value = value.strip()
        if len(stripped_value) == 0:
            return None

        return stripped_value

    def tr(self, text: str) -> str:
        return QgsApplication.translate(self.__class__.__name__, text)
