# World of Warcraft-Inspired D&D Auction House

## Software Design Document (SDD)

**Document purpose:** Define the requirements, architecture, data model,
implementation approach, and acceptance criteria for a local-network
auction house application supporting a Dungeons & Dragons campaign.

**Status:** Initial implementation specification\
**Target platform:** Local Windows/Linux computer running a Python web
application\
**Primary users:** Dungeon Master (DM) and campaign players

------------------------------------------------------------------------

# 1. Project Overview

## 1.1 Purpose

Build a locally hosted, browser-based auction house for a Dungeons &
Dragons campaign. The experience should be inspired by the World of
Warcraft auction house: players can browse a shared marketplace, inspect
items, list items for sale, and see completed sales.

The application will simulate a living marketplace through non-player
character (NPC) buyers and sellers. NPC activity should make the
marketplace feel populated even when few or no players are online.

The application is a campaign utility, not a replacement for D&D Beyond.
The app tracks player item listings and sales, but **does not maintain
player gold balances**. D&D Beyond remains the source of truth for
player gold. When an NPC purchases a player listing, the app records the
sale and the amount of gold the player should manually add to D&D
Beyond.

## 1.2 Goals

-   Provide a polished, intuitive auction-house interface inspired by
    World of Warcraft.
-   Allow a player to select a prebuilt campaign character and interact
    with the marketplace.
-   Provide a separate DM dashboard for managing the marketplace and its
    simulation.
-   Maintain a shared marketplace containing both player and NPC
    listings.
-   Keep player listings and NPC listings distinguishable internally.
-   Simulate NPC buyers and sellers, including NPC purchases of player
    listings.
-   Dynamically adjust market prices based on supply and demand.
-   Maintain a permanent record of transactions, especially sales
    involving player-owned items.
-   Make the application available to devices on the same local network.
-   Keep the initial implementation straightforward to develop, operate,
    back up, and maintain.

## 1.3 Non-goals and Explicit Constraints

The following are outside the scope of the initial implementation:

-   Player gold balances, wallets, or bank accounts.
-   Automatically updating D&D Beyond.
-   Online hosting or public internet access.
-   User registration, passwords, PINs, authentication, or account
    security.
-   Real-money payments.
-   A complex real-time push architecture using WebSockets.
-   A full D&D character manager.
-   Automatic synchronization with D&D Beyond.

**Important:** Do not add a login screen, PIN prompt, password system,
or player authentication workflow. The intended access model is a
trusted, local campaign network.

## 1.4 Core User Experience

The landing page must present exactly two primary choices:

1.  **Player** --- Opens a character-selection screen containing the
    prebuilt campaign characters. Selecting a character opens the player
    marketplace view.
2.  **DM** --- Opens the DM dashboard directly.

Do not add additional landing-page choices or authentication steps.

The player should be able to browse the same marketplace that contains
NPC listings, create and manage their own listings, and review relevant
sale history.

The DM should be able to manage the market, inspect listings and
transactions, control or configure simulation behavior, and review the
economic state of the campaign.

## 1.5 Technology Stack

  Component          Technology                               Purpose
  ------------------ ---------------------------------------- ------------------------------------
  Language           Python 3.12+                             Application logic
  Frontend           Dash                                     Web interface
  Styling            Dash Bootstrap Components / custom CSS   UI design
  Charts             Plotly                                   Market analytics
  Database           SQLite                                   Persistent storage
  ORM                SQLAlchemy                               Database interactions
  Validation         Pydantic                                 Input and configuration validation
  Scheduling         APScheduler                              Background simulation scheduling
  Testing            Pytest                                   Automated tests
  Logging            Python logging                           System and transaction logs
  Image management   Local asset files                        Item and character artwork

Use compatible, pinned dependency versions in a `requirements.txt` file.

For the initial implementation, use Dash polling through `dcc.Interval`
rather than introducing WebSockets. This is sufficient for a small
campaign and reduces architectural complexity.

------------------------------------------------------------------------

# 2. System Architecture and Design Principles

## 2.1 Architecture Overview

The application should use a modular, layered architecture. The Dash
interface should not contain marketplace business rules or issue
database queries directly. Instead, UI callbacks should call
service-layer functions, which coordinate the auction engine, economy
engine, NPC simulation, and persistence layer.

The major logical components are:

1.  **Dash Web Interface** --- Landing page, player marketplace, DM
    dashboard, forms, tables, charts, and polling.
2.  **Application / Service Layer** --- Coordinates user actions and
    connects the UI to domain logic.
3.  **Auction Engine** --- Handles listing creation, validation,
    purchases, listing expiration, and transaction recording.
4.  **Economy Engine** --- Calculates market prices and updates price
    history using supply and demand.
5.  **NPC Simulation Engine** --- Generates NPC listings, evaluates
    buying opportunities, and simulates marketplace activity.
6.  **Item Catalog** --- Provides canonical item definitions, metadata,
    rarity, descriptions, and artwork references.
7.  **Persistence Layer** --- Uses SQLAlchemy and SQLite to store
    campaign state and historical records.
8.  **Background Scheduler** --- Runs periodic NPC and market simulation
    tasks.
9.  **Configuration and Asset Management** --- Loads settings, item
    catalog data, character artwork, and other local assets.

### High-level architecture

``` text
Browser (Player / DM)
        |
        v
Dash Web Interface
        |
        v
Application / Service Layer
        |
        +-------------------+-------------------+-------------------+
        |                   |                   |                   |
        v                   v                   v                   v
   Auction Engine      Economy Engine      NPC Simulation      Catalog Service
        |                   |                   |                   |
        +-------------------+-------------------+-------------------+
                            |
                            v
                    SQLAlchemy Data Layer
                            |
                            v
                       SQLite Database

Background Scheduler
        |
        +----> NPC Simulation
        +----> Auction Expiration
        +----> Economy Updates
        +----> Market History
```

