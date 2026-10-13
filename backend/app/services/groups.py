import secrets

from sqlalchemy.orm import Session, selectinload

from app.models import Group

# No 0/O or 1/I/L: codes are read out loud and typed on phones.
CODE_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
CODE_LENGTH = 8  # 31^8 ≈ 850 billion codes: guessing one is hopeless


def find_group(db: Session, code: str) -> Group | None:
    """The group with this share code (any case), members loaded, or None.

    None = no such group; the caller decides whether that's a 404 or a message.
    """
    return (
        db.query(Group)
        .options(selectinload(Group.members))
        .filter(Group.share_code == code.upper())
        .first()
    )


def generate_share_code(db: Session) -> str:
    """A random, unused share code.

    `secrets` (not `random`): random's output can be predicted after seeing
    enough of it, and the code is the group's only protection. The loop
    handles the (astronomically unlikely) collision; the unique index on
    groups.share_code is the final safety net.
    """
    while True:
        code = "".join(secrets.choice(CODE_ALPHABET) for _ in range(CODE_LENGTH))
        if db.query(Group).filter(Group.share_code == code).first() is None:
            return code
