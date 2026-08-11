from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import UTC, date, datetime

DEFAULT_CM_GAMES = [
    "magic",
    "yugioh",
    "pokemon",
    "onepiece",
    "dragonballsuper",
    "fleshandblood",
    "digimon",
    "lorcana",
    "starwarsunlimited",
    "riftbound",
]


def _split_csv(value: str | None, default: list[str]) -> list[str]:
    if not value:
        return default
    return [item.strip() for item in value.split(",") if item.strip()]


@dataclass(frozen=True)
class Settings:
    cm_games: list[str]
    cm_priceguide_url_template: str
    cm_catalogue_url_template: str
    cm_user_agent: str
    r2_account_id: str
    r2_access_key_id: str
    r2_secret_access_key: str
    r2_bucket: str
    supabase_db_url: str
    supabase_url: str
    supabase_anon_key: str
    alert_discord_webhook: str | None

    @classmethod
    def from_env(cls) -> Settings:
        return cls(
            cm_games=_split_csv(os.getenv("CM_GAMES"), DEFAULT_CM_GAMES),
            cm_priceguide_url_template=os.getenv("CM_PRICEGUIDE_URL_TEMPLATE", ""),
            cm_catalogue_url_template=os.getenv("CM_CATALOGUE_URL_TEMPLATE", ""),
            cm_user_agent=os.getenv(
                "CM_USER_AGENT", "tcg-eu-index/0.1 contact=operator@example.com"
            ),
            r2_account_id=os.getenv("R2_ACCOUNT_ID", ""),
            r2_access_key_id=os.getenv("R2_ACCESS_KEY_ID", ""),
            r2_secret_access_key=os.getenv("R2_SECRET_ACCESS_KEY", ""),
            r2_bucket=os.getenv("R2_BUCKET", "tcg-raw"),
            supabase_db_url=os.getenv("SUPABASE_DB_URL", ""),
            supabase_url=os.getenv("SUPABASE_URL", ""),
            supabase_anon_key=os.getenv("SUPABASE_ANON_KEY", ""),
            alert_discord_webhook=os.getenv("ALERT_DISCORD_WEBHOOK"),
        )

    @property
    def r2_endpoint_url(self) -> str:
        if not self.r2_account_id:
            return ""
        return f"https://{self.r2_account_id}.r2.cloudflarestorage.com"


def utc_now() -> datetime:
    return datetime.now(UTC)


def parse_run_date(value: str | None) -> date:
    if not value or value == "today":
        return utc_now().date()
    return date.fromisoformat(value)