## 2.2 Design Principles

### Separation of concerns

-   UI callbacks should be thin and should delegate to service
    functions.
-   Business rules should live in independently testable Python modules.
-   Database access should be centralized through SQLAlchemy models and
    repository/service functions.
-   NPC simulation should use the same auction and transaction services
    as player actions wherever practical. This prevents simulated
    transactions from bypassing marketplace rules.
-   Item definitions should be kept separate from player-owned and
    NPC-owned item instances.

### Single source of truth

-   SQLite is the source of truth for campaign marketplace state.
-   The JSON catalog is the source of truth for canonical item
    definitions.
-   D&D Beyond is the source of truth for player gold.
-   A player sale record is an instruction/reference for the player to
    update D&D Beyond manually; it is not a balance adjustment in this
    app.

### Shared marketplace, distinct ownership

Player and NPC listings appear together in the marketplace UI.
Internally, every listing must identify its source and owner type so
that the application can distinguish real player activity from simulated
NPC activity.

### Deterministic and auditable transactions

A transaction should be recorded atomically. A purchase must not result
in an item being sold twice, a listing remaining active after purchase,
or a player sale being omitted from the ledger.

### Simple local deployment

The app should run on one host machine and be accessible by browsers on
the same LAN. The initial implementation should not depend on cloud
services, external databases, or a public-facing server.

## 2.3 Application Startup and Network Access

-   Provide a clear application entry point, such as `python app.py`.
-   Bind the Dash server to `0.0.0.0` so other devices on the local
    network can connect.
-   Make the port configurable, with a documented default.
-   Display or log the host machine's LAN access URL when practical.
-   Do not expose the app through a public hosting service.
-   Do not add authentication or password controls.
-   Provide clear startup errors if the port is already in use or the
    database cannot be opened.

------------------------------------------------------------------------

# 3. User Interface Requirements

## 3.1 Visual Direction

The interface should be visually inspired by the World of Warcraft
auction house while remaining practical and readable in a browser.

Design characteristics:

-   Dark fantasy / game-interface styling.
-   Strong visual hierarchy.
-   Rarity colors for item names and borders.
-   Item icons or artwork displayed consistently.
-   Clear separation between search, filters, listings, and details.
-   Tables and controls that remain usable on common desktop and mobile
    browser sizes.
-   Avoid excessive animation or visual clutter.

Use custom CSS and Dash Bootstrap Components to achieve the desired
appearance. Keep styling centralized rather than scattering inline style
definitions throughout callbacks.

## 3.2 Landing Page

The landing page should have only two primary buttons:

-   **Player**
-   **DM**

Player opens character selection. DM opens the DM dashboard.

No login, PIN, password, or authentication interface should be present.

## 3.3 Player Character Selection

Display the prebuilt campaign characters. Each character should have:

-   Name.
-   Portrait or image, if available.
-   Optional short description or class label.
-   A clear selection action.

The selected character is a UI context used to associate listings and
sale records with that character. It is not a secure identity or
authentication mechanism.

## 3.4 Player Marketplace

The player view should include:

-   Shared marketplace listings.
-   Search by item name.
-   Filters for item category, rarity, and other useful catalog
    attributes.
-   Sorting by price, item name, rarity, and listing age.
-   Item detail inspection.
-   A way to create a listing from the available item catalog.
-   A view of the selected character's active listings.
-   A view of completed sales involving that character.
-   Clear indication of the amount of gold earned from each sale that
    should be manually added to D&D Beyond.

Player-facing UI must not display an app-managed gold balance or imply
that the app has updated D&D Beyond.

## 3.5 Listing Presentation

Each marketplace listing should show, where applicable:

-   Item icon.
-   Item name.
-   Rarity.
-   Quantity.
-   Asking price.
-   Seller or seller category (player or NPC), if useful to the
    interface.
-   Listing age or expiration information.
-   Relevant item details.

Player and NPC listings should be visually consistent enough to feel
like one marketplace. Do not create separate player and NPC
marketplaces.

## 3.6 Item Details

Selecting an item should provide a detail view or modal containing:

-   Item image.
-   Name.
-   Rarity.
-   Category.
-   Description.
-   Relevant properties.
-   Listed quantity.
-   Current asking price.
-   Seller/listing information.
-   Purchase action when applicable.

## 3.7 Create Listing

The player listing form should allow the user to:

-   Select an item from the catalog.
-   Enter quantity, where applicable.
-   Enter an asking price.
-   Review the listing before confirming.

Validate all inputs. Quantity and price must be positive. Do not permit
a listing with an invalid item reference.

The app does not need to verify that the character owns the item. The
campaign group can manage physical inventory and item ownership outside
the application.

## 3.8 DM Dashboard

The DM dashboard should provide access to:

-   Marketplace overview.
-   Active listings.
-   Recent transactions.
-   Player sales ledger.
-   NPC activity.
-   Market prices and price history.
-   Item catalog overview.
-   Simulation settings and controls.
-   Basic economic event controls, if implemented.
-   Administrative actions for correcting or removing invalid listings.

Destructive actions should require a clear confirmation step. This is an
operational safeguard, not an authentication feature.

## 3.9 Responsive Updates

Use `dcc.Interval` to periodically refresh relevant data displayed in
the browser. Polling should be configurable and should not cause
unnecessary full-page reloads.

A reasonable initial polling interval is approximately 5--10 seconds for
marketplace data. The interval can be adjusted after performance
testing.

------------------------------------------------------------------------

# 4. Item Catalog System

## 4.1 Catalog Source

Maintain canonical item definitions in JSON files stored locally in the
project. The catalog should be independent from the SQLite records that
represent individual listings and transactions.

The catalog should be easy to edit without changing application code.

## 4.2 Item Data Fields

