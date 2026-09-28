# Importing every model here registers it on Base.metadata, and lets the
# rest of the app keep writing `from app.models import Crag, Sector`.
from app.models.crag import Crag
from app.models.sector import ClimbingStyle, Sector

__all__ = ["Crag", "Sector", "ClimbingStyle"]
