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
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

from qgis.core import QgsApplication

from osminfo.core.exceptions import OsmInfoWizardFreeFormError
from osminfo.utils import qgis_locale


@dataclass(frozen=True)
class PresetReference:
    """Store the source preset referenced by a derived preset.

    Represent the tag key and optional value used to point back to a base iD
    preset definition.

    :ivar key: Referenced tag key.
    :ivar value: Optional referenced tag value.
    """

    key: str
    value: Optional[str] = None

    @classmethod
    def from_mapping(cls, raw_value: object) -> Optional["PresetReference"]:
        if not isinstance(raw_value, dict):
            return None

        key = raw_value.get("key")
        if not isinstance(key, str) or len(key) == 0:
            return None

        value = raw_value.get("value")
        if value is not None and not isinstance(value, str):
            value = str(value)

        return cls(key=key, value=value)


@dataclass(frozen=True)
class PresetLocationSet:
    """Store geographic include and exclude filters for a preset.

    Preserve location-set metadata from the iD tagging schema.

    :ivar exclude: Regions where the preset is unavailable.
    :ivar include: Regions where the preset is explicitly available.
    """

    exclude: List[str] = field(default_factory=list)
    include: List[str] = field(default_factory=list)

    @classmethod
    def from_mapping(cls, raw_value: object) -> Optional["PresetLocationSet"]:
        if not isinstance(raw_value, dict):
            return None

        exclude = raw_value.get("exclude")
        include = raw_value.get("include")
        return cls(
            exclude=cls._string_list(exclude),
            include=cls._string_list(include),
        )

    @staticmethod
    def _string_list(raw_value: object) -> List[str]:
        if not isinstance(raw_value, list):
            return []

        return [item for item in raw_value if isinstance(item, str)]


@dataclass(frozen=True)
class PresetDefinition:
    """Store one preset entry loaded from the iD tagging schema.

    Preserve the fields relevant for free-form wizard resolution and preset
    matching.

    :ivar identifier: Preset identifier from the schema.
    :ivar name: Normalized preset name.
    :ivar nameCased: Display name preserving original casing.
    :ivar terms: Normalized search terms.
    :ivar translated: Whether the preset ships translated labels.
    :ivar fields: Primary preset fields.
    :ivar moreFields: Secondary preset fields.
    :ivar geometry: Geometry kinds supported by the preset.
    :ivar tags: Base tag mapping for the preset.
    :ivar searchable: Whether the preset participates in search.
    :ivar icon: Optional icon identifier.
    :ivar matchScore: Optional iD match score.
    :ivar addTags: Tags added by the preset.
    :ivar removeTags: Tags removed by the preset.
    :ivar reference: Optional reference to another preset.
    :ivar replacement: Optional replacement preset identifier.
    :ivar locationSet: Optional location filter metadata.
    """

    identifier: str
    name: Optional[str] = None
    nameCased: Optional[str] = None
    terms: List[str] = field(default_factory=list)
    translated: bool = False
    fields: List[str] = field(default_factory=list)
    moreFields: List[str] = field(default_factory=list)
    geometry: List[str] = field(default_factory=list)
    tags: Dict[str, str] = field(default_factory=dict)
    searchable: Optional[bool] = True
    icon: Optional[str] = None
    matchScore: Optional[float] = None
    addTags: Dict[str, str] = field(default_factory=dict)
    removeTags: Dict[str, str] = field(default_factory=dict)
    reference: Optional[PresetReference] = None
    replacement: Optional[str] = None
    locationSet: Optional[PresetLocationSet] = None

    @classmethod
    def from_mapping(
        cls,
        identifier: str,
        raw_value: object,
    ) -> "PresetDefinition":
        if not isinstance(raw_value, dict):
            raise TypeError("Preset definition must be a mapping")

        return cls(
            identifier=identifier,
            name=cls._optional_string(raw_value.get("name")),
            nameCased=cls._optional_string(raw_value.get("nameCased")),
            terms=cls._string_list(raw_value.get("terms")),
            translated=bool(raw_value.get("translated", False)),
            fields=cls._string_list(raw_value.get("fields")),
            moreFields=cls._string_list(raw_value.get("moreFields")),
            geometry=cls._string_list(raw_value.get("geometry")),
            tags=cls._string_dict(raw_value.get("tags")),
            searchable=cls._optional_bool(raw_value.get("searchable"), True),
            icon=cls._optional_string(raw_value.get("icon")),
            matchScore=cls._optional_float(raw_value.get("matchScore")),
            addTags=cls._string_dict(raw_value.get("addTags")),
            removeTags=cls._string_dict(raw_value.get("removeTags")),
            reference=PresetReference.from_mapping(raw_value.get("reference")),
            replacement=cls._optional_string(raw_value.get("replacement")),
            locationSet=PresetLocationSet.from_mapping(
                raw_value.get("locationSet")
            ),
        )

    @staticmethod
    def _optional_string(raw_value: object) -> Optional[str]:
        if raw_value is None:
            return None

        if isinstance(raw_value, str):
            return raw_value

        return str(raw_value)

    @staticmethod
    def _optional_bool(
        raw_value: object,
        default_value: Optional[bool],
    ) -> Optional[bool]:
        if raw_value is None:
            return default_value

        if isinstance(raw_value, bool):
            return raw_value

        return bool(raw_value)

    @staticmethod
    def _optional_float(raw_value: object) -> Optional[float]:
        if raw_value is None:
            return None

        if isinstance(raw_value, (int, float)):
            return float(raw_value)

        return None

    @staticmethod
    def _string_list(raw_value: object) -> List[str]:
        if not isinstance(raw_value, list):
            return []

        return [item for item in raw_value if isinstance(item, str)]

    @staticmethod
    def _string_dict(raw_value: object) -> Dict[str, str]:
        if not isinstance(raw_value, dict):
            return {}

        return {
            key: value
            for key, value in raw_value.items()
            if isinstance(key, str) and isinstance(value, str)
        }


