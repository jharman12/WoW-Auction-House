from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from database.models import Character
from services.catalog_service import CharacterDefinition


def sync_characters(
    characters: Sequence[CharacterDefinition],
    session_factory: sessionmaker[Session],
) -> None:
    active_ids = {character.id for character in characters}
    with session_factory.begin() as session:
        stored_characters = {
            character.id: character
            for character in session.scalars(select(Character)).all()
        }

        for definition in characters:
            stored = stored_characters.get(definition.id)
            if stored is None:
                stored = Character(id=definition.id, name=definition.name)
                session.add(stored)
            stored.name = definition.name
            stored.image_path = definition.image
            stored.description = definition.description
            stored.active = True

        for character_id, stored in stored_characters.items():
            if character_id not in active_ids:
                stored.active = False