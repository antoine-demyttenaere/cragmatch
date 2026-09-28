import voyageai
from sqlalchemy.orm import joinedload

from app.config import settings
from app.database import SessionLocal
from app.models import Sector

voyage = voyageai.Client(api_key=settings.voyage_api_key)

# Illustrative notes for testing fuzzy search, not verified beta.
NOTES = {
    "Can Marges": "Popular, well-bolted sport wall with a short 5-minute approach from the parking. Can get crowded on weekends.",
    "Siuranella": "Long orange limestone wall with lots of mid-grade routes. 15-minute walk, sunny in the afternoon, great in winter.",
    "El Pati": "Home of the legendary La Rambla. Steep, serious atmosphere, for strong climbers. Busy with visiting pros.",
    "Camp de Tir": "Pocketed conglomerate right next to the road, almost no approach. Shady in the morning, good for a quick session.",
    "Regall": "Overhanging conglomerate caves with powerful, pumpy routes. 20-minute walk up a steep path. Stays dry in light rain.",
    "Poble": "Easy-going crag just above the village, 5 minutes from the car. Family-friendly base with flat ground, good for beginners and kids.",
    "Agulles": "Adventurous traditional climbing on Montserrat's conglomerate needles. Long approach, sparse protection, quiet and remote.",
    "Collbató": "Sunny south-facing slabs and walls above Collbató, short approach. Technical, vertical climbing, can be hot in summer.",
    "Roca Regina": "Tall grey limestone above the Noguera Pallaresa river, 10-minute approach. Shaded most of the day, good in summer.",
    "Paretot": "Steep, athletic limestone for strong climbers. Short but steep uphill approach. Quiet midweek.",
    "Aombra": "Shady, sheltered sector with moderate routes, 10 minutes from the car. Cool in summer, usually uncrowded.",
    "Congost": "Big limestone gorge walls in the Montsec, long multi-bolt routes. 30-minute approach, peaceful and remote.",
    "Serrat": "Relaxed sunny sector with plenty of moderate routes and a 10-minute approach. Quiet, good for a laid-back day.",
}


def build_text(sector: Sector) -> str:
    return f"{sector.name} at {sector.crag.name} in {sector.crag.region}. Style: {sector.style.value}. Grades: {sector.grade_min} to {sector.grade_max}. Approach: {sector.approach_notes}"


def main():
    db = SessionLocal()
    try:
        sectors = db.query(Sector).options(joinedload(Sector.crag)).all()

        # 1. Attach the notes
        for s in sectors:
            s.approach_notes = NOTES.get(s.name)

        # 2. Embed all texts in ONE API call (a list in, a list out, same order)
        texts = [build_text(s) for s in sectors]
        result = voyage.embed(texts, model="voyage-3.5", input_type="document")

        # 3. loop over sectors and result.embeddings together (zip),
        #    assigning each vector to sector.embedding. Then db.commit().
        for sector, embedding in zip(sectors, result.embeddings):
            sector.embedding = embedding
        db.commit()
    finally:
        db.close()


if __name__ == "__main__":
    main()