Each item definition should support fields such as:

  -----------------------------------------------------------------------
  Field                               Description
  ----------------------------------- -----------------------------------
  `id`                                Stable unique item identifier

  `name`                              Display name

  `category`                          Equipment, weapon, armor,
                                      consumable, magic item, material,
                                      etc.

  `rarity`                            Common, uncommon, rare, very rare,
                                      legendary, artifact, or
                                      campaign-defined value

  `base_price`                        Baseline reference price in gold

  `description`                       Item description

  `image`                             Relative path to local artwork

  `stackable`                         Whether multiple units may be
                                      listed together

  `properties`                        Optional structured item attributes

  `tags`                              Search and filtering labels

  `enabled`                           Whether the item can currently be
                                      selected for new listings
  -----------------------------------------------------------------------

Additional optional fields may be added when needed, but catalog entries
should remain consistent and validated.

## 4.3 Item Identity

The catalog item ID must remain stable. Listings should reference the
catalog ID rather than relying on the item's display name.

Changing an item's display name should not break existing listings or
transaction history.

## 4.4 Image Management

-   Store item and character images locally.
-   Use relative paths from a known asset directory.
-   Validate that referenced files exist or provide a fallback image.
-   Do not require remote image hosting.
-   Use consistent image dimensions or CSS containers to avoid layout
    shifts.

## 4.5 Catalog Validation

Use Pydantic models to validate catalog data during startup or catalog
reload.

Validation should identify:

-   Missing IDs or names.
-   Duplicate IDs.
-   Invalid rarity or category values, where constrained.
-   Negative or malformed base prices.
-   Invalid image paths.
-   Missing required fields.

A malformed catalog entry should produce a useful error message. The
application should not silently create invalid item records.

------------------------------------------------------------------------

# 5. Auction Engine

The auction engine is responsible for all listing and purchase rules.

## 5.1 Listing Types

Every listing must identify whether it is:

-   **Player listing** --- A real campaign listing created on behalf of
    a selected player character.
-   **NPC listing** --- A simulated listing created by the NPC
    marketplace simulation.

Both types appear in the same marketplace.

## 5.2 Listing Lifecycle

A listing should support the following states:

-   `ACTIVE`
-   `SOLD`
-   `EXPIRED`
-   `CANCELLED`

Only active listings can be purchased.

A listing should record creation time and, if expiration is enabled,
expiration time.

## 5.3 Listing Creation

When a player creates a listing:

1.  Validate the selected character.
2.  Validate the catalog item ID.
3.  Validate quantity and asking price.
4.  Create a player listing.
5.  Record creation and ownership metadata.
6.  Make the listing visible in the shared marketplace.

The application should not subtract the item from a character inventory
because the app does not maintain character inventory.

NPC listing creation should follow the same core validation rules but
use an NPC owner reference.

## 5.4 Purchasing

A purchase operation must:

1.  Confirm the listing exists.
2.  Confirm the listing is active.
3.  Confirm the requested quantity is available.
4.  Confirm the purchase price and listing data are valid.
5.  Prevent duplicate or concurrent purchases.
6.  Record the transaction.
7.  Update or close the listing.
8.  Update market supply and demand information.

For a full purchase, mark the listing as sold. If partial purchases are
supported, reduce the remaining quantity and leave the listing active
until the remaining quantity reaches zero.

For the initial version, it is acceptable to implement whole-listing
purchases only, provided the data model can be extended to support
partial purchases later.

## 5.5 Player Sale Handling

When an NPC purchases a player listing:

-   Record the seller character.
-   Record the item and quantity.
-   Record the sale price.
-   Record the sale timestamp.
-   Mark the transaction as a player-relevant sale.
-   Display the net gold proceeds the player should manually add to D&D
    Beyond.

The application must not add the proceeds to a player gold balance.

When a player buys an NPC listing, record the purchase for marketplace
history. Do not attempt to debit an app-managed gold balance.

## 5.6 Listing Cancellation and Expiration

Players should be able to cancel their active listings. The DM should be
able to cancel or expire any listing.

Expired and cancelled listings should remain in the database for
historical and audit purposes rather than being deleted.

## 5.7 Transaction Atomicity

A purchase and its related database changes must be committed as one
transaction. If any step fails, roll back the operation so the listing
and transaction history remain consistent.

Use database transactions and appropriate constraints to reduce the
possibility of duplicate sales.

------------------------------------------------------------------------

# 6. Dynamic Pricing and Economy Engine

## 6.1 Objective

The marketplace should feel like a functioning economy. Prices should
respond to the quantity of items available and the rate at which items
are being purchased.

The central behavior is:

-   More supply generally lowers market prices.
-   Less supply generally raises market prices.
-   Strong demand generally raises prices.
-   Weak demand generally lowers prices.

Prices should remain bounded and should not fluctuate wildly from a
single transaction.

## 6.2 Base Price

Each catalog item should have a base price. This is the reference point
for market pricing, not necessarily the exact listing price.

## 6.3 Market Price Calculation

Implement a transparent, configurable formula. A reasonable initial
approach is to combine supply and demand multipliers:

``` text
market_price = base_price * supply_multiplier * demand_multiplier
```

The supply multiplier should decrease as active market supply increases
relative to a target supply level.

The demand multiplier should increase when purchases occur more
frequently than expected and decrease when demand is weak.

Clamp the final multiplier to configurable minimum and maximum values to
prevent extreme prices.

## 6.4 Supply Measurement

Supply can be estimated using:

-   Number of active listings for an item.
-   Total quantity currently listed.
-   Recent NPC and player listing activity.

The initial implementation may use total active quantity as the primary
supply measure.

## 6.5 Demand Measurement

Demand can be estimated using:

-   Completed purchases in a rolling time window.
-   Quantity sold in that window.
-   Number of purchase attempts, if tracked.

Use a configurable rolling window so that old transactions do not
permanently influence current prices.

## 6.6 Price Update Frequency

Price calculations should run on a scheduled interval rather than on
every page request.

Store price history so the DM can review market changes over time.

## 6.7 Price Stability

