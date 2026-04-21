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

from random import Random
from typing import Callable, Dict, Optional, Sequence, Tuple, TypeVar

from osminfo.openstreetmap.preset_repository import PresetRepository

ChoiceValue = TypeVar("ChoiceValue")


class PlaceholderBuilder:
    """Generate sample wizard searches for the search input placeholder.

    Assemble valid example queries from curated presets, places, and common
    wizard condition patterns.
    """

    _CITY_NAMES: Tuple[str, ...] = (
        "London",
        "Paris",
        "New York",
        "Mexico City",
        "Rio de Janeiro",
        "Buenos Aires",
        "Cairo",
        "Cape Town",
        "Tokyo",
        "Singapore",
        "Sydney",
        "Auckland",
    )
    _PLACE_NAMES: Tuple[str, ...] = (
        "Eiffel Tower",
        "Statue of Liberty",
        "Taj Mahal",
        "Christ the Redeemer",
        "Colosseum",
        "Pyramids of Giza",
        "Sydney Opera House",
        "Burj Khalifa",
        "Times Square",
        "Marina Bay Sands",
        "CN Tower",
        "Plaza de Mayo",
        "Auckland Sky Tower",
    )
    _OSM_IDS: Tuple[str, ...] = (
        "5013364",
        "1802652184",
        "5305957",
    )
    _PRESET_IDENTIFIERS: Tuple[str, ...] = (
        "amenity/library",
        "amenity/marketplace",
        "tourism/hotel",
        "tourism/museum",
        "tourism/artwork",
        "tourism/viewpoint",
    )
    _FALLBACK_PRESET_NAMES: Tuple[str, ...] = (
        "Library",
        "Marketplace",
        "Hotel",
        "Museum",
        "Artwork",
        "Viewpoint",
    )
    _KEY_VALUE_PAIRS: Tuple[Tuple[str, str], ...] = (
        ("amenity", "library"),
        ("amenity", "marketplace"),
        ("amenity", "bus_station"),
        ("amenity", "charging_station"),
        ("tourism", "artwork"),
        ("tourism", "museum"),
    )
    _READY_EXPRESSIONS: Tuple[str, ...] = (
        "(amenity=library or tourism=museum) and type:node",
        "(amenity=charging_station or amenity=fuel) and type:node",
        "(tourism=artwork or tourism=viewpoint) and type:node",
    )

    def __init__(
        self,
        repository: Optional[PresetRepository] = None,
        random_generator: Optional[Random] = None,
    ) -> None:
        self._repository = repository or PresetRepository()
        self._random = random_generator or Random()
        self._builders: Dict[str, Callable[[], str]] = {
            "preset": self._build_preset,
            "preset_in": self._build_preset_in,
            "preset_around": self._build_preset_around,
            "key_value": self._build_key_value,
            "key_value_in": self._build_key_value_in,
            "expression": self._build_expression,
            "id": self._build_id,
        }

    def build(self, variant: Optional[str] = None) -> str:
        builder_name = variant or self._choose(tuple(self._builders.keys()))
        builder = self._builders.get(builder_name)
        if builder is None:
            raise ValueError(f"Unknown placeholder variant: {builder_name}")
        return builder()

    def _build_preset(self) -> str:
        return self._quote_if_needed(self._choose_preset_name())

    def _build_preset_in(self) -> str:
        preset_name = self._quote_if_needed(self._choose_preset_name())
        city_name = self._quote_if_needed(self._choose(self._CITY_NAMES))
        return f"{preset_name} in {city_name}"

    def _build_preset_around(self) -> str:
        preset_name = self._quote_if_needed(self._choose_preset_name())
        place_name = self._quote_if_needed(self._choose(self._PLACE_NAMES))
        return f"{preset_name} around {place_name}"

    def _build_key_value(self) -> str:
        key, value = self._choose(self._KEY_VALUE_PAIRS)
        return f"{key}={value}"

    def _build_key_value_in(self) -> str:
        key_value_pair = self._build_key_value()
        city_name = self._quote_if_needed(self._choose(self._CITY_NAMES))
        return f"{key_value_pair} in {city_name}"

    def _build_expression(self) -> str:
        return self._choose(self._READY_EXPRESSIONS)

    def _build_id(self) -> str:
        return f"id:{self._choose(self._OSM_IDS)}"

    def _preset_names(self) -> Tuple[str, ...]:
        presets = self._repository.load()
        preset_names = []
        for identifier in self._PRESET_IDENTIFIERS:
            preset = presets.get(identifier)
            if preset is None:
                continue

            display_name = preset.nameCased or preset.name
            if display_name is None:
                continue

            preset_names.append(display_name)

        if len(preset_names) == 0:
            return self._FALLBACK_PRESET_NAMES

        return tuple(preset_names)

    def _choose_preset_name(self) -> str:
        return self._choose(self._preset_names())

    def _choose(
        self,
        values: Sequence[ChoiceValue],
    ) -> ChoiceValue:
        return self._random.choice(tuple(values))

    def _quote_if_needed(self, value: str) -> str:
        if " " not in value:
            return value

        escaped_value = value.replace('"', '\\"')
        return f'"{escaped_value}"'
