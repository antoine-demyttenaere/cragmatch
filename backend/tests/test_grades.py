import pytest

from app.grades import grade_rank, ranges_overlap, GRADE_ORDER
 

def test_grade_order_length():
    # 5 plain (1..5) x2 for the "+" variant, plus 4 lettered numbers (6..9)
    # x3 letters x2 for "+" = 10 + 24 = 34
    assert len(GRADE_ORDER) == 34


def test_basic_ordering():
    assert grade_rank("6a") < grade_rank("6a+") < grade_rank("6b")
    assert grade_rank("5+") < grade_rank("6a")
    assert grade_rank("8c") < grade_rank("8c+") < grade_rank("9a")


def test_invalid_grade_raises():
    with pytest.raises(ValueError):
        grade_rank("6z")


def test_ranges_overlap_true():
    # sector 7a-9a+ vs a search for 6a-7a: they touch at 7a
    assert ranges_overlap("7a", "9a+", "6a", "7a") is True


def test_ranges_overlap_false():
    # sector tops out below the search's minimum — no overlap
    assert ranges_overlap("5", "6a", "7a", "8a") is False


def test_ranges_overlap_search_range_inside_sector_range():
    assert ranges_overlap("5", "9c+", "6a", "6c") is True
