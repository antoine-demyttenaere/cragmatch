# French climbing grades, lowest to highest.
# Below 6: plain number + optional "+", no letter (matches your seed
# data — Montserrat's Agulles uses "4", Margalef's Poble uses "5+").
# From 6 up: number + letter (a/b/c) + optional "+".
GRADE_ORDER: list[str] = []

# TODO: build the 1-5 range. For n in 1..5, append str(n), then f"{n}+"
for n in range(1, 6):
    GRADE_ORDER.append(str(n))
    GRADE_ORDER.append(f"{n}+")

# TODO: build the 6-9 range. For n in 6..9, for each letter in "abc",
# append f"{n}{letter}", then f"{n}{letter}+"
for n in range(6, 10):
    for letter in "abc":
        GRADE_ORDER.append(f"{n}{letter}")
        GRADE_ORDER.append(f"{n}{letter}+")


def grade_rank(grade: str) -> int:
    """Return this grade's position in GRADE_ORDER (0 = easiest).
    Raises ValueError for anything not in the list."""

    return GRADE_ORDER.index(grade)


def ranges_overlap(a_min: str, a_max: str, b_min: str, b_max: str) -> bool:
    """Do grade range [a_min, a_max] and [b_min, b_max] overlap at all?"""
    return grade_rank(a_min) <= grade_rank(b_max) and grade_rank(b_min) <= grade_rank(a_max)
