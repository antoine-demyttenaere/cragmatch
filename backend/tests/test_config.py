import os

import pytest
from pydantic import ValidationError
from sqlalchemy.engine import make_url

from app.core.config import Settings, settings


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    # CI sets these; each test sets only what it needs.
    for name in list(os.environ):
        if name.startswith("CRAGMATCH_"):
            monkeypatch.delenv(name)


def set_keys(monkeypatch):
    monkeypatch.setenv("CRAGMATCH_ANTHROPIC_API_KEY", "anthropic-dummy")
    monkeypatch.setenv("CRAGMATCH_VOYAGE_API_KEY", "voyage-dummy")


def set_parts(monkeypatch, password="p", host="h"):
    monkeypatch.setenv("CRAGMATCH_POSTGRES_USER", "u")
    monkeypatch.setenv("CRAGMATCH_POSTGRES_PASSWORD", password)
    monkeypatch.setenv("CRAGMATCH_POSTGRES_DB", "d")
    if host:
        monkeypatch.setenv("CRAGMATCH_POSTGRES_HOST", host)
    monkeypatch.setenv("CRAGMATCH_POSTGRES_PORT", "5433")


def build() -> Settings:
    return Settings(_env_file=None)


def test_database_url_from_the_five_parts(monkeypatch):
    set_keys(monkeypatch)
    set_parts(monkeypatch)
    assert build().database_url == "postgresql+psycopg://u:p@h:5433/d"


def test_special_characters_in_the_password_survive(monkeypatch):
    set_keys(monkeypatch)
    set_parts(monkeypatch, password="p@ss:w/rd%#?")
    url = make_url(build().database_url)
    assert url.password == "p@ss:w/rd%#?"
    assert url.host == "h"


@pytest.mark.parametrize(
    "url",
    [
        "postgres://u:p@db.example:5432/app?sslmode=require",
        "postgresql://u:p@db.example:5432/app?sslmode=require",
    ],
    ids=["postgres", "postgresql"],
)
def test_postgres_url_wins_and_keeps_ssl(monkeypatch, url):
    set_keys(monkeypatch)
    set_parts(monkeypatch)
    monkeypatch.setenv("CRAGMATCH_POSTGRES_URL", url)
    assert (
        build().database_url
        == "postgresql+psycopg://u:p@db.example:5432/app?sslmode=require"
    )


def test_postgres_url_alone_is_enough(monkeypatch):
    set_keys(monkeypatch)
    monkeypatch.setenv("CRAGMATCH_POSTGRES_URL", "postgres://u:p@h:5432/d")
    s = build()
    assert s.postgres_user is None
    assert s.postgres_host is None
    assert s.postgres_port is None


def test_postgres_url_with_another_scheme_is_rejected(monkeypatch):
    set_keys(monkeypatch)
    monkeypatch.setenv("CRAGMATCH_POSTGRES_URL", "mysql://u:p@h/d")
    with pytest.raises(ValidationError, match="CRAGMATCH_POSTGRES_URL"):
        build()


def test_missing_database_settings_are_named(monkeypatch):
    set_keys(monkeypatch)
    monkeypatch.setenv("CRAGMATCH_POSTGRES_USER", "u")
    with pytest.raises(ValidationError) as error:
        build()
    assert "CRAGMATCH_POSTGRES_URL" in str(error.value)
    assert "CRAGMATCH_POSTGRES_HOST" in str(error.value)


def test_missing_api_key_is_named(monkeypatch):
    monkeypatch.setenv("CRAGMATCH_VOYAGE_API_KEY", "voyage-dummy")
    set_parts(monkeypatch)
    with pytest.raises(ValidationError, match="anthropic_api_key"):
        build()


def test_blank_value_counts_as_missing(monkeypatch):
    set_parts(monkeypatch)
    monkeypatch.setenv("CRAGMATCH_ANTHROPIC_API_KEY", "anthropic-dummy")
    monkeypatch.setenv("CRAGMATCH_VOYAGE_API_KEY", "")
    with pytest.raises(ValidationError, match="voyage_api_key"):
        build()

    monkeypatch.setenv("CRAGMATCH_VOYAGE_API_KEY", "voyage-dummy")
    monkeypatch.setenv("CRAGMATCH_POSTGRES_URL", "")
    assert build().database_url == "postgresql+psycopg://u:p@h:5433/d"


def test_errors_never_show_secret_values(monkeypatch):
    monkeypatch.setenv("CRAGMATCH_ANTHROPIC_API_KEY", "sk-visible")
    set_parts(monkeypatch, password="hunter2-visible")
    with pytest.raises(ValidationError) as error:
        build()
    text = str(error.value)
    assert "voyage_api_key" in text
    assert "sk-visible" not in text
    assert "hunter2-visible" not in text

    set_keys(monkeypatch)
    monkeypatch.delenv("CRAGMATCH_POSTGRES_HOST")
    with pytest.raises(ValidationError) as error:
        build()
    assert "hunter2-visible" not in str(error.value)


def test_cors_origins_default_to_the_vite_dev_server(monkeypatch):
    set_keys(monkeypatch)
    set_parts(monkeypatch)
    s = build()
    assert s.cors_origins == ["http://localhost:5173"]
    assert s.postgres_url is None


def test_cors_origins_from_a_comma_list(monkeypatch):
    set_keys(monkeypatch)
    set_parts(monkeypatch)
    monkeypatch.setenv(
        "CRAGMATCH_CORS_ORIGINS", " https://a.example , https://b.example/,"
    )
    assert build().cors_origins == ["https://a.example", "https://b.example"]


def test_tests_use_the_cragmatch_test_database(db_session):
    bind_url = db_session.get_bind().url
    app_url = make_url(settings.database_url)
    assert bind_url.database == "cragmatch_test"
    assert bind_url.host == app_url.host
    assert bind_url.port == app_url.port