Implement:

-   Minimum and maximum price multipliers.
-   A maximum percentage change per update.
-   A minimum price floor.
-   Rounding to a sensible gold denomination.
-   Optional smoothing based on the previous market price.

The economy engine should be deterministic when supplied with the same
state and configuration, making it straightforward to test.

## 6.8 Player Asking Prices

A player should be allowed to choose an asking price rather than being
forced to use the calculated market price.

The UI may show the current estimated market price as a recommendation.
It should not silently replace the player's entered asking price.

------------------------------------------------------------------------

# 7. NPC Marketplace Simulation

## 7.1 Objective

NPC buyers and sellers should make the marketplace feel active and
provide opportunities for player listings to sell even when players are
not interacting with the app.

NPC activity must be clearly marked internally as simulated activity.

## 7.2 NPC Data

Each NPC should have:

-   Unique ID.
-   Name.
-   Optional description or archetype.
-   Buyer/seller capabilities.
-   Optional preferred categories or rarities.
-   Optional budget or spending tendency.
-   Active status.
-   Simulation behavior settings.

NPCs are marketplace simulation entities, not full D&D characters.

## 7.3 NPC Sellers

NPC sellers should periodically create listings using items from the
catalog.

The simulation should consider:

-   Item category.
-   Rarity.
-   Current market price.
-   Existing supply.
-   Configured listing frequency.
-   NPC-specific preferences.

NPC listings should use the same listing lifecycle and validation as
player listings.

## 7.4 NPC Buyers

NPC buyers should periodically evaluate active listings.

Their purchase decisions should consider:

-   Item category and preferences.
-   Item rarity.
-   Asking price compared with market price.
-   Current supply and demand.
-   A configurable probability of purchase.
-   NPC spending limits or budget behavior.

The simulation should not make every listing sell immediately. The
marketplace should have believable variation in how long items remain
listed.

## 7.5 NPC Purchase of Player Listings

NPCs must be able to buy player listings. This is a key feature.

When this occurs, the auction engine must record a player-relevant sale
and the player-facing sale ledger must show the proceeds to collect.

NPC purchases of NPC listings should be recorded as simulated
transactions but should not appear as player proceeds.

## 7.6 NPC-NPC Transactions

NPC-to-NPC transactions may be used to keep the market active and
influence price calculations. These transactions must be distinguishable
from transactions involving players.

Do not treat NPC-NPC sales as player earnings.

## 7.7 Simulation Controls

The DM dashboard should allow the DM to:

-   Enable or disable NPC simulation.
-   Trigger a simulation cycle manually.
-   Adjust simulation frequency.
-   Adjust NPC activity intensity.
-   Review recent NPC transactions.

Simulation settings should be stored in configuration or the database so
they persist across restarts.

## 7.8 Simulation Safety

The simulation should avoid:

-   Buying inactive or expired listings.
-   Buying the same listing more than once.
-   Creating invalid quantities or prices.
-   Generating unlimited listings.
-   Producing unbounded transaction volume.

Use configurable caps for active NPC listings and transactions per
simulation cycle.

------------------------------------------------------------------------

# 8. Player Listings and Transaction Tracking

## 8.1 Player Identity

The application should use the prebuilt character list to associate
player activity with campaign characters.

Selecting a character is a convenience for tracking listings and sales.
It is not authentication, and the application must not imply that it
prevents another person on the LAN from selecting that character.

## 8.2 Player Listing Records

Each player listing should retain:

-   Listing ID.
-   Character ID.
-   Catalog item ID.
-   Quantity.
-   Asking price.
-   Creation timestamp.
-   Expiration timestamp, if used.
-   Status.
-   Sale information when sold.

## 8.3 Permanent Sale Log

Maintain a permanent transaction ledger. Do not delete completed
transactions during normal operation.

For every sale involving a player-owned listing, record:

-   Transaction ID.
-   Listing ID.
-   Seller character.
-   Item.
-   Quantity.
-   Sale price.
-   Transaction timestamp.
-   Buyer type (NPC or player).
-   Net gold proceeds to collect.
-   Whether the sale has been acknowledged as collected, if that
    optional tracking feature is implemented.

The ledger should make it easy for the DM or player to identify exactly
how much gold needs to be added manually to D&D Beyond.

## 8.4 Gold Handling

The app must not:

-   Store player gold balances.
-   Calculate or display a current player wallet balance.
-   Automatically update D&D Beyond.
-   Treat simulated NPC currency as player currency.

The app may store the sale amount for a completed player listing and
show that amount as proceeds to collect.

## 8.5 Sale Collection Acknowledgment

An optional status such as `UNCLAIMED` / `COLLECTED` may be used to help
the DM track whether the player has manually added the proceeds to D&D
Beyond.

This status is only an acknowledgment of an external manual action. It
must not be interpreted as a gold balance or financial transaction
inside the app.

------------------------------------------------------------------------

# 9. Economic Events

Economic events are optional but useful for making the market feel
dynamic.

Examples include:

-   Regional shortage.
-   Merchant caravan arrival.
-   Seasonal demand.
-   Monster attack disrupting supply.
-   Increased demand for healing items.
-   A rare item influx.

An event may temporarily modify supply, demand, or price multipliers for
selected categories or items.

For the initial implementation:

-   Keep event definitions simple.
-   Allow the DM to activate or deactivate an event.
-   Record event start and end times.
-   Ensure events cannot bypass price bounds.
-   Make the impact visible in the DM dashboard.

If implementation time is limited, defer economic events until the core
auction and NPC systems are stable.

------------------------------------------------------------------------

# 10. Database Design

Use SQLite with SQLAlchemy ORM models. Database migrations should be
considered from the beginning; Alembic is recommended if schema changes
are expected during development.

The database should persist marketplace state between application
restarts.

## 10.1 Core Tables

### `characters`

Stores prebuilt campaign characters.

Suggested fields:

