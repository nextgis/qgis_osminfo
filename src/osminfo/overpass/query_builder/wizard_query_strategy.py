from typing import List, Optional

from osminfo.core.exceptions import (
    OsmInfoWizardError,
    OsmInfoWizardParserError,
)
from osminfo.overpass.query_builder.query_header import QueryHeaderBuilder
from osminfo.overpass.query_builder.string_query_strategy import (
    StringQueryStrategy,
)
from osminfo.overpass.query_builder.wizard import (
    WizardQueryCompiler,
)
from osminfo.settings.osm_info_settings import OsmInfoSettings


class WizardQueryStrategy(StringQueryStrategy):
    """Compile wizard syntax into Overpass QL queries.

    Delegate parsing and rendering to the wizard compiler, while treating parser
    failures as a signal that the input is not wizard syntax.
    """

    NAME = "wizard"

    def __init__(
        self,
        compiler: Optional[WizardQueryCompiler] = None,
        settings: Optional[OsmInfoSettings] = None,
    ) -> None:
        self._compiler = compiler or WizardQueryCompiler()
        self._query_header_builder = QueryHeaderBuilder(settings)

    def build(self, search_string: str) -> List[str]:
        try:
            compiled_query = self._compiler.compile(search_string)
        except OsmInfoWizardParserError:
            return []
        except OsmInfoWizardError:
            raise

        return [self._query_header_builder.apply(compiled_query.query)]

    def repair_search(self, search_string: str) -> Optional[str]:
        return self._compiler.repair_search(search_string)
