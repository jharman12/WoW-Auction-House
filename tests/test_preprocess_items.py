import io
import json

import pytest

import preProcessItems as processor
from services.catalog_service import CatalogItem


def source_item(publisher="Wizards of the Coast", cost="25.00"):
    return {
        "key": "srd-2024_test-item",
        "name": "Test Item",
        "cost": cost,
        "document": {"publisher": {"name": publisher}},
    }


def model_item():
    return {
        "id": "model-invented-id",
        "name": "Model Name",
        "category": "adventuring_gear",
        "rarity": "common",
        "base_price": 999,
        "description": "Test description.",
        "image": None,
        "properties": {},
        "tags": [],
        "enabled": True,
    }


def test_exact_publisher_filter_and_missing_publisher():
    assert processor.is_wotc_item(source_item())
    assert not processor.is_wotc_item(source_item("Other Publisher"))
    assert not processor.is_wotc_item({"document": None})
    with pytest.raises(ValueError, match="Only Wizards"):
        processor.convert_item(source_item("Other Publisher"))


@pytest.mark.parametrize("cost, expected, enabled", [("25.00", "25.00", True), ("0", "1", False), (None, "1", False)])
def test_structured_request_validates_and_preserves_source_values(monkeypatch, cost, expected, enabled):
    def fake_request(request, timeout):
        payload = json.loads(request.data)
        assert request.full_url == "http://localhost:11434/api/chat"
        assert payload["model"] == "qwen3.5:4b"
        assert payload["stream"] is False
        assert payload["format"] == CatalogItem.model_json_schema()
        assert json.loads(payload["messages"][1]["content"])["key"] == "srd-2024_test-item"
        assert timeout == 300
        return io.StringIO(json.dumps({"message": {"content": json.dumps(model_item())}}))

    monkeypatch.setattr(processor, "urlopen", fake_request)
    converted = processor.convert_item(source_item(cost=cost))
    assert converted.id == "srd-2024_test-item"
    assert converted.name == "Test Item"
    assert str(converted.base_price) == expected
    assert converted.enabled is enabled
    if not enabled:
        assert converted.properties["price_needs_review"] is True


def test_run_filters_and_resumes_without_resending_saved_items(tmp_path, monkeypatch):
    source_path = tmp_path / "source.json"
    output_path = tmp_path / "converted.json"
    source_path.write_text(json.dumps({"items": [source_item(), source_item("Other Publisher")]}), encoding="utf-8")
    calls = []

    def fake_convert(item, *args):
        calls.append(item["key"])
        result = model_item()
        result["id"] = item["key"]
        result["tags"] = ["utility"]
        return CatalogItem.model_validate(result)

    monkeypatch.setattr(processor, "convert_item", fake_convert)
    monkeypatch.setattr("sys.argv", ["preProcessItems.py", "--input", str(source_path), "--output", str(output_path)])
    processor.main()
    processor.main()
    assert calls == ["srd-2024_test-item"]
    assert len(json.loads(output_path.read_text(encoding="utf-8"))["items"]) == 1


@pytest.mark.parametrize("existing", [False, True])
def test_tagless_items_are_skipped_and_not_reprocessed(tmp_path, monkeypatch, existing):
    source_path = tmp_path / "source.json"
    output_path = tmp_path / "converted.json"
    source_path.write_text(json.dumps({"items": [source_item()]}), encoding="utf-8")
    result = model_item()
    result["id"] = source_item()["key"]
    result["tags"] = [" "]
    if existing:
        output_path.write_text(json.dumps({"items": [result]}), encoding="utf-8")
    calls = []

    def fake_convert(item, *args):
        calls.append(item["key"])
        return CatalogItem.model_validate(result)

    monkeypatch.setattr(processor, "convert_item", fake_convert)
    monkeypatch.setattr("sys.argv", ["preProcessItems.py", "--input", str(source_path), "--output", str(output_path)])
    processor.main()
    processor.main()
    assert calls == ([] if existing else [source_item()["key"]])
    assert json.loads(output_path.read_text(encoding="utf-8"))["items"] == []
    assert json.loads(output_path.with_suffix(".skipped.json").read_text(encoding="utf-8"))["skipped_ids"] == [source_item()["key"]]