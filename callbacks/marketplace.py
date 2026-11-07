import json
import logging
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from urllib.parse import quote, unquote

from dash import ALL, Dash, Input, Output, State, ctx, html, no_update
from sqlalchemy.orm import Session, sessionmaker

from config import Settings
from services.auction_service import (
    BuyerContext,
    InvalidBuyerError,
    purchase_listing,
    get_character_sales,
    get_recent_transactions,
)
from services.catalog_service import CatalogItem
from services.listing_service import (
    ListingError,
    ListingView,
    cancel_listing,
    create_player_listing,
    get_character_active_listings,
    get_listing_view,
    get_marketplace,
)


logger = logging.getLogger(__name__)


def _has_positive_click(value: int | float | list[int] | None) -> bool:
    if isinstance(value, (list, tuple)):
        return any(isinstance(click_count, (int, float)) and not isinstance(click_count, bool) and click_count > 0 for click_count in value)
    return isinstance(value, (int, float)) and not isinstance(value, bool) and value > 0


def _format_price(price: Decimal) -> str:
    if price == price.to_integral_value():
        return f"{price:,.0f}"
    return f"{price:,.2f}".rstrip("0").rstrip(".")


def _format_age(created_at: datetime) -> str:
    timestamp = created_at.replace(tzinfo=UTC) if created_at.tzinfo is None else created_at.astimezone(UTC)
    elapsed_seconds = max(0, int((datetime.now(UTC) - timestamp).total_seconds()))
    if elapsed_seconds < 60:
        return "just now"
    if elapsed_seconds < 3600:
        return f"{elapsed_seconds // 60}m ago"
    if elapsed_seconds < 86400:
        return f"{elapsed_seconds // 3600}h ago"
    return f"{elapsed_seconds // 86400}d ago"


def _format_expiration(expires_at: datetime | None) -> str:
    if expires_at is None:
        return "no expiry"
    timestamp = expires_at.replace(tzinfo=UTC) if expires_at.tzinfo is None else expires_at
    return f"expires {timestamp.astimezone().strftime('%b %d')}"


def _item_image(item: CatalogItem) -> html.Div | html.Img:
    if item.image:
        return html.Img(
            src=f"/assets/images/items/{quote(item.image, safe='/')}",
            alt="",
            className="listing-art",
            loading="lazy",
        )
    return html.Div(item.name[:1].upper(), className=f"listing-art art-{item.rarity}", role="presentation")


def _listing_row(listing: ListingView, can_inspect: bool, can_cancel: bool) -> html.Article:
    actions = []
    if can_inspect:
        actions.append(
            html.Button(
                "Inspect",
                id={"type": "inspect-listing", "listing_id": listing.id},
                n_clicks=0,
                className="quiet-button",
            )
        )
    if can_cancel:
        actions.append(
            html.Button(
                "Cancel",
                id={"type": "cancel-listing", "listing_id": listing.id},
                n_clicks=0,
                className="text-button cancel-listing-button",
                title="Remove this active listing from the market",
            )
        )

    seller_label = "Player listing" if listing.owner_type == "PLAYER" else "NPC merchant"
    return html.Article(
        [
            _item_image(listing.item),
            html.Div(
                [
                    html.Div(
                        [
                            html.H3(listing.item.name),
                            html.Span(listing.item.rarity.replace("_", " "), className=f"rarity-tag rarity-{listing.item.rarity}"),
                        ],
                        className="listing-title-row",
                    ),
                    html.P(
                        [seller_label, html.Span(" · "), listing.owner_name],
                        className="listing-seller",
                    ),
                    html.P(
                        f"{listing.quantity} available · {listing.item.category.replace('_', ' ')} · "
                        f"listed {_format_age(listing.created_at)} · {_format_expiration(listing.expires_at)}",
                        className="listing-meta",
                    ),
                ],
                className="listing-main",
            ),
            html.Div(
                [
                    html.Strong(f"{_format_price(listing.asking_price)} gp"),
                    html.Span("each", className="price-unit"),
                ],
                className="listing-price",
            ),
            html.Div(actions, className="listing-actions"),
        ],
        className=f"listing-row listing-{listing.owner_type.lower()}",
    )


