"""Group search: glue between the pure matching logic and the database.

group_matching.py decides WHO a sector fits; this module fetches the
sectors and packages the answer. Kept apart so the matching stays pure
(no DB) and easy to unit-test.
"""

from typing import Literal, Sequence

from sqlalchemy.orm import Session, joinedload

from app.models import Sector
from app.schemas.group import GroupSearchResponse, GroupSectorMatch, MemberMisfit, MergedFilters
from app.services.geo import BARCELONA
from app.services.group_matching import (
    FitMode,
    Preferences,
    SectorFit,
    merge_preferences,
    score_sectors,
)
from app.services.search import find_matching_sectors

SearchMode = Literal["strict", "scored"]


def _to_match(fit: SectorFit, member_count: int) -> GroupSectorMatch:
    return GroupSectorMatch(
        sector=fit.sector,
        distance_km=round(fit.distance_km, 1),
        fit_count=fit.fit_count,
        member_count=member_count,
        fits=fit.fits,
        misfits=[MemberMisfit(name=m.name, reason=m.reason) for m in fit.misfits],
    )


def search_for_group(
    db: Session,
    members: Sequence[Preferences],
    mode: SearchMode,
    fit: FitMode,
) -> GroupSearchResponse:
    base = {"mode": mode, "fit": fit, "member_count": len(members)}

    if not members:
        return GroupSearchResponse(
            **base, common_ground=False, message="Add at least one member to search.", results=[]
        )

    if mode == "strict":
        merged = merge_preferences(members)
        if not merged.common_ground:
            return GroupSearchResponse(
                **base, common_ground=False, message=" ".join(merged.conflicts), results=[]
            )

        f = merged.filters
        # Reuse the Stage 1 search for grade range + distance...
        candidates = find_matching_sectors(
            db, f.grade_min, f.grade_max, style=None,
            origin_lat=BARCELONA[0], origin_lon=BARCELONA[1], max_distance_km=f.max_distance_km,
        )
        # ...and filter the styles here, since it takes only one style.
        if f.styles is not None:
            candidates = [s for s in candidates if s.style.value in f.styles]

        # Scoring the candidates gives strict results the same shape as scored
        # ones. With fit="overlap" every candidate fits everyone already; with
        # fit="cover" this also drops sectors that only partly cover someone.
        scored = [r for r in score_sectors(candidates, members, fit, BARCELONA) if r.fit_count == len(members)]
        return GroupSearchResponse(
            **base,
            common_ground=True,
            message=None if scored else "The group agrees on filters, but no sector matches them.",
            filters=MergedFilters(
                grade_min=f.grade_min, grade_max=f.grade_max,
                max_distance_km=f.max_distance_km, styles=f.styles,
            ),
            results=[_to_match(r, len(members)) for r in scored],
        )

    # Scored mode: every sector, ranked by how many members it fits.
    sectors = db.query(Sector).options(joinedload(Sector.crag)).all()
    scored = score_sectors(sectors, members, fit, BARCELONA)
    return GroupSearchResponse(
        **base,
        common_ground=any(r.fit_count == len(members) for r in scored),
        results=[_to_match(r, len(members)) for r in scored],
    )
