"""Unit tests for the pure group-matching logic (no database, no API).

merge_preferences() and score_sectors() only read attributes, so plain
dataclasses / SimpleNamespace objects stand in for Member and Sector rows.
"""

from dataclasses import dataclass, field
from types import SimpleNamespace

from app.services.group_matching import merge_preferences, score_sectors
from app.services.grades import GRADE_ORDER

BARCELONA = (41.3874, 2.1686)


@dataclass
class P:
    """A member's preferences, shaped like the Member model."""
    name: str
    grade_min: str | None = None
    grade_max: str | None = None
    max_distance_km: float | None = None
    styles: list[str] = field(default_factory=list)
    # Last, so existing tests that build P positionally keep working.
    max_approach_minutes: int | None = None


def sector(name, grade_min, grade_max, style="sport", lat=41.3874, lon=2.1686, approach=None):
    """A fake Sector. The default coordinates are Barcelona itself (0 km)."""
    return SimpleNamespace(
        name=name, grade_min=grade_min, grade_max=grade_max, style=style,
        approach_minutes=approach,
        crag=SimpleNamespace(latitude=lat, longitude=lon),
    )


# --- merge_preferences (strict mode) --------------------------------------


def test_merge_grade_range_is_the_overlap():
    result = merge_preferences([P("Ana", "6a", "7a"), P("Marc", "6b", "7b")])

    assert result.common_ground
    assert (result.filters.grade_min, result.filters.grade_max) == ("6b", "7a")


def test_merge_distance_is_the_smallest_limit():
    result = merge_preferences([P("Ana", max_distance_km=150), P("Marc", max_distance_km=90), P("Lia")])

    assert result.filters.max_distance_km == 90


def test_merge_approach_is_the_smallest_limit():
    result = merge_preferences([
        P("Ana", max_approach_minutes=15), P("Ben", max_approach_minutes=30), P("Lia"),
    ])

    assert result.filters.max_approach_minutes == 15


def test_merge_without_approach_limits_means_no_restriction():
    result = merge_preferences([P("Ana"), P("Ben")])

    assert result.common_ground
    assert result.filters.max_approach_minutes is None


def test_merge_styles_are_the_ones_everyone_accepts():
    result = merge_preferences([
        P("Ana", styles=["sport", "boulder"]),
        P("Marc", styles=["sport", "trad"]),
        P("Lia"),  # no styles = accepts anything, so she doesn't narrow it
    ])

    assert result.filters.styles == ["sport"]


def test_merge_with_no_grades_or_styles_means_no_restriction():
    result = merge_preferences([P("Ana"), P("Marc")])

    assert result.common_ground
    assert (result.filters.grade_min, result.filters.grade_max) == (GRADE_ORDER[0], GRADE_ORDER[-1])
    assert result.filters.max_distance_km is None
    assert result.filters.styles is None


def test_merge_one_member_is_just_their_preferences():
    result = merge_preferences([P("Ana", "5+", "6b", 80, ["sport"])])

    f = result.filters
    assert (f.grade_min, f.grade_max, f.max_distance_km, f.styles) == ("5+", "6b", 80, ["sport"])


def test_merge_identical_preferences():
    ana, marc = P("Ana", "6a", "7a", 100, ["sport"]), P("Marc", "6a", "7a", 100, ["sport"])

    f = merge_preferences([ana, marc]).filters

    assert (f.grade_min, f.grade_max, f.max_distance_km, f.styles) == ("6a", "7a", 100, ["sport"])


def test_merge_ranges_that_only_touch_still_overlap():
    result = merge_preferences([P("Ana", "5+", "6a"), P("Marc", "6a", "7a")])

    assert (result.filters.grade_min, result.filters.grade_max) == ("6a", "6a")


def test_merge_no_grade_overlap_is_a_result_not_an_error():
    result = merge_preferences([P("Ana", "5", "6a"), P("Marc", "7a", "8a")])

    assert not result.common_ground
    assert result.filters is None
    # The message names who clashes, so the group knows what to discuss.
    assert len(result.conflicts) == 1
    assert "Marc" in result.conflicts[0] and "Ana" in result.conflicts[0]


def test_merge_no_common_style():
    result = merge_preferences([P("Ana", styles=["sport"]), P("Marc", styles=["trad"])])

    assert not result.common_ground
    assert "style" in result.conflicts[0].lower()


