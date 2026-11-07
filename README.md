# WoW Auction House

A local-network auction house for a D&D campaign. Phase 3 provides
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

Other simulation and economy defaults are centralized in `config.py` for
later phases. They do not activate background jobs yet.

## Marketplace

Player listings use the selected character context and can be cancelled
from that character's active-listing view. Asking prices are entered and
shown per item in gold pieces; the app does not set a player price or
manage a gold balance. Listings expire after the configured
`AUCTION_DEFAULT_LISTING_EXPIRATION_DAYS` period, defaulting to 14 days.
Expired and cancelled listings remain in SQLite, and expired listings
are moved out of the active market when it refreshes.

The campaign's initial NPC stock is in `data/npc_market_seed.json`.
Startup seeds those NPCs and listings once; restarting the app does not
duplicate them or recreate listings that have been cancelled. This is
static sample stock, not the scheduled NPC simulation planned for a
later phase. The DM view can cancel any active listing.

## Purchases And Sales

Players can inspect an NPC listing and choose **Record purchase**. The
confirmation records the whole listing at its asking price and quantity.
It does not charge or store player gold. NPC buyer services use the same
atomic purchase operation; a sale of a player listing is recorded as
proceeds for that character to add manually to D&D Beyond. NPC-to-NPC
transactions are kept in the ledger but never count as player proceeds.
The Player view shows that character's completed sales, while the DM view
shows recent transactions. Completed transactions are retained in
SQLite; player collection acknowledgment is not implemented yet.

## Catalog Data

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