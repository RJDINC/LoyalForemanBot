"""
Minimal async Patreon API v2 client.

We only need one endpoint:
    GET /api/oauth2/v2/campaigns/{campaign_id}/members

For each member we read:
    - patron_status            ("active_patron" | "declined_patron" | "former_patron")
    - last_charge_status       ("Paid" | "Declined" | "Refunded" | ...)
    - last_charge_date
    - currently_entitled_tiers (relationship -> tier IDs)
    - user.social_connections.discord.user_id (the Discord user ID)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import AsyncIterator

import aiohttp

log = logging.getLogger(__name__)

API_ROOT = "https://www.patreon.com/api/oauth2/v2"

MEMBER_FIELDS = ",".join([
    "patron_status",
    "last_charge_status",
    "last_charge_date",
])
USER_FIELDS = ",".join([
    "social_connections",
])
INCLUDE = "currently_entitled_tiers,user"


@dataclass(frozen=True)
class PatreonMember:
    member_id: str
    discord_user_id: str | None
    patron_status: str | None
    last_charge_status: str | None
    last_charge_date: datetime | None
    entitled_tier_ids: tuple[str, ...]

    def has_tier(self, tier_id: str) -> bool:
        return tier_id in self.entitled_tier_ids

    @property
    def is_active(self) -> bool:
        # "active_patron" with a Paid (or null, for free/manual) charge counts as active.
        if self.patron_status != "active_patron":
            return False
        if self.last_charge_status in (None, "Paid"):
            return True
        return False


def _parse_dt(raw: str | None) -> datetime | None:
    if not raw:
        return None
    # Patreon returns ISO 8601 with +0000 offset
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        log.warning("Failed to parse datetime: %r", raw)
        return None


def _extract_discord_id(user_attrs: dict) -> str | None:
    social = (user_attrs or {}).get("social_connections") or {}
    discord = social.get("discord") or {}
    uid = discord.get("user_id")
    return str(uid) if uid else None


class PatreonClient:
    def __init__(self, creator_token: str, campaign_id: str | None = None):
        self._token = creator_token
        self._campaign_id = campaign_id
        self._session: aiohttp.ClientSession | None = None

    async def __aenter__(self) -> "PatreonClient":
        self._session = aiohttp.ClientSession(
            headers={"Authorization": f"Bearer {self._token}"}
        )
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        if self._session:
            await self._session.close()
            self._session = None

    async def discover(self, tier_name: str) -> tuple[str, str]:
        """
        Auto-detect the creator's first campaign and find the tier whose title
        matches `tier_name` (case-insensitive). Returns (campaign_id, tier_id).

        Raises if the token has no campaigns visible, or no tier matches.
        """
        assert self._session is not None, "Use `async with PatreonClient(...)`"

        params = {
            "include": "tiers",
            "fields[campaign]": "creation_name,vanity",
            "fields[tier]": "title",
        }
        async with self._session.get(f"{API_ROOT}/campaigns", params=params) as resp:
            if resp.status != 200:
                body = await resp.text()
                raise RuntimeError(
                    f"Patreon /campaigns failed ({resp.status}): {body[:300]}"
                )
            payload = await resp.json()

        campaigns = payload.get("data", [])
        if not campaigns:
            raise RuntimeError(
                "Patreon token has no visible campaigns. Is the token from the creator account?"
            )

        if len(campaigns) > 1:
            descriptions = []
            for c in campaigns:
                a = c.get("attributes", {})
                descriptions.append(
                    f"  id={c['id']}  name={a.get('creation_name') or a.get('vanity') or '(unnamed)'}"
                )
            log.warning(
                "Patreon token sees %d campaigns; using the first. If that's wrong, "
                "rotate the token to one that only sees the right campaign, or contact the bot maintainer.\n%s",
                len(campaigns),
                "\n".join(descriptions),
            )

        campaign = campaigns[0]
        campaign_id = campaign["id"]

        tiers_by_id = {
            item["id"]: item["attributes"]
            for item in payload.get("included", [])
            if item.get("type") == "tier"
        }
        tier_refs = (campaign.get("relationships", {}).get("tiers") or {}).get("data") or []

        target = tier_name.strip().lower()
        for ref in tier_refs:
            attrs = tiers_by_id.get(ref["id"], {})
            if (attrs.get("title") or "").strip().lower() == target:
                self._campaign_id = campaign_id
                return campaign_id, ref["id"]

        available = [tiers_by_id.get(r["id"], {}).get("title") for r in tier_refs]
        raise RuntimeError(
            f"No tier named '{tier_name}' found on the campaign. Available tiers: {available}"
        )

    async def fetch_paid_charge_dates(self, member_id: str) -> list[datetime]:
        """
        Fetch one member's pledge history and return the dates of their
        SUCCESSFUL charges, sorted oldest-first.

        Used to compute real continuous-tenure streaks: `pledge_relationship_start`
        is useless for that (it's "first ever pledge" and never resets when a
        patron lapses and returns), so we look at the actual charge events.
        """
        assert self._session is not None, "Use `async with PatreonClient(...)`"

        params = {
            "include": "pledge_history",
            "fields[pledge-event]": "date,type,payment_status",
        }
        async with self._session.get(f"{API_ROOT}/members/{member_id}", params=params) as resp:
            if resp.status != 200:
                body = await resp.text()
                raise RuntimeError(
                    f"Patreon pledge_history fetch failed ({resp.status}) for member {member_id}: {body[:300]}"
                )
            payload = await resp.json()

        dates: list[datetime] = []
        for item in payload.get("included", []):
            if item.get("type") != "pledge-event":
                continue
            attrs = item.get("attributes", {})
            event_type = attrs.get("type")
            status = (attrs.get("payment_status") or "").strip().lower()
            # 'subscription' = a recurring monthly charge; 'pledge_start' can carry
            # the initial charge on charge-upfront campaigns. Count only money
            # that actually went through.
            if event_type in ("subscription", "pledge_start") and status in ("paid", "valid"):
                dt = _parse_dt(attrs.get("date"))
                if dt:
                    dates.append(dt)
        dates.sort()
        return dates

    async def iter_members(self) -> AsyncIterator[PatreonMember]:
        assert self._session is not None, "Use `async with PatreonClient(...)`"
        if not self._campaign_id:
            raise RuntimeError("campaign_id not set; call discover() first or pass it in the constructor")

        url = f"{API_ROOT}/campaigns/{self._campaign_id}/members"
        params = {
            "include": INCLUDE,
            "fields[member]": MEMBER_FIELDS,
            "fields[user]": USER_FIELDS,
            "page[count]": "200",
        }

        while url:
            async with self._session.get(url, params=params) as resp:
                if resp.status != 200:
                    body = await resp.text()
                    raise RuntimeError(
                        f"Patreon API {resp.status} for {url}: {body[:300]}"
                    )
                payload = await resp.json()

            included = {(item["type"], item["id"]): item for item in payload.get("included", [])}

            for entry in payload.get("data", []):
                attrs = entry.get("attributes", {})
                rels = entry.get("relationships", {})

                tier_data = (rels.get("currently_entitled_tiers") or {}).get("data") or []
                tier_ids = tuple(t["id"] for t in tier_data)

                user_ref = (rels.get("user") or {}).get("data") or {}
                user_inc = included.get(("user", user_ref.get("id"))) if user_ref else None
                discord_id = _extract_discord_id(user_inc.get("attributes") if user_inc else None)

                yield PatreonMember(
                    member_id=entry["id"],
                    discord_user_id=discord_id,
                    patron_status=attrs.get("patron_status"),
                    last_charge_status=attrs.get("last_charge_status"),
                    last_charge_date=_parse_dt(attrs.get("last_charge_date")),
                    entitled_tier_ids=tier_ids,
                )

            # Pagination: next link is in links.next OR meta.pagination.cursors.next
            links = payload.get("links") or {}
            next_url = links.get("next")
            if next_url:
                url = next_url
                # params already baked into next_url
                params = None
            else:
                url = None
