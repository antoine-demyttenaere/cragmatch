# Importing every model here registers it on Base.metadata, and lets the
# rest of the app keep writing `from app.models import Crag, Sector`.
from app.models.crag import Crag
from app.models.sector import ClimbingStyle, Sector
from app.models.member import Member
from app.models.group import Group

__all__ = ["Crag", "Sector", "ClimbingStyle", "Member", "Group"]
