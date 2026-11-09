# WoW Auction House

A local-network auction house for a D&D campaign. Phase 5 provides
editable JSON catalogs, Player/DM navigation, a shared Player/NPC market,
listing management, item details, atomic purchases, and transaction
history with player sale proceeds.

## Requirements

- Python 3.12 or newer
- Windows or Linux

## Setup

From the repository root, create and activate a virtual environment.

Windows PowerShell:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

Linux:

```sh
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

## Run

```sh
python app.py
```

Open `http://localhost:8050` on the host computer. The server binds to
`0.0.0.0` by default so other devices on the same trusted local network can
connect using the host computer's LAN IP and port 8050. The host's firewall
may need to allow inbound connections on that port for private networks.
No firewall rules are changed automatically. This app has no authentication
and is intended only for a trusted LAN; do not expose it to the public
internet.

Configuration is read from environment variables prefixed with `AUCTION_`:

| Variable | Default | Purpose |
| --- | --- | --- |
| `AUCTION_HOST` | `0.0.0.0` | Bind address |
| `AUCTION_PORT` | `8050` | Web server port |
| `AUCTION_DATABASE_PATH` | `instance/auction_house.db` | SQLite database path |
| `AUCTION_LOG_LEVEL` | `INFO` | Log verbosity |
| `AUCTION_LOG_PATH` | `logs/auction_house.log` | Log file path |
| `AUCTION_MINIMUM_PRICE_MULTIPLIER` | `0.25` | Lower overall price multiplier |
| `AUCTION_MAXIMUM_PRICE_MULTIPLIER` | `4.0` | Upper overall price multiplier |
| `AUCTION_MAX_PRICE_CHANGE_PERCENT` | `10` | Maximum price movement per update |
| `AUCTION_ECONOMY_TARGET_SUPPLY_QUANTITY` | `10` | Target active supply per item |
| `AUCTION_ECONOMY_TARGET_DEMAND_QUANTITY` | `5` | Target quantity sold in the demand window |
| `AUCTION_ECONOMY_DEMAND_WINDOW_HOURS` | `168` | Rolling demand window |
| `AUCTION_ECONOMY_SMOOTHING_FACTOR` | `0.5` | Weight given to the new calculated price |
| `AUCTION_ECONOMY_MINIMUM_PRICE_GP` | `1` | Price floor in gold pieces |
| `AUCTION_ECONOMY_PRICE_ROUNDING_INCREMENT` | `1` | Price rounding denomination in gold pieces |
| `AUCTION_ECONOMY_UPDATE_INTERVAL_MINUTES` | `60` | Scheduled price recalculation interval |
| `AUCTION_MARKET_HISTORY_INTERVAL_MINUTES` | `60` | Scheduled history snapshot interval |
| `AUCTION_NPC_SIMULATION_ENABLED` | `true` | Default scheduled NPC simulation state |
| `AUCTION_NPC_SIMULATION_INTERVAL_SECONDS` | `300` | NPC cycle interval |
| `AUCTION_NPC_ACTIVITY_INTENSITY` | `0.35` | Default NPC activity probability scale |
| `AUCTION_MAX_NPC_LISTINGS` | `100` | Maximum active NPC listings |
| `AUCTION_MAX_NPC_NEW_LISTINGS_PER_CYCLE` | `5` | Maximum NPC listings generated per cycle |
| `AUCTION_MAX_NPC_TRANSACTIONS_PER_CYCLE` | `10` | Maximum NPC purchases per cycle |

The DM's simulation settings are stored in SQLite and override these
startup defaults after they are saved in the dashboard.

## Marketplace

Player listings use the selected character context and can be cancelled
from that character's active-listing view. Asking prices are entered and
shown per item in gold pieces; the app does not set a player price or
manage a gold balance. Listings expire after the configured
`AUCTION_DEFAULT_LISTING_EXPIRATION_DAYS` period, defaulting to 14 days.
Expired and cancelled listings remain in SQLite, and expired listings
are moved out of the active market when it refreshes.

The campaign's initial NPC stock and buyer/seller preferences are in
`data/npc_market_seed.json`. Startup seeds those NPCs and listings once;
restarting the app does not duplicate them or recreate listings that have
been cancelled. The DM view can cancel any active listing.

## NPC Simulation

Scheduled NPC cycles generate listings from the local catalog and let
active NPC buyers evaluate player and NPC listings. Each NPC uses its
preferred categories/rarities, purchase probability, price ceiling,
per-cycle budget, and seller activity settings. Simulated purchases use
the same atomic auction service and appear in the transaction ledger.
Activity intensity and per-cycle/active-listing caps are configurable in
the DM dashboard. Settings persist in SQLite. **Run cycle now** triggers
one bounded cycle even while scheduled simulation is paused. NPC budgets
are simulation limits, not player wallets; no player gold is managed.

