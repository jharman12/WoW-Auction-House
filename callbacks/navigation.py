from dash import Dash, Input, Output

from layouts.pages import resolve_page
from services.category_taxonomy import CategoryFilterDocument
from services.catalog_service import CatalogItem, CharacterDefinition
from services.npc_simulation_service import NpcSimulationSettings


def register_navigation(
    app: Dash,
    items: list[CatalogItem],
    category_filters: CategoryFilterDocument,
    characters: list[CharacterDefinition],
    poll_interval_ms: int,
    simulation_settings: NpcSimulationSettings,
) -> None:
    @app.callback(Output("page-content", "children"), Input("url", "pathname"))
    def navigate(pathname: str | None):
        return resolve_page(pathname, items, category_filters, characters, poll_interval_ms, simulation_settings)