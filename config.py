"""
Config — minimal env vars for a one-click self-host.

REQUIRED (set in Railway Variables tab):
    DISCORD_BOT_TOKEN
    PATREON_CREATOR_TOKEN

OPTIONAL (sensible defaults):
    FOREMAN_TIER_NAME          (default: "Foreman")
    LOYAL_FOREMAN_ROLE_NAME    (default: "Loyal Foreman")
    TENURE_DAYS                (default: 90)
    LAPSE_GRACE_DAYS           (default: 7)
    CHECK_INTERVAL_MINUTES     (default: 60)
    DB_PATH                    (default: /data/tenure.db on Railway template)

Everything else — Discord server ID, role ID, Patreon campaign ID, Patreon tier
ID — is auto-discovered by the bot at startup, so the recipient never has to
hunt for IDs.
"""

import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


def _require(name: str) -> str:
    val = os.getenv(name)
    if not val or val == "replace-me":
        raise RuntimeError(f"Missing required env var: {name}")
    return val


def _int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or raw == "":
        return default
    return int(raw)


@dataclass(frozen=True)
class Config:
    # Required
    discord_bot_token: str
    patreon_creator_token: str

    # Configurable, defaulted
    foreman_tier_name: str
    loyal_foreman_role_name: str
    tenure_days: int
    lapse_grace_days: int
    check_interval_minutes: int
    db_path: str


def load() -> Config:
    return Config(
        discord_bot_token=_require("DISCORD_BOT_TOKEN"),
        patreon_creator_token=_require("PATREON_CREATOR_TOKEN"),
        foreman_tier_name=os.getenv("FOREMAN_TIER_NAME", "Foreman"),
        loyal_foreman_role_name=os.getenv("LOYAL_FOREMAN_ROLE_NAME", "Loyal Foreman"),
        tenure_days=_int("TENURE_DAYS", 90),
        lapse_grace_days=_int("LAPSE_GRACE_DAYS", 7),
        check_interval_minutes=_int("CHECK_INTERVAL_MINUTES", 60),
        db_path=os.getenv("DB_PATH", "tenure.db"),
    )
