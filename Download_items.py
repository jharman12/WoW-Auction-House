
import json
import requests
from pathlib import Path
from datetime import datetime, timezone

BASE_URL = "https://api.open5e.com/v2"

OUTPUT_DIR = Path("output")
OUTPUT_DIR.mkdir(exist_ok=True)

OUTPUT_FILE = OUTPUT_DIR / "dnd_items.json"

# Endpoints to download
ENDPOINTS = {
    "mundane": f"{BASE_URL}/items/",
    "magic": f"{BASE_URL}/magicitems/",
}


def download_items(endpoint_name, url):
    """Download every page from an Open5e endpoint."""

    session = requests.Session()

    all_items = []
    params = {"limit": 100}

    print(f"\nDownloading {endpoint_name} items...")

    while url:
        response = session.get(
            url,
            params=params,
            timeout=100
        )

        response.raise_for_status()

        data = response.json()

        results = data.get("results", [])

        # Keep track of which endpoint supplied the item
        for item in results:
            item["_resource_type"] = endpoint_name

        all_items.extend(results)

        print(
            f"Retrieved {len(results)} items | "
            f"Total: {len(all_items)}"
        )

        # Follow pagination
        url = data.get("next")

        # Parameters are already included in next URL
        params = None

    print(f"Finished {endpoint_name}: {len(all_items)} items")

    return all_items


def main():
    all_items = []

    for name, endpoint in ENDPOINTS.items():
        items = download_items(name, endpoint)
        all_items.extend(items)

    # Remove duplicate records by resource type + unique key
    unique_items = {}
    for item in all_items:
        identifier = (
            item["_resource_type"],
            item.get("key")
        )

        unique_items[identifier] = item

    final_items = list(unique_items.values())

    output = {
        "metadata": {
            "source": "Open5e API",
            "downloaded_at": datetime.now(
                timezone.utc
            ).isoformat(),
            "total_items": len(final_items)
        },
        "items": final_items
    }

    # Save JSON
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(
            output,
            f,
            indent=2,
            ensure_ascii=False
        )

    print("\n------------------------------")
    print("Download complete!")
    print(f"Total items: {len(final_items)}")
    print(f"Saved to: {OUTPUT_FILE}")
    print("------------------------------")


if __name__ == "__main__":
    main()
