import json
from urllib.parse import quote, unquote

from dash import dcc, html

from services.catalog_service import CatalogItem, CharacterDefinition


def _masthead(section: str, action: str | None = None, href: str | None = None) -> html.Header:
    action_link = dcc.Link(action, href=href, className="text-link") if action and href else None
    return html.Header(
        [
            dcc.Link("THE GILDED LEDGER", href="/", className="brand-mark"),
            html.Span(section.upper(), className="masthead-section"),
            action_link,
        ],
        className="masthead",
    )


def landing_page() -> html.Div:
    return html.Div(
        [
            _masthead("Campaign Exchange"),
            html.Main(
                [
                    html.P("A SHARED MARKET FOR YOUR CAMPAIGN", className="eyebrow"),
                    html.H1(["The Gilded", html.Br(), "Ledger"]),
                    html.P(
                        "A place for adventurers, merchants, and the occasional lucky find.",
                        className="intro-copy",
                    ),
                    html.Div(
                        [
                            dcc.Link(
                                [
                                    html.Span("01", className="choice-index"),
                                    html.Span("Player", className="choice-title"),
                                    html.Span("Choose a character and enter the market", className="choice-caption"),
                                    html.Span(">", className="choice-arrow"),
                                ],
                                href="/characters",
                                className="portal-choice player-choice",
                            ),
                            dcc.Link(
                                [
                                    html.Span("02", className="choice-index"),
                                    html.Span("DM", className="choice-title"),
                                    html.Span("Review the campaign exchange", className="choice-caption"),
                                    html.Span(">", className="choice-arrow"),
                                ],
                                href="/dm",
                                className="portal-choice dm-choice",
                            ),
                        ],
                        className="portal-grid",
                    ),
                ],
                className="landing-content",
            ),
            html.Footer("LOCAL CAMPAIGN NETWORK", className="page-footer"),
        ],
        className="app-shell landing-page",
    )


def character_selection_page(characters: list[CharacterDefinition]) -> html.Div:
    cards = []
    for character in characters:
        portrait = (
            html.Img(
                src=f"/assets/images/characters/{quote(character.image, safe='/')}",
                alt=f"Portrait of {character.name}",
                className="character-portrait",
            )
            if character.image
            else html.Div("*", className="character-portrait portrait-fallback", role="presentation")
        )
        cards.append(
            html.Article(
                [
                    portrait,
                    html.Div(
                        [
                            html.P(character.class_label.upper(), className="eyebrow card-eyebrow"),
                            html.H2(character.name),
                            html.P(character.description, className="character-description"),
                            dcc.Link(
                                "Enter the market",
                                href=f"/player/{quote(character.id, safe='')}",
                                className="text-link select-character",
                            ),
                        ],
                        className="character-copy",
                    ),
                ],
                className="character-card",
            )
        )

    return html.Div(
        [
            _masthead("Character Select", "Back", "/"),
            html.Main(
                [
                    html.P("PLAYER ACCESS", className="eyebrow"),
                    html.H1("Choose your character"),
                    html.P("Select the campaign character whose activity you are tracking.", className="intro-copy"),
                    html.Div(cards, className="character-grid"),
                ],
                className="content-page",
            ),
        ],
        className="app-shell",
    )