class PresetRepository:
    """Load and normalize iD preset definitions for wizard free-form queries.

    Read the preset schema, cache parsed entries, and derive normalized names
    and search terms used by the wizard resolver.
    """

    _cache: Dict[Tuple[str, str, str], Dict[str, PresetDefinition]] = {}

    def __init__(
        self,
        presets_path: Optional[Path] = None,
        translations_path: Optional[Path] = None,
        locale_name: Optional[str] = None,
    ) -> None:
        self._presets_path = (
            presets_path if presets_path is not None else self._default_path()
        )
        self._translations_path = (
            translations_path
            if translations_path is not None
            else self._presets_path.parent / "translations"
        )
        self._locale_name = locale_name

    def load(self) -> Dict[str, PresetDefinition]:
        cache_key = self._cache_key()
        cached_presets = self.__class__._cache.get(cache_key)
        if cached_presets is not None:
            return cached_presets

        try:
            raw_presets = json.loads(
                self._presets_path.read_text(encoding="utf-8")
            )
        except Exception as error:
            raise OsmInfoWizardFreeFormError(
                log_message=f"Failed to load presets file: {error}",
                user_message=self.tr("Failed to load presets file."),
            ) from error

        presets: Dict[str, PresetDefinition] = {}
        try:
            for preset_id, raw_preset in raw_presets.items():
                preset = PresetDefinition.from_mapping(preset_id, raw_preset)
                presets[preset_id] = self._normalize_preset(preset)

            presets = self._apply_translations(presets)
        except Exception as error:
            raise OsmInfoWizardFreeFormError(
                log_message=f"Failed to parse presets file: {error}",
                user_message=self.tr("Failed to parse presets file."),
            ) from error

        self.__class__._cache[cache_key] = presets
        return presets

    def _apply_translations(
        self,
        presets: Dict[str, PresetDefinition],
    ) -> Dict[str, PresetDefinition]:
        translated_presets = self._apply_translation_file(
            presets,
            language="en",
        )

        locale_name = self._resolved_locale_name()
        if locale_name is None:
            return translated_presets

        short_locale_name = locale_name[:2]
        if short_locale_name == "en":
            return translated_presets

        return self._apply_translation_file(
            translated_presets,
            language=locale_name,
        )

    def _apply_translation_file(
        self,
        presets: Dict[str, PresetDefinition],
        language: str,
    ) -> Dict[str, PresetDefinition]:
        translated_entries = self._load_translation_entries(language)
        if translated_entries is None:
            return presets

        translated_presets = dict(presets)
        for preset_id, translation in translated_entries.items():
            preset = translated_presets.get(preset_id)
            if preset is None or not isinstance(translation, dict):
                continue

            translated_presets[preset_id] = self._merge_translation(
                preset,
                translation,
            )

        return translated_presets

    def _load_translation_entries(
        self,
        language: str,
    ) -> Optional[Dict[str, object]]:
        for candidate in self._translation_candidates(language):
            translations_file = self._translations_path / f"{candidate}.json"
            if not translations_file.exists():
                continue

            try:
                raw_translations = json.loads(
                    translations_file.read_text(encoding="utf-8")
                )
            except Exception as error:
                raise OsmInfoWizardFreeFormError(
                    log_message=(
                        "Failed to load preset translations file "
                        f"for {candidate}: {error}"
                    ),
                    user_message=self.tr(
                        "Failed to load preset translations file."
                    ),
                ) from error

            translations = self._translation_payload(
                raw_translations,
                candidate,
            )
            if translations is not None:
                return translations

        return None

    def _translation_payload(
        self,
        raw_translations: object,
        language: str,
    ) -> Optional[Dict[str, object]]:
        if not isinstance(raw_translations, dict):
            return None

        language_payload = None
        for candidate in self._translation_candidates(language):
            candidate_payload = raw_translations.get(candidate)
            if isinstance(candidate_payload, dict):
                language_payload = candidate_payload
                break

        if not isinstance(language_payload, dict):
            return None

        presets_payload = language_payload.get("presets")
        if not isinstance(presets_payload, dict):
            return None

        translated_presets = presets_payload.get("presets")
        if not isinstance(translated_presets, dict):
            return None

        return translated_presets

    def _merge_translation(
        self,
        preset: PresetDefinition,
        translation: Dict[str, object],
    ) -> PresetDefinition:
        display_name = preset.nameCased
        normalized_name = preset.name

        translated_name = translation.get("name")
        if isinstance(translated_name, str):
            stripped_name = translated_name.strip()
            if len(stripped_name) > 0:
                display_name = stripped_name
                normalized_name = self._normalize_label(stripped_name)

        translated_terms = []
        raw_terms = translation.get("terms")
        if isinstance(raw_terms, str):
            translated_terms = [
                self._normalize_label(term) for term in raw_terms.split(",")
            ]

        merged_terms: List[str] = []
        if preset.name is not None:
            merged_terms.append(preset.name)

        merged_terms.extend(translated_terms)
        merged_terms.extend(preset.terms)

        return replace(
            preset,
            name=normalized_name,
            nameCased=display_name,
            terms=self._unique_terms(merged_terms),
            translated=True,
        )

    def _cache_key(self) -> Tuple[str, str, str]:
        return (
            str(self._presets_path),
            str(self._translations_path),
            self._resolved_locale_name() or "",
        )

    def _resolved_locale_name(self) -> Optional[str]:
        if self._locale_name is not None:
            normalized_locale_name = self._locale_name.strip().replace(
                "-", "_"
            )
            return normalized_locale_name or None

        return qgis_locale()

    def _translation_candidates(self, language: str) -> List[str]:
        normalized_language = language.strip()
        if len(normalized_language) == 0:
            return []

        candidates: List[str] = []
        for candidate in (
            normalized_language,
            normalized_language.replace("-", "_"),
            normalized_language.replace("_", "-"),
        ):
            if len(candidate) == 0 or candidate in candidates:
                continue

            candidates.append(candidate)

        # Add short language code candidates for any locale with a region or variant
        for candidate in tuple(candidates):
            short_language = candidate.split("_", 1)[0].split("-", 1)[0]
            if len(short_language) == 0 or short_language in candidates:
                continue

            candidates.append(short_language)

        return candidates

    def _normalize_preset(self, preset: PresetDefinition) -> PresetDefinition:
        normalized_name = self._best_name(preset)
        display_name = self._display_name(preset, normalized_name)
        normalized_terms = self._unique_terms(
            self._build_terms(preset, normalized_name)
        )

        return replace(
            preset,
            name=normalized_name,
            nameCased=display_name,
            terms=normalized_terms,
        )

    def _display_name(
        self,
        preset: PresetDefinition,
        normalized_name: Optional[str],
    ) -> Optional[str]:
        for value in (preset.nameCased, preset.name):
            if value is None:
                continue

            stripped_value = value.strip()
            if len(stripped_value) > 0:
                return stripped_value

        return normalized_name

    def _best_name(
        self,
        preset: PresetDefinition,
    ) -> Optional[str]:
        if preset.name:
            return self._normalize_label(preset.name)

        identifier_tail = preset.identifier.split("/")[-1]
        return self._normalize_label(identifier_tail)

    def _build_terms(
        self,
        preset: PresetDefinition,
        normalized_name: Optional[str],
    ) -> Iterable[str]:
        if normalized_name:
            yield normalized_name

        if preset.nameCased:
            yield self._normalize_label(preset.nameCased)

        for term in preset.terms:
            yield self._normalize_label(term)

        yield self._normalize_label(preset.identifier)
        yield self._normalize_label(preset.identifier.split("/")[-1])

    def _normalize_label(self, value: str) -> str:
        normalized_value = value.strip().lower()
        if normalized_value.startswith("{") and normalized_value.endswith("}"):
            normalized_value = normalized_value[1:-1]
            normalized_value = normalized_value.split("/")[-1]

        normalized_value = normalized_value.replace("_", " ")
        normalized_value = normalized_value.replace("/", " ")
        return normalized_value.strip()

    def _unique_terms(self, values: Iterable[str]) -> List[str]:
        unique_terms: List[str] = []
        for value in values:
            if len(value) == 0:
                continue
            if value in unique_terms:
                continue
            unique_terms.append(value)
        return unique_terms

    def _default_path(self) -> Path:
        return (
            Path(__file__).resolve().parents[1]
            / "resources"
            / "id_tagging_schema"
            / "presets.json"
        )

    @staticmethod
    def tr(message: str) -> str:
        return QgsApplication.translate(PresetRepository.__name__, message)