-   `id` --- Primary key.
-   `name` --- Character display name.
-   `image_path` --- Optional local portrait path.
-   `description` --- Optional description.
-   `active` --- Whether the character is selectable.

### `items`

Stores catalog item metadata in the database if a searchable database
mirror is useful. The JSON catalog remains the canonical source for
definitions.

Suggested fields:

-   `id` --- Stable catalog item ID.
-   `name`.
-   `category`.
-   `rarity`.
-   `base_price`.
-   `image_path`.
-   `enabled`.

Avoid duplicating catalog data unnecessarily. If item definitions are
loaded directly from JSON, database records should be limited to
information needed for relationships, search, or historical consistency.

### `npcs`

Stores NPC marketplace simulation entities.

Suggested fields:

-   `id`.
-   `name`.
-   `archetype`.
-   `is_buyer`.
-   `is_seller`.
-   `preferences_json`.
-   `active`.

### `listings`

Stores both player and NPC listings.

Suggested fields:

-   `id`.
-   `item_id`.
-   `owner_type` --- `PLAYER` or `NPC`.
-   `character_id` --- Nullable; populated for player listings.
-   `npc_id` --- Nullable; populated for NPC listings.
-   `quantity`.
-   `remaining_quantity`.
-   `asking_price`.
-   `status`.
-   `created_at`.
-   `expires_at`.
-   `sold_at`.

Enforce ownership consistency: a player listing should reference a
character, while an NPC listing should reference an NPC.

### `transactions`

Stores all completed purchases.

Suggested fields:

-   `id`.
-   `listing_id`.
-   `item_id`.
-   `seller_type`.
-   `seller_character_id` --- Nullable.
-   `seller_npc_id` --- Nullable.
-   `buyer_type`.
-   `buyer_character_id` --- Nullable.
-   `buyer_npc_id` --- Nullable.
-   `quantity`.
-   `unit_price`.
-   `total_price`.
-   `created_at`.
-   `player_sale_proceeds` --- Nullable or zero for transactions not
    involving a player seller.
-   `collection_status` --- Optional manual acknowledgment state.

Transactions must be immutable under normal application workflows.
Corrections should be explicit administrative adjustments rather than
silent edits.

### `market_history`

Stores market price snapshots.

Suggested fields:

-   `id`.
-   `item_id`.
-   `market_price`.
-   `active_supply`.
-   `recent_quantity_sold`.
-   `recorded_at`.

### `settings`

Stores persistent simulation and application settings.

Suggested fields:

-   `key`.
-   `value`.
-   `updated_at`.

### `economic_events`

If economic events are implemented, store event definitions and
activation history.

Suggested fields:

-   `id`.
-   `name`.
-   `description`.
-   `effect_json`.
-   `starts_at`.
-   `ends_at`.
-   `active`.

## 10.2 Optional Future Tables

The schema may later be extended with:

-   `bids` if bidding or timed auctions are added.
-   `mailbox` if the application later supports item delivery or
    notifications.
-   `simulation_runs` for detailed simulation auditing.
-   `administrative_adjustments` for tracking DM corrections.

Do not implement unused tables solely for speculative future features.
Keep the initial schema focused.

## 10.3 Database Constraints and Indexes

Add constraints and indexes for:

-   Listing status.
-   Listing owner type.
-   Item ID.
-   Character ID.
-   NPC ID.
-   Transaction timestamp.
-   Seller and buyer type.
-   Active listing queries.

Use database constraints where practical to prevent invalid ownership
combinations and duplicate transaction processing.

## 10.4 Timestamps

Use consistent timestamp handling. Store timestamps in UTC and convert
to local display time in the UI.

------------------------------------------------------------------------

# 11. Application Service Layer

The service layer should expose functions that the Dash callbacks can
call without needing to understand database internals.

Suggested service modules:

-   `listing_service`
-   `auction_service`
-   `transaction_service`
-   `market_service`
-   `npc_service`
-   `catalog_service`
-   `character_service`
-   `settings_service`
-   `event_service`

Example operations:

``` python
create_player_listing(character_id, item_id, quantity, asking_price)
cancel_listing(listing_id)
purchase_listing(listing_id, buyer_context)
get_marketplace(filters, sort_options)
get_character_active_listings(character_id)
get_character_sales(character_id)
get_unclaimed_player_proceeds()
run_npc_simulation_cycle()
update_market_prices()
get_market_history(item_id, limit)
```

Service functions should:

-   Validate input.
-   Open and close database sessions appropriately.
-   Apply domain rules.
-   Commit or roll back transactions.
-   Return predictable result objects or raise documented domain
    exceptions.
-   Avoid depending on Dash request or component objects.

------------------------------------------------------------------------

# 12. Background Simulation Architecture

Use APScheduler to run background tasks.

Potential scheduled jobs:

  -----------------------------------------------------------------------
  Job                                 Purpose
  ----------------------------------- -----------------------------------
  NPC simulation cycle                Generate NPC activity and evaluate
                                      purchases

  Listing expiration                  Mark expired listings

  Market price update                 Recalculate market prices

  Market history snapshot             Store periodic market data

  Cleanup / maintenance               Optional housekeeping without
                                      deleting permanent transaction
                                      history
  -----------------------------------------------------------------------

## 12.1 Scheduler Lifecycle

-   Start the scheduler once when the application process starts.
-   Avoid starting duplicate schedulers during development reloads or
    multi-worker deployment.
-   Shut it down cleanly when the process exits.
-   Log job start, completion, duration, and exceptions.
-   Ensure a failed job does not permanently stop future scheduled
    executions.

For the initial deployment, run a single application process and a
single scheduler instance.

## 12.2 Database Sessions

Each background task should create its own SQLAlchemy session. Do not
share a session between the scheduler and Dash callbacks.

## 12.3 Simulation Locking

Prevent overlapping simulation cycles. If a cycle is still running, skip
or defer the next cycle rather than allowing two cycles to process the
same listings simultaneously.

