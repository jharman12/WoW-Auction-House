import json
from pathlib import Path

import pytest

from config import PROJECT_ROOT
from services.catalog_service import CatalogDataError, load_characters, load_item_catalog


DATA_ROOT = PROJECT_ROOT / "data"
ITEM_ASSET_ROOT = PROJECT_ROOT / "assets" / "images" / "items"
CHARACTER_ASSET_ROOT = PROJECT_ROOT / "assets" / "images" / "characters"


def test_sample_catalog_loads_representative_items() -> None:
    items = load_item_catalog(DATA_ROOT / "item_catalog.json", ITEM_ASSET_ROOT)

    assert len(items) == 8
    assert {item.category for item in items} >= {
        "weapon",
        "armor",
        "adventuring_gear",
        "consumable",
        "magic_item",
        "material",
    }
    assert {item.rarity for item in items} >= {"common", "uncommon", "rare", "very_rare"}
    assert all(item.base_price > 0 for item in items)
    assert items[4].properties["activation"]["reset"] == "dawn"


def test_campaign_defined_category_and_rarity_are_supported(tmp_path: Path) -> None:
    catalog = json.loads((DATA_ROOT / "item_catalog.json").read_text(encoding="utf-8"))
    catalog["items"][0]["category"] = "relic"
    catalog["items"][0]["rarity"] = "mythic"
    path = tmp_path / "campaign_values_catalog.json"
    path.write_text(json.dumps(catalog), encoding="utf-8")

    items = load_item_catalog(path, tmp_path / "images")

    assert items[0].category == "relic"
    assert items[0].rarity == "mythic"


def test_duplicate_item_ids_are_rejected(tmp_path: Path) -> None:
    catalog = json.loads((DATA_ROOT / "item_catalog.json").read_text(encoding="utf-8"))
    catalog["items"].append(catalog["items"][0])
    path = tmp_path / "duplicate_catalog.json"
    path.write_text(json.dumps(catalog), encoding="utf-8")

    with pytest.raises(CatalogDataError, match="item ids must be unique"):
        load_item_catalog(path, tmp_path / "images")


def test_invalid_price_is_rejected(tmp_path: Path) -> None:
    catalog = json.loads((DATA_ROOT / "item_catalog.json").read_text(encoding="utf-8"))
    catalog["items"][0]["base_price"] = 0
    path = tmp_path / "invalid_price_catalog.json"
    path.write_text(json.dumps(catalog), encoding="utf-8")

    with pytest.raises(CatalogDataError, match="base_price"):
        load_item_catalog(path, tmp_path / "images")


def test_missing_item_image_uses_fallback(tmp_path: Path) -> None:
    catalog = json.loads((DATA_ROOT / "item_catalog.json").read_text(encoding="utf-8"))
    catalog["items"][0]["image"] = "missing-image.png"
    path = tmp_path / "missing_image_catalog.json"
    path.write_text(json.dumps(catalog), encoding="utf-8")

    items = load_item_catalog(path, tmp_path / "images")

    assert items[0].image is None


def test_image_paths_cannot_escape_asset_directory(tmp_path: Path) -> None:
    catalog = json.loads((DATA_ROOT / "item_catalog.json").read_text(encoding="utf-8"))
    catalog["items"][0]["image"] = "../outside.png"
    path = tmp_path / "unsafe_image_catalog.json"
    path.write_text(json.dumps(catalog), encoding="utf-8")

    with pytest.raises(CatalogDataError, match="relative path"):
        load_item_catalog(path, tmp_path / "images")


def test_sample_characters_load() -> None:
    characters = load_characters(DATA_ROOT / "characters.json", CHARACTER_ASSET_ROOT)

    assert len(characters) == 3
    assert all(character.name and character.class_label for character in characters)


def test_imported_catalog_works_for_app_listings_and_filters(tmp_path: Path) -> None:
    from app import create_app
    from config import Settings
    from services.category_taxonomy import load_category_filters, resolve_category_filter
    from services.listing_service import create_player_listing, get_marketplace

    additional_path = tmp_path / "imported.json"
    additional_path.write_text(json.dumps({"items": [{
        "id": "srd-2024_test-battleaxe",
        "name": "Imported Battleaxe",
        "category": "weapon",
        "rarity": "common",
        "base_price": "10.00",
        "description": "Imported weapon.",
        "properties": {"source_document": {"key": "srd-2024"}},
        "tags": ["weapon:martial_melee", "weapon:versatile"],
    }]}), encoding="utf-8")
    app = create_app(Settings(database_path=tmp_path / "market.db", additional_catalog_path=additional_path))
    items = {item.id: item for item in app.server.config["AUCTION_HOUSE_ITEMS"]}
    sessions = app.server.config["AUCTION_HOUSE_SESSION_FACTORY"]
    assert len(items) == 9
    assert items["srd-2024_test-battleaxe"].base_price == 10
    assert "ironbound-shortsword" in items
    listing_id = create_player_listing(sessions, items, "mira-coppervale", "srd-2024_test-battleaxe", 1, "12.50", 14)
    taxonomy = load_category_filters(DATA_ROOT / "marketplace_filters.json")
    selection = resolve_category_filter(taxonomy, "weapons.martial-melee.versatile")
    results = get_marketplace(sessions, items, filter_selection=selection)
    assert any(listing.id == listing_id for listing in results.listings)