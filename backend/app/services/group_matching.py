"""Pure group-matching logic: no database, no HTTP.

Everything here only reads attributes from the objects it's given, so it
works with Member/Sector rows in the app and with plain stand-ins in tests
(and, in Stage 6, can be called as an agent tool).

Two ways to combine a group's preferences:
- merge_preferences(): STRICT. One set of filters every member accepts
  (the intersection), or a clear "no common ground" result.
- score_sectors(): SCORED. Every sector gets a fit count and, for each
  member it doesn't fit, a short reason ("too easy", "too far (...)").
"""

from dataclasses import dataclass, field
from typing import Literal, Protocol, Sequence

from app.services.geo import haversine_km
from app.services.grades import GRADE_ORDER, grade_rank, ranges_overlap

# What "a sector fits a member" means for grades:
#   overlap: the sector has at least some routes in the member's range
#   cover:   the sector's range contains the member's whole range
FitMode = Literal["overlap", "cover"]


class Preferences(Protocol):
    """Anything shaped like a Member: the Member model, or a test stand-in."""
    name: str
    grade_min: str | None
    grade_max: str | None
    max_distance_km: float | None
    styles: list[str]


# --- Strict mode: merge ---------------------------------------------------


@dataclass
class SearchFilters:
    grade_min: str
    grade_max: str
    max_distance_km: float | None  # None = no distance limit
    styles: list[str] | None       # None = any style


@dataclass
class MergeResult:
    filters: SearchFilters | None  # None when there's no common ground
    conflicts: list[str] = field(default_factory=list)

    @property
    def common_ground(self) -> bool:
        return self.filters is not None


def merge_preferences(members: Sequence[Preferences]) -> MergeResult:
    """Intersect everyone's preferences into one set of search filters.

    A member who hasn't set something doesn't restrict it. If the group
    can't agree, return every conflict in words instead of raising: "no
    common ground" is a normal answer for a group, not an error.
    """
    conflicts: list[str] = []

    # Grades: the overlap is [hardest minimum, easiest maximum].
    graded = [m for m in members if m.grade_min is not None and m.grade_max is not None]
    grade_min, grade_max = GRADE_ORDER[0], GRADE_ORDER[-1]
    if graded:
        hardest_min = max(graded, key=lambda m: grade_rank(m.grade_min))
        easiest_max = min(graded, key=lambda m: grade_rank(m.grade_max))
        grade_min, grade_max = hardest_min.grade_min, easiest_max.grade_max
        if grade_rank(grade_min) > grade_rank(grade_max):
            conflicts.append(
                f"No grade everyone climbs: {hardest_min.name} wants {hardest_min.grade_min} or harder, "
                f"but {easiest_max.name} wants {easiest_max.grade_max} or easier."
            )

    # Distance: the strictest limit anyone set.
    limits = [m.max_distance_km for m in members if m.max_distance_km is not None]
    max_distance_km = min(limits) if limits else None

    # Styles: the ones every member with a style preference accepts.
    # An empty list means "anything", so those members are skipped.
    picky = [m for m in members if m.styles]
    styles: list[str] | None = None
    if picky:
        common = set(picky[0].styles).intersection(*(m.styles for m in picky[1:]))
        # Keep the first member's order, so the result is predictable.
        styles = [s for s in picky[0].styles if s in common]
        if not styles:
            wanted = "; ".join(f"{m.name}: {', '.join(m.styles)}" for m in picky)
            conflicts.append(f"No style everyone accepts ({wanted}).")

    if conflicts:
        return MergeResult(filters=None, conflicts=conflicts)
    return MergeResult(filters=SearchFilters(grade_min, grade_max, max_distance_km, styles))


# --- Scored mode ----------------------------------------------------------


@dataclass
class Misfit:
    name: str
    reason: str


@dataclass
class SectorFit:
    sector: object  # a Sector row (or a stand-in with the same attributes)
    distance_km: float
    fits: list[str] = field(default_factory=list)
    misfits: list[Misfit] = field(default_factory=list)

    @property
    def fit_count(self) -> int:
        return len(self.fits)


def _style_value(style) -> str:
    # Sector.style is a ClimbingStyle enum in the app, a plain str in tests.
    return getattr(style, "value", style)


def why_not(sector, distance_km: float, member: Preferences, fit: FitMode) -> str | None:
    """None if the sector fits this member, otherwise a short reason.

    Several problems are joined ("too hard, too far (112 km > 80 km)").
    """
    reasons: list[str] = []

    if member.grade_min is not None and member.grade_max is not None:
        s_min, s_max = grade_rank(sector.grade_min), grade_rank(sector.grade_max)
        m_min, m_max = grade_rank(member.grade_min), grade_rank(member.grade_max)
        if s_max < m_min:
            reasons.append("too easy")
        elif s_min > m_max:
            reasons.append("too hard")
        elif fit == "cover" and not (s_min <= m_min and s_max >= m_max):
            # Overlaps, but doesn't contain the member's whole range.
            reasons.append(f"only covers part of {member.grade_min}–{member.grade_max}")

    if member.max_distance_km is not None and distance_km > member.max_distance_km:
        reasons.append(f"too far ({distance_km:.0f} km > {member.max_distance_km:.0f} km)")

    style = _style_value(sector.style)
    if member.styles and style not in member.styles:
        reasons.append(f"wrong style ({style})")

    return ", ".join(reasons) or None


def score_sectors(
    sectors: Sequence,
    members: Sequence[Preferences],
    fit: FitMode,
    origin: tuple[float, float],
) -> list[SectorFit]:
    """Score every sector against every member, best first.

    Ranking: most members fitted first; ties broken by distance (closest
    first), then by name so the order is always the same.
    """
    results = []
    for s in sectors:
        distance = haversine_km(s.crag.latitude, s.crag.longitude, *origin)
        scored = SectorFit(sector=s, distance_km=distance)
        for m in members:
            reason = why_not(s, distance, m, fit)
            if reason is None:
                scored.fits.append(m.name)
            else:
                scored.misfits.append(Misfit(m.name, reason))
        results.append(scored)

    results.sort(key=lambda r: (-r.fit_count, r.distance_km, r.sector.name))
    return results