------------------------------------------------------------------------

# 13. Project Directory Structure

Use a modular structure similar to:

``` text
auction_house/
│
├── app.py
├── config.py
├── requirements.txt
├── README.md
│
├── assets/
│   ├── css/
│   │   └── style.css
│   ├── images/
│   │   ├── items/
│   │   └── characters/
│   └── fonts/
│
├── data/
│   ├── item_catalog.json
│   └── characters.json
│
├── database/
│   ├── __init__.py
│   ├── connection.py
│   ├── models.py
│   └── migrations/
│
├── layouts/
│   ├── __init__.py
│   ├── landing.py
│   ├── character_select.py
│   ├── player_market.py
│   └── dm_dashboard.py
│
├── callbacks/
│   ├── __init__.py
│   ├── navigation.py
│   ├── marketplace.py
│   ├── player.py
│   └── dm.py
│
├── services/
│   ├── __init__.py
│   ├── listing_service.py
│   ├── auction_service.py
│   ├── transaction_service.py
│   ├── market_service.py
│   ├── npc_service.py
│   ├── catalog_service.py
│   ├── character_service.py
│   ├── settings_service.py
│   └── event_service.py
│
├── engines/
│   ├── __init__.py
│   ├── auction_engine.py
│   ├── economy_engine.py
│   └── npc_simulation.py
│
├── scheduler/
│   ├── __init__.py
│   └── jobs.py
│
├── tests/
│   ├── conftest.py
│   ├── test_catalog.py
│   ├── test_listings.py
│   ├── test_auctions.py
│   ├── test_transactions.py
│   ├── test_economy.py
│   ├── test_npc_simulation.py
│   └── test_ui_services.py
│
├── logs/
└── instance/
    └── auction_house.db
```

The implementation may adjust this structure if there is a clear
architectural reason, but keep UI, services, engines, persistence, and
data assets separated.

------------------------------------------------------------------------

# 14. Configuration Management

Use a centralized configuration module.

Configuration should include:

-   Application host and port.
-   Database path.
-   Marketplace polling interval.
-   NPC simulation enabled/disabled.
-   NPC simulation frequency.
-   Maximum NPC listings.
-   Maximum NPC transactions per cycle.
-   Listing expiration defaults.
-   Price multiplier bounds.
-   Maximum price movement per update.
-   Economy update interval.
-   Market history interval.
-   Logging level and log path.

Use sensible defaults and validate configuration with Pydantic.

Avoid hardcoding important tuning values throughout the codebase.

------------------------------------------------------------------------

# 15. Networking and Deployment

## 15.1 Local Network Hosting

The application should be hosted on one computer and accessed by other
devices on the same local network.

Run Dash with a host binding of `0.0.0.0`, not only `127.0.0.1`.

The user should be able to open the application using the host
computer's LAN IP address and configured port, for example:

``` text
http://192.168.1.100:8050
```

The actual IP address will depend on the host network.

## 15.2 Firewall

Document that the host computer's firewall may need to allow inbound
connections on the configured application port for private/local
networks.

Do not create automatic firewall rules without explicit user action.

## 15.3 Deployment Scope

-   The app is intended for a trusted local network.
-   Do not configure public internet exposure.
-   Do not add cloud dependencies.
-   Do not add authentication, PINs, or passwords.
-   Do not claim that LAN-only access is a security boundary against
    every device or person on the network.

## 15.4 Operational Simplicity

The initial deployment should be easy to start and stop. Provide a
README with setup, dependency installation, database initialization,
startup, LAN access, backup, and troubleshooting instructions.

------------------------------------------------------------------------

# 16. Backup and Data Integrity

## 16.1 Persistent Data

The SQLite database contains important campaign marketplace state. It
must survive normal application restarts.

## 16.2 Backups

Provide a simple backup procedure for the database and relevant
configuration/catalog files.

At minimum:

-   Explain how to stop the app before copying the SQLite database, or
    use SQLite's backup mechanism.
-   Keep dated backups.
-   Explain how to restore a backup.
-   Do not automatically delete historical transaction records.

## 16.3 Data Integrity

-   Use database transactions for purchases and listing updates.
-   Validate references before creating listings.
-   Avoid hard deletion of completed listings and transactions.
-   Log administrative corrections.
-   Handle database exceptions gracefully.
-   Ensure background jobs cannot corrupt state through overlapping
    execution.

------------------------------------------------------------------------

# 17. Logging and Error Handling

Use Python's standard `logging` module.

Log:

-   Application startup and shutdown.
-   Database initialization and errors.
-   Catalog loading and validation errors.
-   Listing creation and cancellation.
-   Purchases and completed transactions.
-   NPC simulation cycles.
-   Market price updates.
-   Scheduler errors.
-   Administrative corrections.

Do not log unnecessary sensitive information. The application does not
need passwords or authentication secrets.

User-facing errors should be understandable and should not expose stack
traces. Detailed exceptions should be written to the log.

Use domain-specific exceptions where helpful, such as:

-   `ListingNotFoundError`
-   `ListingNotActiveError`
-   `InvalidListingError`
-   `PurchaseConflictError`
-   `CatalogValidationError`
-   `SimulationError`

------------------------------------------------------------------------

# 18. Testing Requirements

Use Pytest.

## 18.1 Unit Tests

Test:

-   Catalog loading and validation.
-   Price calculation.
-   Supply and demand multipliers.
-   Price bounds and rounding.
-   NPC buying decisions.
-   NPC listing generation.
-   Listing state transitions.
-   Transaction calculations.

## 18.2 Integration Tests

Test:

-   Creating a player listing.
-   Creating an NPC listing.
-   Purchasing an NPC listing.
-   NPC purchasing a player listing.
-   NPC purchasing an NPC listing.
-   Cancelling a listing.
-   Expiring a listing.
-   Recording and retrieving player sale proceeds.
-   Ensuring a player sale never updates a gold balance.
-   Database rollback after a failed purchase.
-   Scheduler jobs using independent database sessions.

