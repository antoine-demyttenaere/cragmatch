from app.agent.state import Approval
from app.scripts.trip_planner import describe_update, format_plan, run_planner

AGREEING = [
    {"name": "Ana", "grade_min": "6a", "grade_max": "7a"},
    {"name": "Marc", "grade_min": "6b", "grade_max": "7b"},
]
DISAGREEING = [
    {"name": "Ana", "grade_min": "5", "grade_max": "6a"},
    {"name": "Marc", "grade_min": "7a", "grade_max": "8a"},
]


def two_sectors(make_sector, make_stay):
    make_sector("Near", "6a", "7a")
    make_sector("Far", "6a", "7a", lat=41.26, lon=0.93, crag="Siurana")
    make_stay("Close", 41.61, 1.82)
    make_stay("Siurana camp", 41.27, 0.94)


def test_describe_update_lists_the_changed_fields():
    assert describe_update("merge_preferences", {"members": [], "filters": None}) == (
        "merge_preferences: members, filters"
    )


def test_describe_update_without_changes():
    assert describe_update("find_stays", {}) == "find_stays: (no change)"
    assert describe_update("find_stays", None) == "find_stays: (no change)"


def test_run_planner_approves_and_returns_a_plan(db_session, make_group, make_sector, make_stay):
    group = make_group(members=AGREEING)
    two_sectors(make_sector, make_stay)
    questions = []
    lines = []

    def ask(question):
        questions.append(question)
        return Approval(approved=True)

    state = run_planner(db_session, group.share_code, ask=ask, out=lines.append)

    assert state["plan"]["stays"]
    assert len(questions) == 1
    prefixes = [
        "merge_preferences:",
        "search_sectors:",
        "pick_sector:",
        "approve_sector: approved",
        "find_stays:",
        "propose_plan:",
    ]
    assert len(lines) == len(prefixes)
    assert all(line.startswith(prefix) for line, prefix in zip(lines, prefixes))


def test_run_planner_reject_then_approve_uses_the_second_sector(
    db_session, make_group, make_sector, make_stay
):
    group = make_group(members=AGREEING)
    two_sectors(make_sector, make_stay)
    answers = iter([Approval(approved=False, reason="too close"), Approval(approved=True)])

    state = run_planner(
        db_session, group.share_code, ask=lambda question: next(answers), out=lambda line: None
    )

    assert state["plan"]["sector"]["sector_name"] == "Far"


def test_run_planner_without_common_ground_never_asks(db_session, make_group):
    group = make_group(members=DISAGREEING)
    lines = []

    def ask(question):
        raise AssertionError("the group should not be asked")

    state = run_planner(db_session, group.share_code, ask=ask, out=lines.append)

    assert state.get("plan") is None
    assert "No grade everyone climbs" in state["message"]
    assert len(lines) == 2
    assert lines[0].startswith("merge_preferences:")
    assert lines[1].startswith("explain_conflicts:")


def test_format_plan_shows_links_or_the_message():
    plan = {
        "sector": {"sector_name": "Near", "crag_name": "Montserrat"},
        "checkin": "2026-11-07",
        "checkout": "2026-11-09",
        "nights": 2,
        "guests": 2,
        "stays": [{"stay": {"name": "Close", "type": "campsite"}, "distance_km": 1.2}],
        "links": {"airbnb": "https://airbnb.example/x", "booking": "https://booking.example/y"},
    }

    text = format_plan({"plan": plan})

    assert "Near (Montserrat)" in text
    assert "Close, campsite, 1.2 km" in text
    assert "https://airbnb.example/x" in text
    assert "https://booking.example/y" in text
    assert format_plan({"message": "No plan: nothing."}) == "No plan: nothing."
