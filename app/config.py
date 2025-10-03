import os
from functools import lru_cache

from pydantic import AnyHttpUrl, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", env_prefix="", extra="ignore")

    app_name: str = Field(default="CottagePlayer", alias="APP_NAME")
    google_client_id: str = Field(alias="GOOGLE_CLIENT_ID")
    google_client_secret: str = Field(alias="GOOGLE_CLIENT_SECRET")
    google_redirect_paths_raw: str = Field(default="/auth/callback", alias="GOOGLE_REDIRECT_PATHS")
    oauth_redirect_url: AnyHttpUrl = Field(alias="OAUTH_REDIRECT_URL")
    session_secret: str = Field(alias="SESSION_SECRET")
    media_root: str = Field(default=os.path.join(os.path.dirname(__file__), "storage", "media"), alias="MEDIA_ROOT")
    database_url: str | None = Field(default=None, alias="DATABASE_URL")
    initial_admin_emails_raw: str = Field(default="", alias="INITIAL_ADMIN_EMAILS")
    allow_auto_signup: bool = Field(default=False, alias="ALLOW_AUTO_SIGNUP")

    @property
    def database_connection_url(self) -> str:
        if self.database_url and self.database_url.strip():
            return self.database_url.strip()
        os.makedirs(self.media_root, exist_ok=True)
        return f"sqlite:///{self.media_root}/cottageplayer.db"

    @property
    def initial_admin_emails(self) -> list[str]:
        if not self.initial_admin_emails_raw:
            return []
        return [email.strip() for email in self.initial_admin_emails_raw.split(",") if email.strip()]

    @property
    def allowed_redirect_uris(self) -> list[str]:
        base = str(self.oauth_redirect_url)
        if base.endswith("/auth/callback"):
            base = base[: -(len("/auth/callback"))]
        paths = [p.strip() for p in self.google_redirect_paths_raw.split(",") if p.strip()]
        return [f"{base}{path}" for path in paths]


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    os.makedirs(settings.media_root, exist_ok=True)
    return settings
