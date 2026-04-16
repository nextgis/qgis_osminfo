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
        "Vienna",
        "London",
        "Berlin",
        "Prague",
        "Paris",
        "Rome",
        "Madrid",
        "Lisbon",
        "Warsaw",
        "Budapest",
        "Munich",
        "Hamburg",
        "Zurich",
        "Amsterdam",
        "Brussels",
    )
    _PLACE_NAMES: Tuple[str, ...] = (
        "Eiffel Tower",
        "Statue of Liberty",
        "Great Wall of China",
        "Taj Mahal",
        "Machu Picchu",
        "Christ the Redeemer",
        "Colosseum",
        "Pyramids of Giza",
        "Sydney Opera House",
        "Golden Gate Bridge",
        "Big Ben",
        "Mount Fuji",
        "Burj Khalifa",
        "Acropolis of Athens",
        "Angkor Wat",
    )
    _OSM_IDS: Tuple[str, ...] = (
        "5013364",
        "1802652184",
        "5305957",
    )
    _PRESET_IDENTIFIERS: Tuple[str, ...] = (
        "amenity/cafe",
        "amenity/drinking_water",
        "amenity/pharmacy",
        "amenity/restaurant",
        "tourism/hotel",
        "tourism/museum",
    )
    _FALLBACK_PRESET_NAMES: Tuple[str, ...] = (
        "Cafe",
        "Drinking Water",
        "Pharmacy",
        "Restaurant",
        "Hotel",
        "Museum",
    )
    _KEY_VALUE_PAIRS: Tuple[Tuple[str, str], ...] = (
        ("amenity", "drinking_water"),
        ("amenity", "pharmacy"),
        ("shop", "bakery"),
        ("tourism", "hotel"),
        ("tourism", "museum"),
    )
    _READY_EXPRESSIONS: Tuple[str, ...] = (
        "amenity=drinking_water and type:node",
        "(highway=primary or highway=secondary) and type:way",
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
        return self._choose(self._preset_names())

    def _build_preset_in(self) -> str:
        preset_name = self._quote_if_needed(self._build_preset())
        city_name = self._quote_if_needed(self._choose(self._CITY_NAMES))
        return f"{preset_name} in {city_name}"

    def _build_preset_around(self) -> str:
        preset_name = self._quote_if_needed(self._build_preset())
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
