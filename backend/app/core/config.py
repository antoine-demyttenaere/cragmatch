from typing import Annotated

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict
from sqlalchemy.engine import URL, make_url
from sqlalchemy.exc import ArgumentError


class Settings(BaseSettings):
    # Either postgres_url or all five parts; checked in check_database_settings.
    postgres_url: str | None = None
    postgres_user: str | None = None
    postgres_password: str | None = None
    postgres_db: str | None = None
    postgres_host: str | None = None
    postgres_port: int | None = None
    anthropic_api_key: str
    voyage_api_key: str
    cors_origins: Annotated[list[str], NoDecode] = ["http://localhost:5173"]

    # env_ignore_empty: a blank value (as in .env.example) counts as missing
    # instead of starting the app with an empty key.
    # hide_input_in_errors: a start-up error must never print keys or
    # passwords into a platform's logs.
    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="CRAGMATCH_",
        env_ignore_empty=True,
        hide_input_in_errors=True,
    )

    @field_validator("cors_origins", mode="before")
    @classmethod
    def split_cors_origins(cls, value: object) -> object:
        # A comma list is easier to type into a platform's settings page than
        # JSON. A browser's Origin header never ends in "/", so strip it.
        if not isinstance(value, str):
            return value
        parts = [part.strip().rstrip("/") for part in value.split(",")]
        return [part for part in parts if part]

    @field_validator("postgres_url")
    @classmethod
    def check_postgres_url(cls, value: str | None) -> str | None:
        if value is None:
            return value
        message = "CRAGMATCH_POSTGRES_URL must start with postgres:// or postgresql://"
        # The messages never contain the URL: it holds the password.
        try:
            backend = make_url(value).get_backend_name()
        except ArgumentError:
            raise ValueError(message) from None
        if backend not in ("postgres", "postgresql"):
            raise ValueError(message)
        return value

    @model_validator(mode="after")
    def check_database_settings(self) -> "Settings":
        if self.postgres_url is not None:
            return self
        parts = {
            "CRAGMATCH_POSTGRES_USER": self.postgres_user,
            "CRAGMATCH_POSTGRES_PASSWORD": self.postgres_password,
            "CRAGMATCH_POSTGRES_DB": self.postgres_db,
            "CRAGMATCH_POSTGRES_HOST": self.postgres_host,
            "CRAGMATCH_POSTGRES_PORT": self.postgres_port,
        }
        missing = [name for name, value in parts.items() if value is None]
        if missing:
            raise ValueError(
                "Set CRAGMATCH_POSTGRES_URL, or all of CRAGMATCH_POSTGRES_USER, "
                "CRAGMATCH_POSTGRES_PASSWORD, CRAGMATCH_POSTGRES_DB, "
                "CRAGMATCH_POSTGRES_HOST, CRAGMATCH_POSTGRES_PORT "
                f"(missing: {', '.join(missing)})"
            )
        return self

    @property
    def database_url(self) -> str:
        # Still the only place that builds the URL. The driver is forced, so
        # both postgres:// and postgresql:// work; query options such as
        # sslmode are kept, and URL.create escapes special characters in the
        # password.
        if self.postgres_url is not None:
            url = make_url(self.postgres_url).set(drivername="postgresql+psycopg")
        else:
            url = URL.create(
                "postgresql+psycopg",
                username=self.postgres_user,
                password=self.postgres_password,
                host=self.postgres_host,
                port=self.postgres_port,
                database=self.postgres_db,
            )
        return url.render_as_string(hide_password=False)


settings = Settings()