def _listing_details(listing: ListingView | None, can_purchase: bool = False) -> html.Div:
    if listing is None:
        return html.Div(
            [html.P("Select a listing to inspect it.", className="detail-empty")],
            className="listing-detail-content",
        )

    properties = [
        html.Div(
            [html.Span(key.replace("_", " ").title()), html.Span(json.dumps(value, ensure_ascii=False))],
            className="property-row",
        )
        for key, value in sorted(listing.item.properties.items())
    ]
    image = _item_image(listing.item)
    return html.Div(
        [
            image,
            html.Div(
                [
                    html.P(listing.item.category.replace("_", " ").upper(), className="eyebrow"),
                    html.H2(listing.item.name),
                    html.P(listing.item.description, className="detail-description"),
                    html.Div(
                        [
                            html.Div([html.Span("Rarity"), html.Strong(listing.item.rarity.replace("_", " "))]),
                            html.Div([html.Span("Available"), html.Strong(str(listing.quantity))]),
                            html.Div([html.Span("Asking price"), html.Strong(f"{_format_price(listing.asking_price)} gp each")]),
                            html.Div([html.Span("Seller"), html.Strong(f"{listing.owner_type} · {listing.owner_name}")]),
                        ],
                        className="detail-facts",
                    ),
                    html.Div(properties, className="property-list") if properties else None,
                    html.Div(
                        [
                            html.Button(
                                "Record purchase",
                                id={"type": "purchase-listing", "listing_id": listing.id},
                                n_clicks=0,
                                className="action-button",
                            ),
                            html.P(
                                "No app-managed gold is charged or stored.",
                                className="purchase-note",
                            ),
                        ],
                        className="purchase-action",
                    )
                    if can_purchase
                    else None,
                ],
                className="detail-copy",
            ),
        ],
        className="listing-detail-content",
    )


def _transaction_row(transaction, player_ledger: bool) -> html.Article:
    if player_ledger:
        summary = (
            f"Sold {transaction.quantity} × {transaction.item_name} to {transaction.buyer_name} "
            f"for {_format_price(transaction.total_price)} gp. "
            f"Add {_format_price(transaction.player_sale_proceeds or Decimal('0'))} gp manually to D&D Beyond."
        )
        label = "PLAYER SALE"
    else:
        summary = (
            f"{transaction.seller_type} · {transaction.seller_name} → "
            f"{transaction.buyer_type} · {transaction.buyer_name} · "
            f"{transaction.quantity} × {transaction.item_name} · {_format_price(transaction.total_price)} gp"
        )
        label = "TRANSACTION"

    return html.Article(
        [
            html.Span(label, className="transaction-kind"),
            html.P(summary, className="transaction-summary"),
            html.Time(
                    (
                        transaction.created_at.replace(tzinfo=UTC)
                        if transaction.created_at.tzinfo is None
                        else transaction.created_at.astimezone(UTC)
                    ).astimezone().strftime("%b %d, %Y %H:%M"),
                className="transaction-time",
            ),
        ],
        className="transaction-row",
    )


def _empty_listings(message: str) -> html.Div:
    return html.Div(message, className="listing-empty")


