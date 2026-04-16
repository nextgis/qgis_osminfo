import json

import pytest


def test_repository_normalizes_terms_without_losing_order(
    preset_repository,
) -> None:
    restaurant = preset_repository.load()["amenity/restaurant"]

    assert restaurant.name == "restaurant"
    assert restaurant.nameCased == "Restaurant"
    assert restaurant.terms[:4] == [
        "restaurant",
        "shared",
        "food",
        "amenity restaurant",
    ]


def test_resolver_prefers_lower_term_index(preset_resolver) -> None:
    resolution = preset_resolver.resolve("shared")

    assert resolution.conditions[0].key == "amenity"
    assert resolution.conditions[0].val == "restaurant"


def test_resolver_returns_expected_types_and_conditions(
    preset_resolver, wizard_modules
) -> None:
    resolution = preset_resolver.resolve("restaurant")
    models = wizard_modules.models

    assert resolution.types == [
        models.OsmElementType.NODE,
        models.OsmElementType.WAY,
        models.OsmElementType.RELATION,
    ]
    assert resolution.conditions == [
        models.ConditionNode(
            query=models.ConditionQueryType.EQ,
            key="amenity",
            val="restaurant",
        )
    ]


def test_fuzzy_search_returns_display_name(preset_resolver) -> None:
    assert preset_resolver.fuzzy_search("restarant") == "Restaurant"


def test_unknown_preset_raises_with_suggestion(
    preset_resolver,
    wizard_modules,
) -> None:
    with pytest.raises(
        wizard_modules.exceptions.OsmInfoError,
        match=r"Did you mean 'Restaurant'\?",
    ):
        preset_resolver.resolve("restarant")


def test_unknown_preset_exposes_user_message(preset_resolver) -> None:
    with pytest.raises(Exception) as exc_info:
        preset_resolver.resolve("restarant")

    error = exc_info.value
    assert getattr(error, "user_message", "").endswith(
        "Did you mean 'Restaurant'?"
    )


def test_repository_applies_english_translations_like_upstream(
    tmp_path,
    wizard_modules,
) -> None:
    presets_path = tmp_path / "presets.json"
    translations_path = tmp_path / "translations"
    translations_path.mkdir()

    presets_path.write_text(
        json.dumps(
            {
                "amenity/cafe": {
                    "name": "Cafe",
                    "terms": ["espresso"],
                    "geometry": ["point"],
                    "tags": {"amenity": "cafe"},
                }
            }
        ),
        encoding="utf-8",
    )
    (translations_path / "en.json").write_text(
        json.dumps(
            {
                "en": {
                    "presets": {
                        "presets": {
                            "amenity/cafe": {
                                "name": "Coffee Shop",
                                "terms": "coffee, latte",
                            }
                        }
                    }
                }
            }
        ),
        encoding="utf-8",
    )

    repository_class = wizard_modules.free_form.PresetRepository
    repository_class._cache = {}
    repository = repository_class(
        presets_path=presets_path,
        translations_path=translations_path,
        locale_name="en_US",
    )

    preset = repository.load()["amenity/cafe"]

    assert preset.translated is True
    assert preset.name == "coffee shop"
    assert preset.nameCased == "Coffee Shop"
    assert preset.terms[:4] == ["cafe", "coffee", "latte", "espresso"]


def test_repository_normalizes_referenced_preset_name_tail(
    tmp_path,
    wizard_modules,
) -> None:
    presets_path = tmp_path / "presets.json"
    presets_path.write_text(
        json.dumps(
            {
                "amenity/language_school": {
                    "name": "{education/language_school}",
                    "terms": [],
                    "geometry": ["point"],
                    "tags": {
                        "amenity": "language_school",
                    },
                }
            }
        ),
        encoding="utf-8",
    )

    repository_class = wizard_modules.free_form.PresetRepository
    repository_class._cache = {}
    repository = repository_class(
        presets_path=presets_path,
        locale_name="en",
    )

    preset = repository.load()["amenity/language_school"]

    assert preset.name == "language school"
    assert preset.nameCased == "{education/language_school}"
    assert preset.terms[:2] == [
        "language school",
        "amenity language school",
    ]


