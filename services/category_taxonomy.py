from dataclasses import dataclass
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from services.catalog_service import CatalogDataError


class CategoryFilterNode(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=r"^[a-z0-9]+(?:[.-][a-z0-9]+)*$", max_length=120)
    label: str = Field(min_length=1, max_length=80)
    categories: list[str] = Field(default_factory=list)
    tag: str | None = Field(default=None, pattern=r"^[a-z0-9]+:[a-z0-9_]+$")
    children: list["CategoryFilterNode"] = Field(default_factory=list)


class CategoryFilterDocument(BaseModel):
    model_config = ConfigDict(extra="forbid")

    categories: list[CategoryFilterNode] = Field(min_length=1)

    @model_validator(mode="after")
    def require_unique_ids(self) -> "CategoryFilterDocument":
        identifiers: list[str] = []

        def collect(nodes: list[CategoryFilterNode]) -> None:
            for node in nodes:
                identifiers.append(node.id)
                collect(node.children)

        collect(self.categories)
        if len(identifiers) != len(set(identifiers)):
            raise ValueError("category filter ids must be unique")
        return self


@dataclass(frozen=True)
class CategoryFilterSelection:
    categories: tuple[str, ...]
    required_tags: tuple[str, ...]
    label_path: tuple[str, ...]


def load_category_filters(path: Path) -> CategoryFilterDocument:
    try:
        return CategoryFilterDocument.model_validate_json(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise CatalogDataError(f"Could not read marketplace filters '{path}': {exc}") from exc
    except ValidationError as exc:
        raise CatalogDataError(f"Invalid marketplace filters '{path}':\n{exc}") from exc


def resolve_category_filter(
    document: CategoryFilterDocument,
    filter_id: str | None,
) -> CategoryFilterSelection | None:
    if not filter_id or filter_id == "all":
        return None

    def find(
        nodes: list[CategoryFilterNode],
        inherited_categories: tuple[str, ...] = (),
        inherited_tags: tuple[str, ...] = (),
        inherited_labels: tuple[str, ...] = (),
    ) -> CategoryFilterSelection | None:
        for node in nodes:
            categories = tuple(node.categories) if node.categories else inherited_categories
            tags = inherited_tags + ((node.tag,) if node.tag else ())
            labels = inherited_labels + (node.label,)
            if node.id == filter_id:
                return CategoryFilterSelection(categories, tags, labels)
            found = find(node.children, categories, tags, labels)
            if found is not None:
                return found
        return None

    return find(document.categories)


def render_category_filter_tree(
    nodes: list[CategoryFilterNode],
    selected_id: str | None,
) -> list[object]:
    from dash import html

    rendered = []
    for node in nodes:
        selected = node.id == selected_id
        button = html.Button(
            node.label,
            id={"type": "market-category-filter", "filter_id": node.id},
            n_clicks=0,
            className="category-filter-button selected" if selected else "category-filter-button",
            title="Filter by this group",
            type="button",
        )
        children = []
        if node.children:
            children = render_category_filter_tree(node.children, selected_id)
            rendered.append(
                html.Details(
                    [
                        html.Summary(node.label, className="category-filter-summary"),
                        button,
                        html.Div(children, className="category-filter-children"),
                    ],
                    className="category-filter-node",
                )
            )
        else:
            rendered.append(html.Div(button, className="category-filter-leaf"))
    return rendered