## Purchases And Sales

Players can choose **Buy** on another character's or an NPC's market row.
A confirmation dialog must be accepted before the whole listing is
recorded as sold at its asking price and quantity. It does not charge or
store player gold. NPC buyer services use the same
atomic purchase operation; a sale of a player listing is recorded as
proceeds for that character to add manually to D&D Beyond. NPC-to-NPC
transactions are kept in the ledger but never count as player proceeds.
The Player view shows that character's completed sales, while the DM view
shows recent transactions. Completed transactions are retained in
SQLite; player collection acknowledgment is not implemented yet.

## Economy

Market prices use each item's JSON `base_price`, total active listing
quantity, and completed quantity sold in the recent demand window. Defaults
target 10 units of supply and 5 units sold over 168 hours. Supply and demand
multipliers are combined, clamped to the configured minimum/maximum
multipliers, smoothed, limited to a 10% change per update, floored at 1 gp,
and rounded to whole gold pieces. These defaults are configurable in
`config.py`.

Missing current prices are initialized at app startup. APScheduler
recalculates prices and records history at the configured intervals. The
DM can also use **Recalculate prices** for an immediate update and snapshot;
the dashboard charts an item's history and shows current supply and recent
demand. The Player listing preview shows a recommendation, but does not
change the player's entered asking price.

## Catalog Data

The app also loads `output/auction_house_items.json` when present, in
addition to `data/item_catalog.json`. Set `AUCTION_ADDITIONAL_CATALOG_PATH`
to use another generated catalog. Both sources are validated with the same
schema; duplicate IDs across sources produce a startup error. Existing
sample IDs remain available for historical listings and NPC seed references.
Restart the app after generating more items. Imported items become available
for player listing creation and NPC listing generation; import alone does
not create active listings. Review AI-generated tags and categories manually,
since schema validation cannot verify D&D rule accuracy.

Edit `data/item_catalog.json` to add or change items. The root object has
one `items` array. Every item requires a stable `id`, `name`, `category`,
`rarity`, positive `base_price`, and `description`. `base_price` is in
gold pieces. Optional fields are `image`, `stackable`, `properties`,
`tags`, and `enabled`.

The sample uses categories `weapon`, `armor`, `adventuring_gear`,
`consumable`, `magic_item`, and `material`; common rarity values include
`common`, `uncommon`, `rare`, `very_rare`, `legendary`, and `artifact`.
Campaign-defined categories and rarities are also accepted as lowercase
slugs such as `relic` or `mythic`. Item IDs must be unique, lowercase
URL-friendly values; keep them unchanged when renaming an item so future
listing history can continue to refer to it.

An image is optional. When provided, set `image` to a relative filename
under `assets/images/items/`, for example `ironbound-shortsword.png`.
Missing files are logged and use the built-in placeholder. Character
definitions are in `data/characters.json`; character images use
`assets/images/characters/`. The included items and characters are
original sample data intended to demonstrate the structure and can be
replaced with campaign content.

## Marketplace Category Filters

`data/marketplace_filters.json` defines the collapsible Player/DM category
tree. Top-level entries filter by catalog `category`; nested groups and
properties also require matching item tags. Add the listed tags to an
item's `tags` array in `data/item_catalog.json` to make it appear under
those branches. A nested selection requires every tag along its path, so
**Weapons → Simple Ranged → Finesse** only matches items classified as
both simple ranged and finesse.

Tag prefixes follow the tree: weapon properties use `weapon:`, armor
types use `armor:`, utility leaves use `utility:`, and potion types use
`potion:`. For example, a simple melee thrown weapon can use
`weapon:simple_melee` and `weapon:thrown`. The taxonomy and sample tags
are editable locally; the filter tree does not alter canonical catalog
item IDs or listing records.

Example item:

```json
{
	"id": "ironbound-shortsword",
	"name": "Ironbound Shortsword",
	"category": "weapon",
	"rarity": "common",
	"base_price": 10,
	"description": "A practical blade with a leather-wrapped grip.",
	"image": null,
	"stackable": false,
	"properties": {"damage": "1d6 piercing", "weight_lb": 2},
	"tags": ["melee", "martial"],
	"enabled": true
}
```

## Database And Backups

The SQLite database is created under `instance/` on first startup and
upgraded with Alembic migrations. To back it up, stop the application and
copy `instance/auction_house.db` to a dated backup location. To restore,
stop the application and replace the database file with the backup. Keep
the backup outside the repository. The database and logs are ignored by
Git.

## Tests

```sh
python -m pytest
```

The tests cover configuration validation, database migration and
persistence, catalog and character validation, shared Player/NPC
listings, filtering, details, creation, cancellation, expiration,
purchase atomicity, buyer/seller combinations, sale proceeds, duplicate
purchase prevention, rollback, and Dash navigation. LAN reachability
from a second device must be verified on the campaign network.