def _marketplace_workspace(
    items: list[CatalogItem],
    poll_interval_ms: int,
    show_listing_form: bool,
) -> html.Div:
    enabled_items = [item for item in items if item.enabled]
    categories = sorted({item.category for item in enabled_items})
    rarities = sorted({item.rarity for item in enabled_items})
    listing_form = html.Section(
            [
                html.Div(
                    [
                        html.P("YOUR STALL", className="eyebrow"),
                        html.H2("Create a listing"),
                    ],
                    className="section-heading",
                ),
                html.Div(
                    [
                        dcc.Dropdown(
                            id="listing-item",
                            options=[
                                {"label": f"{item.name} · {item.rarity.replace('_', ' ')}", "value": item.id}
                                for item in enabled_items
                            ],
                            placeholder="Choose a catalog item",
                            clearable=True,
                            searchable=True,
                            className="market-dropdown listing-item-control",
                        ),
                        dcc.Input(id="listing-quantity", type="number", min=1, step=1, value=1, debounce=True),
                        dcc.Input(
                            id="listing-price",
                            type="number",
                            min=0.01,
                            step=0.01,
                            debounce=True,
                            placeholder="Price each (gp)",
                        ),
                        html.Button("Create listing", id="create-listing", n_clicks=0, className="action-button"),
                    ],
                    className="listing-form-grid",
                ),
                html.P("Choose an item to preview its listing details before posting.", id="listing-preview", className="listing-preview"),
            ],
            className="listing-composer" if show_listing_form else "listing-composer visually-hidden",
        )

    economy_panel = (
        html.Section(
            [
                html.Div(
                    [
                        html.Div(
                            [
                                html.P("ECONOMY ENGINE", className="eyebrow"),
                                html.H2("Market prices"),
                            ],
                            className="section-heading",
                        ),
                        html.Button(
                            "Recalculate prices",
                            id="market-update-prices",
                            n_clicks=0,
                            className="action-button",
                        ),
                    ],
                    className="market-heading-row economy-heading",
                ),
                html.P(
                    "Prices respond to active supply and recent purchases. Player asking prices remain independent.",
                    className="economy-caption",
                ),
                dcc.Dropdown(
                    id="market-history-item",
                    options=[{"label": item.name, "value": item.id} for item in enabled_items],
                    value=enabled_items[0].id if enabled_items else None,
                    clearable=False,
                    className="market-dropdown economy-item-select",
                ),
                dcc.Graph(
                    id="market-price-chart",
                    config={"displayModeBar": False, "responsive": True},
                    className="market-price-chart",
                ),
                html.Div(id="market-price-table", className="market-price-table"),
                html.P(id="market-update-feedback", className="listing-feedback", role="status"),
            ],
            className="economy-panel",
        )
        if not show_listing_form
        else None
    )

    return html.Div(
        [
            dcc.Interval(id="market-poll", interval=poll_interval_ms, n_intervals=0),
            dcc.Store(id="listing-refresh-token", data=0),
            dcc.Store(id="listing-page", data=1),
            dcc.Store(id="purchase-listing-id"),
            dcc.ConfirmDialog(id="purchase-confirmation", displayed=False),
            economy_panel,
            listing_form,
            html.P(id="listing-feedback", className="listing-feedback", role="status"),
            html.Section(
                [
                    html.Div(
                        [
                            html.Div(
                                [
                                    html.P("SHARED EXCHANGE", className="eyebrow"),
                                    html.H2("Active listings"),
                                ],
                                className="section-heading",
                            ),
                            html.P("", id="market-count", className="market-count"),
                        ],
                        className="market-heading-row",
                    ),
                    html.Div(
                        [
                            dcc.Input(
                                id="market-search",
                                type="search",
                                placeholder="Search item names and tags",
                                debounce=True,
                                className="market-search",
                            ),
                            dcc.Dropdown(
                                id="market-category",
                                options=[{"label": "All categories", "value": "all"}]
                                + [{"label": value.replace("_", " ").title(), "value": value} for value in categories],
                                value="all",
                                clearable=False,
                                className="market-dropdown",
                            ),
                            dcc.Dropdown(
                                id="market-rarity",
                                options=[{"label": "All rarities", "value": "all"}]
                                + [{"label": value.replace("_", " ").title(), "value": value} for value in rarities],
                                value="all",
                                clearable=False,
                                className="market-dropdown",
                            ),
                            dcc.Dropdown(
                                id="market-sort",
                                options=[
                                    {"label": "Newest", "value": "newest"},
                                    {"label": "Oldest", "value": "oldest"},
                                    {"label": "Price: low to high", "value": "price_asc"},
                                    {"label": "Price: high to low", "value": "price_desc"},
                                    {"label": "Item name", "value": "name"},
                                    {"label": "Rarity", "value": "rarity"},
                                ],
                                value="newest",
                                clearable=False,
                                className="market-dropdown",
                            ),
                        ],
                        className="market-filters",
                    ),
                    html.Div("Loading active listings...", id="market-listings", className="listing-stack"),
                    html.Div(
                        [
                            html.Button("Previous", id="market-previous", n_clicks=0, className="quiet-button"),
                            html.Span("Page 1 of 1", id="market-page-label", className="market-page-label"),
                            html.Button("Next", id="market-next", n_clicks=0, className="quiet-button"),
                        ],
                        className="market-pagination",
                    ),
                    html.Section(
                        html.P("Select Inspect on a listing to view its details.", className="detail-empty"),
                        id="listing-details",
                        className="listing-details",
                    ),
                ],
                className="market-section",
            ),
            html.Section(
                [
                    html.Div(
                        [
                            html.P("ACCOUNT ACTIVITY" if show_listing_form else "DM CONTROLS", className="eyebrow"),
                            html.H2("Your active listings" if show_listing_form else "Manage active listings"),
                        ],
                        className="section-heading",
                    ),
                    html.Div("Loading...", id="owner-listings", className="listing-stack owner-listings"),
                ],
                className="owner-listings-section",
            ),
            html.Section(
                [
                    html.Div(
                        [
                            html.P("PLAYER SALE LEDGER" if show_listing_form else "TRANSACTION LEDGER", className="eyebrow"),
                            html.H2("Completed sales" if show_listing_form else "Recent transactions"),
                        ],
                        className="section-heading",
                    ),
                    html.Div(id="transaction-history", className="transaction-stack"),
                ],
                className="transaction-history-section",
            ),
        ],
        className="marketplace-workspace",
    )