def register_marketplace_callbacks(
    app: Dash,
    items: list[CatalogItem],
    session_factory: sessionmaker[Session],
    settings: Settings,
) -> None:
    items_by_id = {item.id: item for item in items}

    @app.callback(
        Output("market-listings", "children"),
        Output("owner-listings", "children"),
        Output("market-count", "children"),
        Output("market-page-label", "children"),
        Output("listing-page", "data"),
        Output("transaction-history", "children"),
        Input("market-search", "value"),
        Input("market-category", "value"),
        Input("market-rarity", "value"),
        Input("market-sort", "value"),
        Input("market-poll", "n_intervals"),
        Input("listing-refresh-token", "data"),
        Input("market-previous", "n_clicks"),
        Input("market-next", "n_clicks"),
        State("url", "pathname"),
        State("listing-page", "data"),
    )
    def refresh_marketplace(
        search: str | None,
        category: str | None,
        rarity: str | None,
        sort_by: str | None,
        _poll_count: int,
        _refresh_token: int,
        _previous_clicks: int,
        _next_clicks: int,
        pathname: str | None,
        current_page: int | None,
    ):
        page = max(1, current_page or 1)
        if ctx.triggered_id in {"market-search", "market-category", "market-rarity", "market-sort"}:
            page = 1
        elif ctx.triggered_id == "market-previous":
            page = max(1, page - 1)
        elif ctx.triggered_id == "market-next":
            page += 1

        results = get_marketplace(
            session_factory,
            items_by_id,
            search=search or "",
            category=category or "all",
            rarity=rarity or "all",
            sort_by=sort_by or "newest",
            page=page,
        )
        total_pages = max(1, (results.total_count + results.page_size - 1) // results.page_size)
        if page > total_pages:
            page = total_pages
            results = get_marketplace(
                session_factory,
                items_by_id,
                search=search or "",
                category=category or "all",
                rarity=rarity or "all",
                sort_by=sort_by or "newest",
                page=page,
            )

        market_rows = [_listing_row(listing, can_inspect=True, can_cancel=False) for listing in results.listings]
        if not market_rows:
            market_content = _empty_listings("No active listings match these filters.")
        else:
            market_content = market_rows

        if pathname and pathname.startswith("/player/"):
            character_id = unquote(pathname.removeprefix("/player/"))
            owner_rows = get_character_active_listings(session_factory, items_by_id, character_id)
            owner_content = (
                [_listing_row(listing, can_inspect=False, can_cancel=True) for listing in owner_rows]
                if owner_rows
                else _empty_listings("You have no active listings.")
            )
        else:
            owner_content = (
                [_listing_row(listing, can_inspect=False, can_cancel=True) for listing in results.listings]
                if results.listings
                else _empty_listings("There are no active listings to manage.")
            )

        if pathname and pathname.startswith("/player/"):
            character_id = unquote(pathname.removeprefix("/player/"))
            transactions = get_character_sales(session_factory, items_by_id, character_id)
            transaction_content = (
                [_transaction_row(transaction, player_ledger=True) for transaction in transactions]
                if transactions
                else _empty_listings("Completed sales for this character will appear here.")
            )
        elif pathname == "/dm":
            transactions = get_recent_transactions(session_factory, items_by_id)
            transaction_content = (
                [_transaction_row(transaction, player_ledger=False) for transaction in transactions]
                if transactions
                else _empty_listings("Completed purchases will appear in the ledger.")
            )
        else:
            transaction_content = []

        count_label = f"{results.total_count} active listing{'s' if results.total_count != 1 else ''}"
        if results.truncated:
            count_label += " · first 5,000 shown"
        return (
            market_content,
            owner_content,
            count_label,
            f"Page {page} of {total_pages}",
            page,
            transaction_content,
        )

    @app.callback(
        Output("listing-preview", "children"),
        Input("listing-item", "value"),
        Input("listing-quantity", "value"),
        Input("listing-price", "value"),
    )
    def preview_listing(item_id: str | None, quantity: int | None, asking_price: int | float | None):
        item = items_by_id.get(item_id or "")
        if item is None:
            return "Choose an item to preview its listing details before posting."
        quantity_text = str(quantity) if quantity and quantity > 0 else "1"
        if asking_price is None:
            price_text = "price not set"
        else:
            try:
                price_text = f"{_format_price(Decimal(str(asking_price)))} gp each"
            except InvalidOperation:
                price_text = "invalid price"
        return f"Preview: {quantity_text} × {item.name} · {item.rarity.replace('_', ' ')} · {price_text}"

    @app.callback(
        Output("listing-feedback", "children"),
        Output("listing-refresh-token", "data"),
        Input("create-listing", "n_clicks"),
        Input({"type": "cancel-listing", "listing_id": ALL}, "n_clicks"),
        Input("purchase-confirmation", "submit_n_clicks"),
        State("url", "pathname"),
        State("listing-item", "value"),
        State("listing-quantity", "value"),
        State("listing-price", "value"),
        State("listing-refresh-token", "data"),
        State("purchase-listing-id", "data"),
        prevent_initial_call=True,
    )
    def mutate_listings(
        _create_clicks: int,
        _cancel_clicks: list[int],
        _purchase_clicks: int,
        pathname: str | None,
        item_id: str | None,
        quantity: int | float | None,
        asking_price: int | float | None,
        refresh_token: int | None,
        purchase_listing_id: int | None,
    ):
        try:
            triggered_id = ctx.triggered_id
            if triggered_id == "purchase-confirmation":
                if not _has_positive_click(_purchase_clicks):
                    return no_update, no_update
                if not pathname or not pathname.startswith("/player/") or purchase_listing_id is None:
                    return "Select a listing from the player marketplace to purchase it.", no_update
                character_id = unquote(pathname.removeprefix("/player/"))
                transaction = purchase_listing(
                    session_factory,
                    purchase_listing_id,
                    BuyerContext(buyer_type="PLAYER", character_id=character_id),
                )
                return (
                    f"Purchase recorded for {_format_price(transaction.total_price)} gp. "
                    "No app-managed gold was deducted.",
                    (refresh_token or 0) + 1,
                )

            if triggered_id == "create-listing":
                if not _has_positive_click(_create_clicks):
                    return no_update, no_update
                if not pathname or not pathname.startswith("/player/"):
                    return "Select a campaign character before creating a listing.", no_update
                character_id = unquote(pathname.removeprefix("/player/"))
                if quantity is None or int(quantity) != quantity:
                    return "Quantity must be a positive whole number.", no_update
                if item_id is None or asking_price is None:
                    return "Choose an item and enter an asking price.", no_update
                create_player_listing(
                    session_factory,
                    items_by_id,
                    character_id,
                    item_id,
                    int(quantity),
                    asking_price,
                    settings.default_listing_expiration_days,
                )
                logger.info("Player listing created by character %s", character_id)
                return "Listing posted to the shared market.", (refresh_token or 0) + 1

            if isinstance(triggered_id, dict) and triggered_id.get("type") == "cancel-listing":
                if not _has_positive_click(_cancel_clicks):
                    return no_update, no_update
                if pathname == "/dm":
                    cancel_listing(
                        session_factory,
                        int(triggered_id["listing_id"]),
                        allow_any_owner=True,
                    )
                elif pathname and pathname.startswith("/player/"):
                    character_id = unquote(pathname.removeprefix("/player/"))
                    cancel_listing(
                        session_factory,
                        int(triggered_id["listing_id"]),
                        character_id=character_id,
                    )
                else:
                    return "Open a player or DM marketplace to manage listings.", no_update
                return "Listing cancelled.", (refresh_token or 0) + 1
        except ListingError as exc:
            return str(exc), no_update
        except (InvalidOperation, TypeError, ValueError):
            return "Check the item, quantity, and asking price, then try again.", no_update
        except Exception:
            logger.exception("Marketplace listing action failed")
            return "The listing could not be changed. Check the application log.", no_update
        return no_update, no_update

    @app.callback(
        Output("listing-details", "children"),
        Input({"type": "inspect-listing", "listing_id": ALL}, "n_clicks"),
        State("url", "pathname"),
        prevent_initial_call=True,
    )
    def inspect_listing(_clicks: list[int], pathname: str | None):
        if not _has_positive_click(_clicks):
            return no_update
        triggered_id = ctx.triggered_id
        if not isinstance(triggered_id, dict) or triggered_id.get("type") != "inspect-listing":
            return no_update
        listing = get_listing_view(
            session_factory,
            items_by_id,
            int(triggered_id["listing_id"]),
        )
        can_purchase = bool(
            listing is not None
            and listing.owner_type == "NPC"
            and pathname
            and pathname.startswith("/player/")
        )
        return _listing_details(listing, can_purchase=can_purchase)

    @app.callback(
        Output("purchase-confirmation", "displayed"),
        Output("purchase-listing-id", "data"),
        Output("purchase-confirmation", "message"),
        Input({"type": "purchase-listing", "listing_id": ALL}, "n_clicks"),
        State("url", "pathname"),
        prevent_initial_call=True,
    )
    def request_purchase(_clicks: list[int], pathname: str | None):
        if not _has_positive_click(_clicks):
            return no_update, no_update, no_update
        triggered_id = ctx.triggered_id
        if not isinstance(triggered_id, dict) or triggered_id.get("type") != "purchase-listing":
            return no_update, no_update, no_update
        if not pathname or not pathname.startswith("/player/"):
            return False, no_update, "Purchases can only be recorded from a player marketplace."

        listing = get_listing_view(session_factory, items_by_id, int(triggered_id["listing_id"]))
        if listing is None or listing.owner_type != "NPC":
            return False, no_update, "This NPC listing is no longer available."
        total_price = listing.asking_price * listing.quantity
        message = (
            f"Record purchase of {listing.quantity} x {listing.item.name} from {listing.owner_name} "
            f"for {_format_price(total_price)} gp? No app-managed gold will be deducted or stored."
        )
        return True, listing.id, message