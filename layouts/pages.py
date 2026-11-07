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


def player_marketplace_page(
    character: CharacterDefinition,
    item_count: int,
) -> html.Div:
    return html.Div(
        [
            _masthead("Player Marketplace", "Change character", "/characters"),
            html.Main(
                [
                    html.P(f"TRADING AS {character.name.upper()}", className="eyebrow"),
                    html.H1("Marketplace"),
                    html.P("The campaign exchange is being prepared for its first listings.", className="intro-copy"),
                    html.Section(
                        [
                            html.Div("*", className="empty-mark", role="presentation"),
                            html.H2("The stalls are quiet for now"),
                            html.P(
                                f"{item_count} catalog items are ready. Shared listings and browsing arrive in Phase 2.",
                                className="empty-copy",
                            ),
                        ],
                        className="empty-state",
                    ),
                ],
                className="content-page",
            ),
        ],
        className="app-shell",
    )


def dm_dashboard_page(item_count: int, character_count: int) -> html.Div:
    return html.Div(
        [
            _masthead("DM Dashboard", "Home", "/"),
            html.Main(
                [
                    html.P("CAMPAIGN CONTROL", className="eyebrow"),
                    html.H1("DM Dashboard"),
                    html.P("The foundation is ready. Market activity will appear here as it is built.", className="intro-copy"),
                    html.Div(
                        [
                            html.Section(
                                [html.P("CATALOG", className="eyebrow"), html.Strong(str(item_count)), html.Span("items loaded")],
                                className="metric-panel",
                            ),
                            html.Section(
                                [html.P("CAMPAIGN", className="eyebrow"), html.Strong(str(character_count)), html.Span("characters loaded")],
                                className="metric-panel",
                            ),
                            html.Section(
                                [html.P("MARKET", className="eyebrow"), html.Strong("Not started"), html.Span("listings begin in Phase 2")],
                                className="metric-panel",
                            ),
                        ],
                        className="metric-grid",
                    ),
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
) -> html.Div:
    if pathname in (None, "", "/"):
        return landing_page()
    if pathname == "/characters":
        return character_selection_page(characters)
    if pathname == "/dm":
        return dm_dashboard_page(len(items), len(characters))
    if pathname.startswith("/player/"):
        character_id = unquote(pathname.removeprefix("/player/"))
        character = next((entry for entry in characters if entry.id == character_id), None)
        if character is not None:
            return player_marketplace_page(character, len(items))
    return not_found_page()