def player_marketplace_page(
    character: CharacterDefinition,
    items: list[CatalogItem],
    poll_interval_ms: int,
) -> html.Div:
    return html.Div(
        [
            _masthead("Player Marketplace", "Change character", "/characters"),
            html.Main(
                [
                    html.P(f"TRADING AS {character.name.upper()}", className="eyebrow"),
                    html.H1("Marketplace"),
                    html.P("Browse the campaign exchange or post an item from your inventory.", className="intro-copy"),
                    _marketplace_workspace(items, poll_interval_ms, show_listing_form=True),
                ],
                className="content-page",
            ),
        ],
        className="app-shell",
    )


def dm_dashboard_page(
    items: list[CatalogItem],
    character_count: int,
    poll_interval_ms: int,
) -> html.Div:
    return html.Div(
        [
            _masthead("DM Dashboard", "Home", "/"),
            html.Main(
                [
                    html.P("CAMPAIGN CONTROL", className="eyebrow"),
                    html.H1("DM Dashboard"),
                    html.P("Review the shared market and manage active listings.", className="intro-copy"),
                    html.Div(
                        [
                            html.Section(
                                [html.P("CATALOG", className="eyebrow"), html.Strong(str(len(items))), html.Span("items loaded")],
                                className="metric-panel",
                            ),
                            html.Section(
                                [html.P("CAMPAIGN", className="eyebrow"), html.Strong(str(character_count)), html.Span("characters loaded")],
                                className="metric-panel",
                            ),
                            html.Section(
                                [html.P("MARKET", className="eyebrow"), html.Strong("Live"), html.Span("shared player and NPC listings")],
                                className="metric-panel",
                            ),
                        ],
                        className="metric-grid",
                    ),
                    _marketplace_workspace(items, poll_interval_ms, show_listing_form=False),
                ],
                className="content-page",
            ),
        ],
        className="app-shell",
    )


def not_found_page() -> html.Div:
    return html.Div(
        [
            _masthead("Page Not Found", "Home", "/"),
            html.Main(
                [
                    html.P("404", className="eyebrow"),
                    html.H1("That page is not here."),
                    dcc.Link("Return home", href="/", className="text-link"),
                ],
                className="content-page",
            ),
        ],
        className="app-shell",
    )


def resolve_page(
    pathname: str | None,
    items: list[CatalogItem],
    characters: list[CharacterDefinition],
    poll_interval_ms: int,
) -> html.Div:
    if pathname in (None, "", "/"):
        return landing_page()
    if pathname == "/characters":
        return character_selection_page(characters)
    if pathname == "/dm":
        return dm_dashboard_page(items, len(characters), poll_interval_ms)
    if pathname.startswith("/player/"):
        character_id = unquote(pathname.removeprefix("/player/"))
        character = next((entry for entry in characters if entry.id == character_id), None)
        if character is not None:
            return player_marketplace_page(character, items, poll_interval_ms)
    return not_found_page()