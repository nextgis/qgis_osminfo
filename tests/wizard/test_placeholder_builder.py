import importlib
from random import Random

import pytest


@pytest.mark.parametrize(
    "variant",
    [
        "preset",
        "preset_in",
        "preset_around",
        "key_value",
        "key_value_in",
        "expression",
        "id",
    ],
)
def test_placeholder_builder_variants_compile(
    wizard_modules,
    variant,
) -> None:
    builder_module = importlib.import_module(
        "osminfo.overpass.query_builder.wizard.placeholder_builder"
    )
    builder = builder_module.PlaceholderBuilder(random_generator=Random(0))

    placeholder = builder.build(variant)
    compiled_query = wizard_modules.compiler.WizardQueryCompiler().compile(
        placeholder
    )

    assert placeholder
    assert compiled_query.query_count >= 1


def test_placeholder_builder_random_builds_compile(wizard_modules) -> None:
    builder_module = importlib.import_module(
        "osminfo.overpass.query_builder.wizard.placeholder_builder"
    )
    builder = builder_module.PlaceholderBuilder(random_generator=Random(0))
    compiler = wizard_modules.compiler.WizardQueryCompiler()

    placeholders = [builder.build() for _ in range(20)]

    assert len(set(placeholders)) > 1
    for placeholder in placeholders:
        compiled_query = compiler.compile(placeholder)
        assert compiled_query.query_count >= 1
