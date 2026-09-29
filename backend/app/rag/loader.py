from typing import Iterator

from langchain_core.document_loaders import BaseLoader
from langchain_core.documents import Document
from sqlalchemy.orm import Session, joinedload

from app.models import Sector
from app.scripts.embed_sectors import build_text


class SectorLoader(BaseLoader):
    """Loads every sector from Postgres as a LangChain Document."""

    def __init__(self, db: Session):
        self.db = db

    def lazy_load(self) -> Iterator[Document]:
        sectors = self.db.query(Sector).options(joinedload(Sector.crag)).order_by(Sector.id).all()
        for sector in sectors:
            yield Document(
                # The text that will be embedded: exactly the same string
                # as Stage 3's embed_sectors.py produces.
                page_content=build_text(sector),
                # Not embedded. Travels alongside the text, so after a
                # search we know which sector a Document came from.
                metadata={
                    "sector_id": sector.id,
                    "name": sector.name,
                    "crag": sector.crag.name,
                    "style": sector.style.value,
                    "grade_min": sector.grade_min,
                    "grade_max": sector.grade_max,
                },
            )