def test_merge_reports_every_conflict_at_once():
    result = merge_preferences([
        P("Ana", "5", "6a", styles=["sport"]),
        P("Marc", "7a", "8a", styles=["trad"]),
    ])

    assert len(result.conflicts) == 2


def test_merge_empty_group_has_no_restrictions():
    # Merging nobody's preferences restricts nothing. Whether an empty group
    # may search at all is the endpoint's decision, not this function's.
    result = merge_preferences([])

    assert result.common_ground
    assert result.filters.styles is None


# --- score_sectors (scored mode) ------------------------------------------


def test_score_counts_fits_and_explains_misfits():
    members = [P("Ana", "6a", "7a"), P("Marc", "7c", "8b")]

    [result] = score_sectors([sector("Poble", "5+", "6c")], members, fit="overlap", origin=BARCELONA)

    assert result.fits == ["Ana"]
    assert [(m.name, m.reason) for m in result.misfits] == [("Marc", "too easy")]
    assert result.fit_count == 1


def test_score_too_hard_too_far_and_wrong_style():
    siurana = sector("El Pati", "7a", "9a+", style="sport", lat=41.2436, lon=0.9186)  # 106 km
    members = [
        P("Ana", "5", "6b"),
        P("Marc", max_distance_km=50),
        P("Lia", styles=["trad"]),
    ]

    [result] = score_sectors([siurana], members, fit="overlap", origin=BARCELONA)

    reasons = {m.name: m.reason for m in result.misfits}
    assert reasons["Ana"] == "too hard"
    assert reasons["Marc"].startswith("too far")
    assert reasons["Lia"] == "wrong style (sport)"


def test_score_member_without_preferences_fits_everything():
    [result] = score_sectors([sector("Any", "4", "9a")], [P("Lia")], fit="overlap", origin=BARCELONA)

    assert result.fits == ["Lia"]


def test_score_approach_too_long_is_a_misfit():
    [result] = score_sectors(
        [sector("Congost", "6a", "7a", approach=30)], [P("Ana", max_approach_minutes=15)],
        fit="overlap", origin=BARCELONA,
    )

    assert [(m.name, m.reason) for m in result.misfits] == [("Ana", "approach too long (30 min > 15 min)")]


def test_score_approach_equal_to_limit_fits():
    [result] = score_sectors(
        [sector("Edge", "6a", "7a", approach=15)], [P("Ana", max_approach_minutes=15)],
        fit="overlap", origin=BARCELONA,
    )

    assert result.fits == ["Ana"]


def test_score_unknown_approach_fits_everyone():
    [result] = score_sectors(
        [sector("El Pati", "6a", "7a", approach=None)], [P("Ana", max_approach_minutes=5)],
        fit="overlap", origin=BARCELONA,
    )

    assert result.fits == ["Ana"]


def test_score_member_without_approach_limit_fits_long_approach():
    [result] = score_sectors(
        [sector("Agulles", "6a", "7a", approach=45)], [P("Ana")], fit="overlap", origin=BARCELONA,
    )

    assert result.fits == ["Ana"]


def test_score_overlap_vs_cover_fit_modes():
    # The sector touches Ana's range (overlap) but doesn't contain all of it (cover).
    members = [P("Ana", "6a", "7a")]
    s = sector("Partial", "6c", "8a")

    [overlap] = score_sectors([s], members, fit="overlap", origin=BARCELONA)
    [cover] = score_sectors([s], members, fit="cover", origin=BARCELONA)

    assert overlap.fits == ["Ana"]
    assert cover.fits == []
    assert cover.misfits[0].reason.startswith("only covers part")


def test_score_ranks_by_fit_count_then_distance():
    members = [P("Ana", "6a", "7a"), P("Marc", "6a", "7a")]
    near_no_fit = sector("Near, 0 fits", "8a", "9a")
    far_all_fit = sector("Far, 2 fits", "6a", "7a", lat=42.0, lon=0.9)
    near_all_fit = sector("Near, 2 fits", "6a", "7a")

    # More fits always wins, even against a closer sector; distance only
    # breaks ties between sectors with the same fit count.
    results = score_sectors([near_no_fit, far_all_fit, near_all_fit], members, fit="overlap", origin=BARCELONA)

    assert [r.sector.name for r in results] == ["Near, 2 fits", "Far, 2 fits", "Near, 0 fits"]
