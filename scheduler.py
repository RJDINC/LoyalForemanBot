"""
Hourly reconciliation between Patreon and Discord roles.

Algorithm (single cycle):

  1. Snapshot `now`. Set `cycle_started = now`.
  2. Fetch every member of the campaign from Patreon.
  3. For each member with the Foreman tier:
        a. If `is_active` (active_patron + Paid): tracker.upsert_active(...).
           On FIRST sighting, backfill foreman_since from the member's real
           charge history (start of their most recent unbroken monthly streak
           of paid FOREMAN-TIER charges — one extra API call, once per member).
        b. Else (declined / former / unpaid): tracker.mark_lapsed_or_reset(..., grace_days)
     For members WITHOUT the Foreman tier, we ignore them — they'll get aged
     out by step 5.
  4. For each tracker row, decide whether to grant/revoke the Loyal Foreman role:
        * grant if tenure_days >= config.tenure_days AND row.last_active_at >= now-grace
        * revoke if row.last_active_at < now-grace (they lapsed beyond grace)
  5. tracker.remove_unseen(before=cycle_started) — drops anyone who no longer
     appears on the Foreman tier at all; revoke their role.

Guild ID, role ID, Patreon campaign ID, and tier ID are all resolved at
startup by bot.py and passed in at construction time.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone

import discord

from config import Config
from patreon_client import PatreonClient
from tenure_tracker import (
    MANUAL_OVERRIDE_PATREON_ID,
    TenureTracker,
    compute_streak_start,
)

log = logging.getLogger(__name__)


class Reconciler:
    def __init__(
        self,
        cfg: Config,
        bot: discord.Client,
        tracker: TenureTracker,
        *,
        guild_id: int,
        role_id: int,
        campaign_id: str,
        tier_id: str,
    ):
        self._cfg = cfg
        self._bot = bot
        self._tracker = tracker
        self._guild_id = guild_id
        self._role_id = role_id
        self._campaign_id = campaign_id
        self._tier_id = tier_id
        self.last_summary: dict | None = None
        self.last_error: str | None = None

    async def run_forever(self) -> None:
        interval = self._cfg.check_interval_minutes * 60
        while not self._bot.is_closed():
            try:
                await self.run_once()
                self.last_error = None
            except Exception as e:
                log.exception("Reconciliation cycle failed; will retry next interval")
                self.last_error = f"{type(e).__name__}: {e}"
            await asyncio.sleep(interval)

    async def run_once(self) -> dict:
        cfg = self._cfg
        cycle_started = datetime.now(timezone.utc)
        log.info("Reconciliation cycle starting at %s", cycle_started.isoformat())

        guild = self._bot.get_guild(self._guild_id)
        if guild is None:
            raise RuntimeError(f"Bot is not in guild {self._guild_id}")
        role = guild.get_role(self._role_id)
        if role is None:
            raise RuntimeError(f"Role {self._role_id} not found in guild")

        # --- 1+2+3: pull from Patreon, update tracker -----------------------
        foremen_seen = 0
        no_discord = 0
        async with PatreonClient(cfg.patreon_creator_token, self._campaign_id) as pc:
            async for member in pc.iter_members():
                if not member.has_tier(self._tier_id):
                    continue
                if not member.discord_user_id:
                    no_discord += 1
                    log.info(
                        "Foreman %s has no linked Discord account — cannot grant role",
                        member.member_id,
                    )
                    continue

                foremen_seen += 1
                if member.is_active:
                    # First sighting: backfill tenure from their REAL charge
                    # history — the start of their most recent unbroken monthly
                    # streak. (pledge_relationship_start is "first ever pledge"
                    # and never resets on a lapse, so it over-credits returners.)
                    historical_since = None
                    if self._tracker.get(member.discord_user_id) is None:
                        try:
                            paid_dates = await pc.fetch_paid_charge_dates(
                                member.member_id, tier_id=self._tier_id
                            )
                            historical_since = compute_streak_start(
                                paid_dates,
                                now=cycle_started,
                                max_gap_days=31 + cfg.lapse_grace_days,
                            )
                        except Exception:
                            # Conservative fallback: no historical credit, clock
                            # starts today. Better to under-credit than hand the
                            # role to a lapsed returner.
                            log.exception(
                                "Charge-history fetch failed for member %s; starting their clock at today",
                                member.member_id,
                            )
                    self._tracker.upsert_active(
                        discord_id=member.discord_user_id,
                        patreon_id=member.member_id,
                        now=cycle_started,
                        historical_since=historical_since,
                    )
                else:
                    self._tracker.mark_lapsed_or_reset(
                        discord_id=member.discord_user_id,
                        grace_days=cfg.lapse_grace_days,
                        now=cycle_started,
                    )

        # --- 4: grant / revoke based on tracker state -----------------------
        granted = revoked = 0
        grace_cutoff = cycle_started - timedelta(days=cfg.lapse_grace_days)

        for row in self._tracker.all_rows():
            # Admin-set exclusion overrides everything — never grant, always revoke if present
            if self._tracker.is_excluded(row.discord_id):
                member = await _fetch_member(guild, row.discord_id)
                if member is not None and role in member.roles:
                    if await _safe_remove_role(member, role, reason="Loyal Foreman: excluded by admin"):
                        self._tracker.set_role_granted(row.discord_id, False)
                        revoked += 1
                continue

            # Manual grants are permanently eligible: never lapse, never expire.
            # If the person later appears on Patreon as a linked Foreman,
            # upsert_active overwrites patreon_id and normal rules take over.
            if row.patreon_id == MANUAL_OVERRIDE_PATREON_ID:
                member = await _fetch_member(guild, row.discord_id)
                if member is not None and role not in member.roles:
                    if await _safe_add_role(member, role, reason="Loyal Foreman: manual grant by admin"):
                        self._tracker.set_role_granted(row.discord_id, True)
                        granted += 1
                continue

            eligible = (
                row.tenure_days(cycle_started) >= cfg.tenure_days
                and row.last_active_at >= grace_cutoff
            )
            member = await _fetch_member(guild, row.discord_id)
            if member is None:
                continue

            has_role = role in member.roles
            if eligible and not has_role:
                if await _safe_add_role(member, role, reason="Loyal Foreman: 3+ months continuous"):
                    self._tracker.set_role_granted(row.discord_id, True)
                    granted += 1
                    # Only DM on the FIRST successful grant (when tracker flips False -> True)
                    if not row.role_granted:
                        await _send_congrats_dm(member, role, guild, cfg.tenure_days)
            elif not eligible and has_role:
                if await _safe_remove_role(member, role, reason="Loyal Foreman: tenure lapsed"):
                    self._tracker.set_role_granted(row.discord_id, False)
                    revoked += 1

        # --- 5: cleanup — anyone we didn't see this cycle is no longer Foreman
        dropped = self._tracker.remove_unseen(before=cycle_started)
        for row in dropped:
            member = await _fetch_member(guild, row.discord_id)
            if member and role in member.roles:
                if await _safe_remove_role(member, role, reason="Loyal Foreman: no longer on Foreman tier"):
                    revoked += 1

        summary = {
            "cycle_started": cycle_started.isoformat(),
            "foremen_seen": foremen_seen,
            "no_discord": no_discord,
            "granted": granted,
            "revoked": revoked,
            "dropped": len(dropped),
            "tracked_total": len(self._tracker.all_rows()),
        }
        log.info("Reconciliation done: %s", summary)
        self.last_summary = summary
        return summary


async def _fetch_member(guild: discord.Guild, discord_id: str) -> discord.Member | None:
    try:
        uid = int(discord_id)
    except ValueError:
        return None
    member = guild.get_member(uid)
    if member is not None:
        return member
    try:
        return await guild.fetch_member(uid)
    except discord.NotFound:
        return None
    except discord.HTTPException:
        log.exception("Failed to fetch member %s", discord_id)
        return None


async def _safe_add_role(member: discord.Member, role: discord.Role, *, reason: str) -> bool:
    try:
        await member.add_roles(role, reason=reason)
        log.info("Granted %s to %s (%s)", role.name, member, member.id)
        return True
    except discord.Forbidden:
        log.error("Missing permission to grant role to %s", member)
        return False
    except discord.HTTPException:
        log.exception("Failed to grant role to %s", member)
        return False


async def _safe_remove_role(member: discord.Member, role: discord.Role, *, reason: str) -> bool:
    try:
        await member.remove_roles(role, reason=reason)
        log.info("Revoked %s from %s (%s)", role.name, member, member.id)
        return True
    except discord.Forbidden:
        log.error("Missing permission to revoke role from %s", member)
        return False
    except discord.HTTPException:
        log.exception("Failed to revoke role from %s", member)
        return False


async def _send_congrats_dm(
    member: discord.Member, role: discord.Role, guild: discord.Guild, tenure_days: int
) -> None:
    """Best-effort DM. Patrons commonly have DMs disabled from server members; that's fine, log and move on."""
    msg = (
        f"Congrats! You've been a continuous Foreman patron of **{guild.name}** for {tenure_days}+ days. "
        f"You've just earned the **{role.name}** role. Thanks for the loyal support."
    )
    try:
        await member.send(msg)
        log.info("Sent congrats DM to %s (%s)", member, member.id)
    except discord.Forbidden:
        log.info("Could not DM %s (DMs likely disabled); role granted silently", member)
    except discord.HTTPException:
        log.exception("Unexpected failure sending congrats DM to %s", member)
