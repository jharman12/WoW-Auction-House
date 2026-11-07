import logging
from decimal import Decimal
from pathlib import Path, PurePosixPath
from typing import Any, TypeVar, cast

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator


logger = logging.getLogger(__name__)
ModelType = TypeVar("ModelType", bound=BaseModel)


class CatalogDataError(ValueError):
    """Raised when local catalog or character data is invalid."""


def _validate_relative_image_path(value: str | None) -> str | None:
    if value is None:
        return value
    path = PurePosixPath(value)
    if not value.strip() or path.is_absolute() or ".." in path.parts or "\\" in value:
        raise ValueError("image must be a non-empty relative path without parent traversal")
    return value


class CatalogItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]*$", max_length=80)
    name: str = Field(min_length=1, max_length=120)
    category: str = Field(pattern=r"^[a-z][a-z0-9_-]*$", max_length=40)
    rarity: str = Field(pattern=r"^[a-z][a-z0-9_-]*$", max_length=40)
    base_price: Decimal = Field(gt=Decimal("0"))
    description: str = Field(min_length=1, max_length=1000)
    image: str | None = Field(default=None, max_length=255)
    stackable: bool = False
    properties: dict[str, Any] = Field(default_factory=dict)
    tags: list[str] = Field(default_factory=list)
    enabled: bool = True

    @field_validator("image")
    @classmethod
    def validate_image(cls, value: str | None) -> str | None:
        return _validate_relative_image_path(value)


class ItemCatalogDocument(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[CatalogItem] = Field(min_length=1)

    @model_validator(mode="after")
    def require_unique_item_ids(self) -> "ItemCatalogDocument":
        ids = [item.id for item in self.items]
        if len(ids) != len(set(ids)):
            raise ValueError("item ids must be unique")
        return self


class CharacterDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=r"^[a-z0-9][a-z0-9_-]*$", max_length=64)
    name: str = Field(min_length=1, max_length=120)
    class_label: str = Field(min_length=1, max_length=80)
    description: str = Field(min_length=1, max_length=500)
    image: str | None = Field(default=None, max_length=255)

    @field_validator("image")
    @classmethod
    def validate_image(cls, value: str | None) -> str | None:
        return _validate_relative_image_path(value)


class CharacterDocument(BaseModel):
    model_config = ConfigDict(extra="forbid")

    characters: list[CharacterDefinition] = Field(min_length=1)

    @model_validator(mode="after")
    def require_unique_character_ids(self) -> "CharacterDocument":
        ids = [character.id for character in self.characters]
        if len(ids) != len(set(ids)):
            raise ValueError("character ids must be unique")
        return self


def _read_document(path: Path, model_type: type[ModelType], label: str) -> ModelType:
    try:
        return model_type.model_validate_json(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise CatalogDataError(f"Could not read {label} file '{path}': {exc}") from exc
    except ValidationError as exc:
        raise CatalogDataError(f"Invalid {label} file '{path}':\n{exc}") from exc


def _apply_image_fallback(
    entries: list[CatalogItem] | list[CharacterDefinition],
    asset_root: Path,
    label: str,
) -> list[CatalogItem] | list[CharacterDefinition]:
    root = asset_root.resolve()
    resolved_entries: list[CatalogItem] | list[CharacterDefinition] = []
    for entry in entries:
        if entry.image is None:
            resolved_entries.append(entry)
            continue

        image_path = (root / entry.image).resolve()
        if not image_path.is_relative_to(root):
            raise CatalogDataError(f"{label} '{entry.id}' image escapes the asset directory")
        if not image_path.is_file():
            logger.warning("Missing %s image '%s'; using the built-in placeholder", label, image_path)
            resolved_entries.append(entry.model_copy(update={"image": None}))
        else:
            resolved_entries.append(entry)
    return resolved_entries


def load_item_catalog(path: Path, asset_root: Path) -> list[CatalogItem]:
    document = _read_document(path, ItemCatalogDocument, "item catalog")
    entries = _apply_image_fallback(document.items, asset_root, "item")
    return cast(list[CatalogItem], entries)


def load_characters(path: Path, asset_root: Path) -> list[CharacterDefinition]:
    document = _read_document(path, CharacterDocument, "character catalog")
    entries = _apply_image_fallback(document.characters, asset_root, "character")
    return cast(list[CharacterDefinition], entries)