def test_resolver_keeps_original_name_searchable_after_translation(
    tmp_path,
    wizard_modules,
) -> None:
    presets_path = tmp_path / "presets.json"
    translations_path = tmp_path / "translations"
    translations_path.mkdir()

    presets_path.write_text(
        json.dumps(
            {
                "amenity/cafe": {
                    "name": "Cafe",
                    "terms": ["espresso"],
                    "geometry": ["point", "area"],
                    "tags": {"amenity": "cafe"},
                }
            }
        ),
        encoding="utf-8",
    )
    (translations_path / "en.json").write_text(
        json.dumps(
            {
                "en": {
                    "presets": {
                        "presets": {
                            "amenity/cafe": {
                                "name": "Coffee Shop",
                                "terms": "coffee, latte",
                            }
                        }
                    }
                }
            }
        ),
        encoding="utf-8",
    )

    repository_class = wizard_modules.free_form.PresetRepository
    repository_class._cache = {}
    repository = repository_class(
        presets_path=presets_path,
        translations_path=translations_path,
        locale_name="en_US",
    )
    resolver = wizard_modules.free_form.PresetFreeFormResolver(repository)
    models = wizard_modules.models

    assert resolver.resolve("Coffee Shop").conditions == [
        models.ConditionNode(
            query=models.ConditionQueryType.EQ,
            key="amenity",
            val="cafe",
        )
    ]
    assert resolver.resolve("Cafe").conditions == [
        models.ConditionNode(
            query=models.ConditionQueryType.EQ,
            key="amenity",
            val="cafe",
        )
    ]
    assert resolver.fuzzy_search("cofee shop") == "Coffee Shop"


def test_repository_ignores_missing_locale_specific_translations(
    tmp_path,
    wizard_modules,
) -> None:
    presets_path = tmp_path / "presets.json"
    translations_path = tmp_path / "translations"
    translations_path.mkdir()

    presets_path.write_text(
        json.dumps(
            {
                "amenity/cafe": {
                    "name": "Cafe",
                    "terms": [],
                    "geometry": ["point"],
                    "tags": {"amenity": "cafe"},
                }
            }
        ),
        encoding="utf-8",
    )
    (translations_path / "en.json").write_text(
        json.dumps(
            {
                "en": {
                    "presets": {
                        "presets": {"amenity/cafe": {"name": "Coffee Shop"}}
                    }
                }
            }
        ),
        encoding="utf-8",
    )

    repository_class = wizard_modules.free_form.PresetRepository
    repository_class._cache = {}
    repository = repository_class(
        presets_path=presets_path,
        translations_path=translations_path,
        locale_name="ru_RU",
    )

    preset = repository.load()["amenity/cafe"]

    assert preset.name == "coffee shop"
    assert preset.nameCased == "Coffee Shop"


def test_repository_loads_hyphenated_locale_translation_file(
    tmp_path,
    wizard_modules,
) -> None:
    presets_path = tmp_path / "presets.json"
    translations_path = tmp_path / "translations"
    translations_path.mkdir()

    presets_path.write_text(
        json.dumps(
            {
                "amenity/cafe": {
                    "name": "Cafe",
                    "terms": [],
                    "geometry": ["point"],
                    "tags": {"amenity": "cafe"},
                }
            }
        ),
        encoding="utf-8",
    )
    (translations_path / "pt-BR.json").write_text(
        json.dumps(
            {
                "pt-BR": {
                    "presets": {
                        "presets": {
                            "amenity/cafe": {
                                "name": "Coffeehouse",
                                "terms": "coffee",
                            }
                        }
                    }
                }
            }
        ),
        encoding="utf-8",
    )

    repository_class = wizard_modules.free_form.PresetRepository
    repository_class._cache = {}
    repository = repository_class(
        presets_path=presets_path,
        translations_path=translations_path,
        locale_name="pt_BR",
    )

    preset = repository.load()["amenity/cafe"]

    assert preset.name == "coffeehouse"
    assert preset.nameCased == "Coffeehouse"
    assert preset.terms[:2] == ["cafe", "coffee"]


def test_repository_reads_hyphenated_payload_from_underscored_file(
    tmp_path,
    wizard_modules,
) -> None:
    presets_path = tmp_path / "presets.json"
    translations_path = tmp_path / "translations"
    translations_path.mkdir()

    presets_path.write_text(
        json.dumps(
            {
                "amenity/cafe": {
                    "name": "Cafe",
                    "terms": [],
                    "geometry": ["point"],
                    "tags": {"amenity": "cafe"},
                }
            }
        ),
        encoding="utf-8",
    )
    (translations_path / "pt_BR.json").write_text(
        json.dumps(
            {
                "pt-BR": {
                    "presets": {
                        "presets": {"amenity/cafe": {"name": "Cafehouse"}}
                    }
                }
            }
        ),
        encoding="utf-8",
    )

    repository_class = wizard_modules.free_form.PresetRepository
    repository_class._cache = {}
    repository = repository_class(
        presets_path=presets_path,
        translations_path=translations_path,
        locale_name="pt-BR",
    )

    preset = repository.load()["amenity/cafe"]

    assert preset.name == "cafehouse"
    assert preset.nameCased == "Cafehouse"