## 18.3 Critical Acceptance Tests

The following scenarios are especially important:

1.  A player creates a listing and it appears in the shared marketplace.
2.  An NPC creates a listing and it appears in the same marketplace.
3.  An NPC buys a player listing.
4.  The player sale ledger records the correct item, quantity, price,
    and proceeds.
5.  The app does not create or modify a player gold balance.
6.  An NPC buys an NPC listing and the transaction is not counted as
    player proceeds.
7.  A listing cannot be purchased twice.
8.  Expired and cancelled listings cannot be purchased.
9.  Supply increases cause the market price to trend downward, all else
    equal.
10. Supply decreases cause the market price to trend upward, all else
    equal.
11. The app remains usable after a restart with all persisted data
    intact.
12. A second device on the same LAN can access the app.

## 18.4 UI Testing

Test service behavior independently of Dash where possible. Add UI-level
tests for critical navigation and callback behavior if practical.

------------------------------------------------------------------------

# 19. Development Roadmap

Implement the project in phases. Each phase should be tested and stable
before moving to the next.

## Phase 0 --- Project Foundation

-   Create the project directory structure.
-   Create and pin dependencies in `requirements.txt`.
-   Set up configuration management.
-   Initialize Dash.
-   Initialize SQLAlchemy and SQLite.
-   Create initial database models.
-   Add logging.
-   Add a basic README.
-   Verify that the application starts locally and can be accessed from
    another LAN device.

**Exit criteria:** The app starts, the database initializes, and the
basic LAN access path works.

## Phase 1 --- Catalog and Navigation

-   Define the JSON item catalog format.
-   Create a small representative catalog.
-   Add Pydantic catalog validation.
-   Load prebuilt characters.
-   Build the landing page with exactly Player and DM buttons.
-   Build character selection.
-   Build a basic DM dashboard landing view.
-   Apply the initial visual theme.

**Exit criteria:** Player can select a prebuilt character; DM can open
the dashboard; catalog and character data load correctly.

## Phase 2 --- Marketplace and Listings

-   Build the shared marketplace view.
-   Add search, filtering, and sorting.
-   Display item images and details.
-   Implement player listing creation.
-   Implement NPC listing creation through services or seed data.
-   Display player and NPC listings together.
-   Implement listing cancellation and expiration.

**Exit criteria:** Player and NPC listings can coexist in one
marketplace and follow valid lifecycle rules.

## Phase 3 --- Purchases and Transaction Ledger

-   Implement purchase operations.
-   Add atomic transaction handling.
-   Prevent duplicate purchases.
-   Record buyer and seller types.
-   Implement the permanent transaction ledger.
-   Implement the player sale proceeds view.
-   Ensure the app never stores player gold balances.
-   Add optional manual collection acknowledgment.

**Exit criteria:** An NPC can purchase a player listing and the app
clearly reports proceeds for manual entry into D&D Beyond.

## Phase 4 --- Economy Engine

-   Implement base price and market price calculation.
-   Implement supply measurement.
-   Implement demand measurement.
-   Add price bounds and smoothing.
-   Store market price history.
-   Add Plotly market analytics to the DM dashboard.

**Exit criteria:** Prices respond predictably to supply and demand and
the DM can inspect historical changes.

## Phase 5 --- NPC Simulation

-   Implement NPC data and preferences.
-   Implement NPC listing generation.
-   Implement NPC buyer evaluation.
-   Route purchases through the auction engine.
-   Add simulation caps and overlap prevention.
-   Add APScheduler jobs.
-   Add DM controls for simulation.

**Exit criteria:** NPC activity can populate the market and purchase
player listings without violating auction rules.

## Phase 6 --- Polish and Economic Events

-   Improve the WoW-inspired UI.
-   Add economic events if desired.
-   Improve empty states, error messages, and item detail presentation.
-   Tune polling and simulation frequency.
-   Add additional catalog content and artwork.
-   Test common desktop and mobile browser sizes.

**Exit criteria:** The app is intuitive and visually coherent for
campaign use.

## Phase 7 --- Release Readiness

-   Run all automated tests.
-   Test LAN access from multiple devices.
-   Test restart and recovery.
-   Verify backup and restore procedures.
-   Verify no player gold balance is stored.
-   Verify transaction history remains intact.
-   Complete README and setup instructions.

**Exit criteria:** The app is reliable enough for use during the
campaign.

------------------------------------------------------------------------

# 20. Initial Sample Data Requirements

Create enough sample data to make the marketplace useful during
development.

## 20.1 Characters

Include a few placeholder prebuilt characters with names and optional
local portrait paths. The actual campaign character list can be
substituted later.

## 20.2 Item Catalog

Include representative examples across categories and rarities, such as:

-   Basic weapons.
-   Armor and shields.
-   Adventuring gear.
-   Potions and consumables.
-   Common magic items.
-   Uncommon magic items.
-   Rare magic items.
-   Higher-rarity items for testing filters and price ranges.

Use sensible base prices as initial balancing values. The DM should be
able to edit catalog data without changing code.

## 20.3 NPCs

Include a small set of sample NPC archetypes, for example:

-   General merchant.
-   Weapons dealer.
-   Traveling trader.
-   Collector.
-   Adventurer.
-   Potion seller.

Give them varied preferences so the simulation does not behave
identically for every NPC.

------------------------------------------------------------------------

# 21. Nonfunctional Requirements

## 21.1 Performance

The app is intended for a small campaign, not a public high-traffic
marketplace.

-   Marketplace queries should be indexed and paginated or otherwise
    bounded as the dataset grows.
-   Polling should not trigger expensive full database scans.
-   Background jobs should have reasonable limits.
-   The application should remain responsive during ordinary NPC
    simulation.

## 21.2 Maintainability

