from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.dependencies import get_db
from app.models import Group, Member, Sector, StayType
from app.routers.sectors import load_sector
from app.schemas.group import (
    GroupCreate,
    GroupRead,
    GroupSearchResponse,
    MemberCreate,
    MemberRead,
)
from app.schemas.stay import BookingLinks, GroupStaysResponse, NearbyStay
from app.services.group_matching import FitMode
from app.services.group_search import SearchMode, search_for_group
from app.services.groups import find_group, generate_share_code
from app.services.stays import airbnb_url, booking_url, find_stays_near, next_saturday

router = APIRouter()


def get_group(code: str, db: Session = Depends(get_db)) -> Group:
    """Dependency: load the group named by {code} in the path, or 404.

    Any endpoint that declares `group: Group = Depends(get_group)` gets the
    loaded group, and never runs at all if the code doesn't exist.
    """
    group = find_group(db, code)
    if group is None:
        raise HTTPException(status_code=404, detail="Group not found")
    return group


def get_member(member_id: int, group: Group = Depends(get_group)) -> Member:
    """Dependency: a member of *this* group, or 404.

    Looking the member up inside group.members (not by id alone) is what
    stops someone with group A's code from editing a member of group B.
    """
    for member in group.members:
        if member.id == member_id:
            return member
    raise HTTPException(status_code=404, detail="Member not found in this group")


@router.post("/", response_model=GroupRead, status_code=201, summary="Create a group")
def create_group(body: GroupCreate, db: Session = Depends(get_db)):
    group =Group(name=body.name, share_code=generate_share_code(db))
    db.add(group)
    db.commit()
    db.refresh(group)
    return group


@router.get("/{code}", response_model=GroupRead, summary="Get a group and its members")
def read_group(group: Group = Depends(get_group)):
    return group


@router.post(
    "/{code}/members",
    response_model=MemberRead,
    status_code=201,
    summary="Add a member with their preferences",
)
def add_member(body: MemberCreate, group: Group = Depends(get_group), db: Session = Depends(get_db)):
    # model_dump() already has styles as plain strings (use_enum_values),
    # ready for the ARRAY(String) column. group=group fills in group_id.
    member = Member(**body.model_dump(), group=group)
    db.add(member)
    db.commit()
    db.refresh(member)
    return member


@router.put(
    "/{code}/members/{member_id}",
    response_model=MemberRead,
    summary="Replace a member's name and preferences",
)
def update_member(body: MemberCreate, member: Member = Depends(get_member), db: Session = Depends(get_db)):
    # PUT = full replacement: every field comes from the body, including
    # clearing preferences back to None / [].
    for field, value in body.model_dump().items():
        setattr(member, field, value)
    db.commit()
    db.refresh(member)
    return member


@router.delete("/{code}/members/{member_id}", status_code=204, summary="Remove a member")
def delete_member(member: Member = Depends(get_member), db: Session = Depends(get_db)):
    db.delete(member)
    db.commit()


@router.get(
    "/{code}/search",
    response_model=GroupSearchResponse,
    summary="Find sectors for the whole group",
    description=(
        "strict: only sectors that satisfy every member (merged preferences). "
        "scored: every sector, ranked by how many members it fits, with the "
        "reason it doesn't fit the others. `fit` decides what 'fits' means for "
        "grades: `overlap` (the sector has some routes in the member's range) "
        "or `cover` (the sector covers the member's whole range)."
    ),
)
def search_group(
    mode: SearchMode = Query("scored"),
    fit: FitMode = Query("overlap"),
    group: Group = Depends(get_group),
    db: Session = Depends(get_db),
):
    # Thin on purpose: all the logic lives in services/, where it's tested
    # directly and (in Stage 6) callable as an agent tool.
    return search_for_group(db, group.members, mode=mode, fit=fit)


@router.get(
    "/{code}/sectors/{sector_id}/stays",
    response_model=GroupStaysResponse,
    summary="Places to stay near a sector, for this group",
    description=(
        "Nearby stays plus prefilled Airbnb / Booking.com searches for the "
        "group's dates and size. guests defaults to the number of members."
    ),
)
def group_sector_stays(
    nights: int = Query(default=2, ge=1, le=30),
    guests: int | None = Query(default=None, ge=1, le=30),
    checkin: date | None = Query(default=None, description="Defaults to next Saturday."),
    type: StayType | None = Query(default=None),
    max_distance_km: float = Query(default=10, gt=0, le=50),
    group: Group = Depends(get_group),
    sector: Sector = Depends(load_sector),
    db: Session = Depends(get_db),
):
    guests = guests or max(len(group.members), 1)
    checkin = checkin or next_saturday()
    if checkin < date.today():
        raise HTTPException(status_code=422, detail="checkin can't be in the past")
    checkout = checkin + timedelta(days=nights)

    crag = sector.crag
    nearby = find_stays_near(
        db, crag.latitude, crag.longitude, max_distance_km,
        stay_type=type.value if type else None,
    )
    return GroupStaysResponse(
        sector_id=sector.id,
        sector_name=sector.name,
        crag_name=crag.name,
        guests=guests,
        checkin=checkin,
        checkout=checkout,
        stays=[NearbyStay(stay=stay, distance_km=round(d, 1)) for stay, d in nearby],
        links=BookingLinks(
            airbnb=airbnb_url(crag.latitude, crag.longitude, checkin, checkout, guests),
            booking=booking_url(crag.name, crag.latitude, crag.longitude, checkin, checkout, guests),
        ),
    )
