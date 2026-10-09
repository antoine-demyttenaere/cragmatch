from typing import Iterator

from langchain_core.document_loaders import BaseLoader
from langchain_core.documents import Document
from sqlalchemy.orm import Session, joinedload

from app.models import Sector


def build_text(sector: Sector) -> str:
    return f"{sector.name} at {sector.crag.name} in {sector.crag.region}. Style: {sector.style.value}. Grades: {sector.grade_min} to {sector.grade_max}. Approach: {sector.approach_notes}"


class SectorLoader(BaseLoader):
    """Loads every sector from Postgres as a LangChain Document."""

    def __init__(self, db: Session):
        self.db = db

    def lazy_load(self) -> Iterator[Document]:
        sectors = self.db.query(Sector).options(joinedload(Sector.crag)).order_by(Sector.id).all()
        for sector in sectors:
            yield Document(
                # The text that will be embedded: changing build_text() means
                # re-running index_sectors_langchain.
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