-   Use type hints for service and engine functions.
-   Keep business logic out of Dash callbacks.
-   Use consistent naming and formatting.
-   Document non-obvious pricing and simulation behavior.
-   Keep configuration centralized.
-   Keep dependencies pinned and compatible.

## 21.3 Reliability

-   Persist data across restarts.
-   Use transactions for purchases.
-   Preserve completed transaction history.
-   Handle background task errors.
-   Provide a backup and restore procedure.

## 21.4 Usability

-   Make the main marketplace easy to browse.
-   Use clear labels and understandable feedback.
-   Keep player proceeds separate from any concept of an app-managed
    balance.
-   Make the DM dashboard useful without requiring technical knowledge.

------------------------------------------------------------------------

# 22. Future Enhancements

The following may be considered after the initial implementation is
stable:

-   Timed auctions and bidding.
-   Partial quantity purchases.
-   Mailbox or item delivery simulation.
-   More advanced NPC personalities.
-   Regional markets.
-   Multiple towns or auction houses.
-   Economic events with richer effects.
-   Item price forecasting.
-   Import/export of campaign data.
-   More detailed market analytics.
-   Optional multi-campaign support.

Do not let future enhancements delay the core shared marketplace, player
sale ledger, dynamic pricing, or NPC purchase functionality.

------------------------------------------------------------------------

# 23. Instructions for the AI Coding Assistant

The coding assistant should follow these implementation rules:

1.  Treat this SDD as the authoritative product specification.
2.  Implement the application in the phases described above.
3.  Do not skip ahead to advanced simulation before the core listing and
    transaction workflows are stable.
4.  Do not introduce authentication, PINs, passwords, or login flows.
5.  Do not create or maintain player gold balances.
6.  Do not attempt to integrate with or modify D&D Beyond.
7.  Keep player listings and NPC listings distinguishable internally.
8.  Present player and NPC listings together in the marketplace.
9.  Ensure NPCs can buy player listings.
10. Ensure player sale proceeds are recorded permanently and clearly
    displayed for manual entry into D&D Beyond.
11. Keep NPC-NPC transactions separate from player proceeds.
12. Use the same auction rules for player and NPC marketplace
    transactions wherever possible.
13. Keep the catalog in JSON and store artwork locally.
14. Use SQLAlchemy for database interactions.
15. Use Pydantic for validation.
16. Use APScheduler for background simulation.
17. Use `dcc.Interval` polling rather than WebSockets for the initial
    implementation.
18. Pin compatible dependency versions.
19. Write tests as each service or engine is implemented.
20. Do not silently change requirements. If a requirement is ambiguous
    or technically problematic, explain the issue and propose a solution
    before changing the design.

At the end of each phase, provide:

-   Files created or modified.
-   Features implemented.
-   Tests run and their results.
-   Known limitations.
-   Any decisions that differ from this SDD.
-   Confirmation that the phase exit criteria have been met.

Do not claim a phase is complete if its exit criteria have not been
verified.

------------------------------------------------------------------------

# 24. Final Project Acceptance Checklist

## Application and Navigation

-   [ ] Application starts using the documented command.
-   [ ] Application is accessible from another device on the same LAN.
-   [ ] Landing page has exactly two primary choices: Player and DM.
-   [ ] Player opens prebuilt character selection.
-   [ ] Selecting a character opens the player marketplace.
-   [ ] DM opens the DM dashboard directly.
-   [ ] No PIN, password, login, or authentication flow exists.

## Marketplace

-   [ ] Player listings appear in the marketplace.
-   [ ] NPC listings appear in the marketplace.
-   [ ] Player and NPC listings appear together.
-   [ ] Search, filters, and sorting work.
-   [ ] Item details display correctly.
-   [ ] Listing creation validates input.
-   [ ] Listing cancellation works.
-   [ ] Expiration works if enabled.

## Transactions and Gold

-   [ ] Purchases are recorded atomically.
-   [ ] Duplicate purchases are prevented.
-   [ ] NPCs can buy player listings.
-   [ ] NPCs can buy NPC listings.
-   [ ] Player sale history is permanent.
-   [ ] Player proceeds are displayed clearly.
-   [ ] NPC-NPC sales are not counted as player proceeds.
-   [ ] No player gold balance is stored or managed.
-   [ ] D&D Beyond remains the external source of truth.

## Economy and Simulation

-   [ ] Supply affects market prices in the intended direction.
-   [ ] Demand affects market prices in the intended direction.
-   [ ] Price bounds and smoothing work.
-   [ ] Price history is stored.
-   [ ] NPC sellers create listings.
-   [ ] NPC buyers evaluate listings.
-   [ ] NPCs can purchase player listings.
-   [ ] Simulation limits prevent runaway activity.
-   [ ] Background jobs do not overlap or corrupt marketplace state.

## Data and Operations

-   [ ] Catalog loads from JSON.
-   [ ] Catalog validation reports malformed data.
-   [ ] Local images load or fall back gracefully.
-   [ ] SQLite data persists across restarts.
-   [ ] Backup and restore instructions are documented.
-   [ ] Logs capture important operations and failures.
-   [ ] Automated tests pass.

------------------------------------------------------------------------

# 25. Final Implementation Priorities

The most important requirements, in priority order, are:

1.  **A working shared marketplace** where player and NPC listings
    appear together.
2.  **Player listing and sale tracking** that records what players sold
    and how much gold they should manually add to D&D Beyond.
3.  **NPC buyers and sellers** that make the marketplace feel active and
    can purchase player listings.
4.  **A dynamic economy** where supply and demand influence market
    prices.
5.  **A polished WoW-inspired interface** that is intuitive for players
    and useful for the DM.
6.  **Reliable local persistence and LAN access** with simple startup
    and backup procedures.

The application should prioritize a reliable, understandable marketplace
over premature complexity. Build and test the core auction workflow
first, then layer in the economy and NPC simulation.
