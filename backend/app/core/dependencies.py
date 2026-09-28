from app.core.database import SessionLocal

def get_db():
    # This is a *generator* dependency: code before `yield` runs before
    # the endpoint, the yielded value is what the endpoint receives, and
    # code after `yield` runs after the endpoint finishes (even on error).
    # That's how you guarantee the session always gets closed.
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
