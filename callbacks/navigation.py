from dash import Dash, Input, Output

from layouts.pages import resolve_page
from services.catalog_service import CatalogItem, CharacterDefinition


def register_navigation(
    app: Dash,
    items: list[CatalogItem],
    characters: list[CharacterDefinition],
    poll_interval_ms: int,
) -> None:
    @app.callback(Output("page-content", "children"), Input("url", "pathname"))
    def navigate(pathname: str | None):
        return resolve_page(pathname, items, characters, poll_interval_ms)