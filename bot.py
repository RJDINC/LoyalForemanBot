"""
Discord bot entrypoint.

Run with:  python bot.py

On startup (once Discord is ready) the bot:
  1. Picks the (single) guild it's been invited to.
  2. Finds or creates the "Loyal Foreman" role.
  3. Verifies its own role sits above that role; logs a clear warning if not.
  4. Calls Patreon to auto-detect the campaign and Foreman tier.
  5. Posts a one-time greeting to the server's system channel.
  6. Starts the hourly reconciliation loop.

Admin slash commands:
    /foreman-status              run a reconciliation now, return summary
    /foreman-check <member>      show tenure info for one member
"""

from __future__ import annotations

import logging
import sys
from datetime import datetime, timezone

import discord
from discord import app_commands

import config
from patreon_client import PatreonClient
from scheduler import Reconciler
from tenure_tracker import MANUAL_OVERRIDE_PATREON_ID, TenureTracker

logging.basicConfig(
    level=logging.INFO,
    stream=sys.stdout,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
log = logging.getLogger("foreman-bot")


async def _ensure_role(
    guild: discord.Guild, name: str, persisted_id: int | None
) -> discord.Role | None:
    # 1. If we previously persisted a role ID, prefer that — even if the role has been renamed.
    if persisted_id is not None:
        role = guild.get_role(persisted_id)
        if role is not None:
            return role
        log.warning(
            "Previously-persisted role id %s no longer exists in this server; falling back to name lookup.",
            persisted_id,
        )

    # 2. Fall back to name lookup.
    role = discord.utils.get(guild.roles, name=name)
    if role is not None:
        return role

    # 3. Last resort — create it.
    try:
        role = await guild.create_role(
            name=name,
            reason="Loyal Foreman bot: first-time setup",
            mentionable=False,
        )
        log.info("Created role '%s' in %s", name, guild.name)
        return role
    except discord.Forbidden:
        log.error("Cannot create role '%s' — I lack Manage Roles permission.", name)
        return None
    except discord.HTTPException:
        log.exception("Discord rejected role creation for '%s'", name)
        return None


def _pick_guild(bot: discord.Client, persisted_id: int | None) -> discord.Guild | None:
    guilds = list(bot.guilds)
    if not guilds:
        return None
    # 1. Prefer the previously-persisted guild if the bot is still in it.
    if persisted_id is not None:
        for g in guilds:
            if g.id == persisted_id:
                if len(guilds) > 1:
                    log.warning(
                        "Bot is in %d servers (%s); using previously-persisted '%s'.",
                        len(guilds), [x.name for x in guilds], g.name,
                    )
                return g
        log.warning(
            "Previously-persisted guild %s isn't one I'm in anymore; will pick a new one.",
            persisted_id,
        )
    # 2. First guild wins; warn if there are several.
    if len(guilds) > 1:
        log.warning(
            "Bot is in %d servers (%s). This build targets a single server — using '%s'. "
            "Kick me from the others to avoid confusion.",
            len(guilds), [g.name for g in guilds], guilds[0].name,
        )
    return guilds[0]


def _check_hierarchy(guild: discord.Guild, role: discord.Role) -> None:
    me = guild.me
    if me is None:
        log.warning("Could not resolve bot's own member object in guild")
        return
    if me.top_role <= role:
        log.warning(
            "HIERARCHY ISSUE: my top role is '%s' (position %d) but '%s' is at position %d. "
            "Drag my role ABOVE '%s' in Server Settings → Roles or I cannot assign it.",
            me.top_role.name, me.top_role.position,
            role.name, role.position,
            role.name,
        )


async def _greet(guild: discord.Guild, role: discord.Role, tier_name: str, tenure_days: int) -> None:
    channel = guild.system_channel
    if channel is None:
        return
    me = guild.me
    if me is None or not channel.permissions_for(me).send_messages:
        return
    try:
        await channel.send(
            f"Loyal Foreman bot online. Watching the **{tier_name}** Patreon tier — "
            f"any member with {tenure_days}+ days continuous gets the **{role.name}** role. "
            f"Checking every hour. Admins can run `/foreman-status` to see counts."
        )
    except discord.HTTPException:
        log.exception("Failed to send startup greeting")


def make_bot(cfg: config.Config) -> discord.Client:
    intents = discord.Intents.default()
    intents.members = True  # required to fetch members + update roles

    bot = discord.Client(intents=intents)
    tree = app_commands.CommandTree(bot)
    tracker = TenureTracker(cfg.db_path)

    # These get populated in on_ready, then captured by closures below.
    state: dict = {"reconciler": None, "guild_id": None, "role_id": None, "started": False}

    @bot.event
    async def on_ready():
        log.info("Logged in as %s (id=%s)", bot.user, bot.user.id if bot.user else "?")

        if state["started"]:
            log.info("on_ready fired again — already initialized, skipping setup")
            return

        # --- 1. Pick the guild ------------------------------------------
        persisted_guild = tracker.get_state("guild_id")
        guild = _pick_guild(bot, int(persisted_guild) if persisted_guild else None)
        if guild is None:
            log.error("I'm not in any server. Generate an invite link in the Discord developer portal and invite me first.")
            return
        tracker.set_state("guild_id", str(guild.id))

        # --- 2+3. Ensure role + hierarchy -------------------------------
        persisted_role = tracker.get_state("role_id")
        role = await _ensure_role(
            guild,
            cfg.loyal_foreman_role_name,
            int(persisted_role) if persisted_role else None,
        )
        if role is None:
            return
        tracker.set_state("role_id", str(role.id))
        _check_hierarchy(guild, role)

        # --- 4. Discover Patreon campaign + tier ------------------------
        # Prefer persisted IDs; fall back to name discovery if either is missing
        # or if the persisted tier no longer matches the configured tier name.
        campaign_id = tracker.get_state("campaign_id")
        tier_id = tracker.get_state("tier_id")
        persisted_tier_name = tracker.get_state("tier_name")
        need_rediscover = (
            not campaign_id
            or not tier_id
            or persisted_tier_name != cfg.foreman_tier_name
        )
        if need_rediscover:
            try:
                async with PatreonClient(cfg.patreon_creator_token) as pc:
                    campaign_id, tier_id = await pc.discover(cfg.foreman_tier_name)
            except Exception as e:
                log.error("Patreon discovery failed: %s", e)
                return
            tracker.set_state("campaign_id", campaign_id)
            tracker.set_state("tier_id", tier_id)
            tracker.set_state("tier_name", cfg.foreman_tier_name)
        log.info(
            "Patreon resolved: campaign=%s, tier_name='%s', tier_id=%s%s",
            campaign_id, cfg.foreman_tier_name, tier_id,
            "" if need_rediscover else " (from persisted state)",
        )

        # --- 5. Build reconciler + sync slash commands ------------------
        reconciler = Reconciler(
            cfg, bot, tracker,
            guild_id=guild.id,
            role_id=role.id,
            campaign_id=campaign_id,
            tier_id=tier_id,
        )
        state["reconciler"] = reconciler
        state["guild_id"] = guild.id
        state["role_id"] = role.id
        state["started"] = True

        # Commands are registered globally (guild unknown at import time). Copy them
        # into this guild before syncing — a guild sync alone would upload an EMPTY
        # set and the commands would never appear in Discord.
        guild_obj = discord.Object(id=guild.id)
        tree.copy_global_to(guild=guild_obj)
        await tree.sync(guild=guild_obj)
        log.info("Slash commands synced to guild %s", guild.id)

        # Only greet once ever — avoids spamming the system channel on every redeploy
        if tracker.get_state("greeted") is None:
            await _greet(guild, role, cfg.foreman_tier_name, cfg.tenure_days)
            tracker.set_state("greeted", datetime.now(timezone.utc).isoformat())

        # --- 6. Start hourly loop ---------------------------------------
        bot.loop.create_task(reconciler.run_forever())

    # ---- Slash commands ------------------------------------------------

    @tree.command(
        name="foreman-status",
        description="Run a Foreman tenure reconciliation now and report the summary.",
    )
    @app_commands.default_permissions(manage_roles=True)
    async def foreman_status(interaction: discord.Interaction):
        reconciler: Reconciler | None = state.get("reconciler")
        if reconciler is None:
            await interaction.response.send_message(
                "Bot is still starting up or failed to initialize. Check the Railway logs.",
                ephemeral=True,
            )
            return

        await interaction.response.defer(ephemeral=True, thinking=True)
        try:
            summary = await reconciler.run_once()
        except Exception as e:
            log.exception("Manual reconciliation failed")
            await interaction.followup.send(f"Reconciliation failed: `{e}`", ephemeral=True)
            return

        lines = [f"**Foreman reconciliation** — {summary['cycle_started']}"]
        lines.append(f"- Foremen seen on Patreon: **{summary['foremen_seen']}**")
        lines.append(f"- No Discord linked (skipped): **{summary['no_discord']}**")
        lines.append(f"- Currently tracked:        **{summary['tracked_total']}**")
        lines.append(f"- Role granted this run:    **{summary['granted']}**")
        lines.append(f"- Role revoked this run:    **{summary['revoked']}**")
        lines.append(f"- Dropped (left tier):      **{summary['dropped']}**")
        await interaction.followup.send("\n".join(lines), ephemeral=True)

    @tree.command(
        name="foreman-check",
        description="Show tenure info for a specific member.",
    )
    @app_commands.describe(member="The Discord member to check")
    @app_commands.default_permissions(manage_roles=True)
    async def foreman_check(interaction: discord.Interaction, member: discord.Member):
        row = tracker.get(str(member.id))
        if row is None:
            await interaction.response.send_message(
                f"{member.mention} is not tracked as a Foreman.", ephemeral=True,
            )
            return
        days = row.tenure_days()
        msg = (
            f"**{member.display_name}** tenure:\n"
            f"- Foreman since: `{row.foreman_since.isoformat()}`\n"
            f"- Days continuous: **{days:.1f}** / {cfg.tenure_days}\n"
            f"- Last active charge: `{row.last_active_at.isoformat()}`\n"
            f"- Role granted: **{'yes' if row.role_granted else 'no'}**"
        )
        await interaction.response.send_message(msg, ephemeral=True)

    @tree.command(
        name="foreman-health",
        description="Run every precondition check and report what's green / red.",
    )
    @app_commands.default_permissions(manage_roles=True)
    async def foreman_health(interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True, thinking=True)
        checks: list[tuple[bool, str]] = []

        # Bot initialized?
        reconciler: Reconciler | None = state.get("reconciler")
        checks.append((reconciler is not None, "Bot initialized (startup completed)"))

        # Guild + role
        guild_id = state.get("guild_id")
        role_id = state.get("role_id")
        guild = bot.get_guild(guild_id) if guild_id else None
        role = guild.get_role(role_id) if (guild and role_id) else None
        checks.append((guild is not None, f"Discord server resolved ({guild.name if guild else '?'})"))
        checks.append((role is not None, f"Loyal Foreman role exists ({role.name if role else '?'})"))

        # Hierarchy
        hierarchy_ok = False
        if guild and role and guild.me:
            hierarchy_ok = guild.me.top_role > role
        checks.append((hierarchy_ok, "Bot's top role is ABOVE the Loyal Foreman role"))

        # Members intent — heuristic: cache should have >50% of member_count if intent is on
        intent_ok = False
        if guild:
            try:
                intent_ok = guild.member_count is None or len(guild.members) >= max(1, guild.member_count // 2)
            except Exception:
                intent_ok = False
        checks.append((intent_ok, "Server Members Intent appears enabled (member cache populated)"))

        # DB writable
        db_ok = False
        try:
            tracker.set_state("health_probe", datetime.now(timezone.utc).isoformat())
            db_ok = tracker.get_state("health_probe") is not None
        except Exception as e:
            log.exception("DB health probe failed")
            db_ok = False
        checks.append((db_ok, "SQLite database is writable"))

        # Patreon API
        patreon_ok = False
        patreon_detail = ""
        try:
            async with PatreonClient(cfg.patreon_creator_token) as pc:
                cid, tid = await pc.discover(cfg.foreman_tier_name)
                patreon_ok = True
                patreon_detail = f"campaign={cid}, tier={tid}"
        except Exception as e:
            patreon_detail = f"FAILED: {type(e).__name__}: {e}"
        checks.append((patreon_ok, f"Patreon API + '{cfg.foreman_tier_name}' tier found ({patreon_detail})"))

        # Last reconciliation result
        last_summary = reconciler.last_summary if reconciler else None
        last_error = reconciler.last_error if reconciler else None
        if last_summary:
            checks.append((last_error is None, f"Last cycle: {last_summary['cycle_started']} (seen={last_summary['foremen_seen']}, tracked={last_summary['tracked_total']})"))
        else:
            checks.append((False, "No reconciliation cycle has completed yet"))
        if last_error:
            checks.append((False, f"Last cycle error: {last_error}"))

        # Format
        lines = ["**Loyal Foreman bot health check**"]
        for ok, desc in checks:
            mark = "✅" if ok else "❌"
            lines.append(f"{mark} {desc}")
        await interaction.followup.send("\n".join(lines), ephemeral=True)

    @tree.command(
        name="foreman-grant",
        description="Manually grant the Loyal Foreman role and mark the member as fully tenured.",
    )
    @app_commands.describe(member="The Discord member to grant the role to")
    @app_commands.default_permissions(manage_roles=True)
    async def foreman_grant(interaction: discord.Interaction, member: discord.Member):
        guild_id = state.get("guild_id")
        role_id = state.get("role_id")
        if guild_id is None or role_id is None:
            await interaction.response.send_message(
                "Bot is still starting up or failed to initialize. Check the logs.",
                ephemeral=True,
            )
            return

        guild = bot.get_guild(guild_id)
        role = guild.get_role(role_id) if guild else None
        if guild is None or role is None:
            await interaction.response.send_message(
                "Couldn't resolve the server or role. Check bot setup.", ephemeral=True,
            )
            return

        # Do the Discord operation FIRST — if it fails, we don't want stale DB state
        try:
            await member.add_roles(role, reason=f"Manual grant by {interaction.user}")
        except discord.Forbidden:
            await interaction.response.send_message(
                "Discord refused — I don't have permission to assign that role. Check role hierarchy.",
                ephemeral=True,
            )
            return
        except discord.HTTPException as e:
            await interaction.response.send_message(
                f"Discord error while granting the role: `{e}`",
                ephemeral=True,
            )
            return

        # Commit DB state only after Discord confirmed
        tracker.remove_exclusion(str(member.id))
        tracker.mark_fully_tenured(
            discord_id=str(member.id),
            patreon_id=MANUAL_OVERRIDE_PATREON_ID,
            tenure_days=cfg.tenure_days,
        )

        await interaction.response.send_message(
            f"Granted **{role.name}** to {member.mention} and marked them as fully tenured. "
            f"This is permanent — the hourly checks will never remove it — until someone runs "
            f"`/foreman-revoke` on them. If they later show up on Patreon as a normally-linked "
            f"Foreman, automatic tracking takes over seamlessly.",
            ephemeral=True,
        )

    @tree.command(
        name="foreman-revoke",
        description="Manually remove the Loyal Foreman role and clear tenure tracking.",
    )
    @app_commands.describe(member="The Discord member to revoke the role from")
    @app_commands.default_permissions(manage_roles=True)
    async def foreman_revoke(interaction: discord.Interaction, member: discord.Member):
        guild_id = state.get("guild_id")
        role_id = state.get("role_id")
        if guild_id is None or role_id is None:
            await interaction.response.send_message(
                "Bot is still starting up or failed to initialize. Check the logs.",
                ephemeral=True,
            )
            return

        guild = bot.get_guild(guild_id)
        role = guild.get_role(role_id) if guild else None
        if guild is None or role is None:
            await interaction.response.send_message(
                "Couldn't resolve the server or role. Check bot setup.", ephemeral=True,
            )
            return

        try:
            await member.remove_roles(role, reason=f"Manual revoke by {interaction.user}")
        except discord.Forbidden:
            await interaction.response.send_message(
                "Discord refused — I don't have permission to remove that role. Check role hierarchy.",
                ephemeral=True,
            )
            return

        # Add to exclusion list — sticky, survives reconciliation cycles
        tracker.add_exclusion(
            str(member.id),
            reason=f"Manual revoke by {interaction.user} ({interaction.user.id})",
        )
        tracker.remove(str(member.id))

        await interaction.response.send_message(
            f"Removed **{role.name}** from {member.mention} and added them to the exclusion list. "
            f"The reconciler will never grant them this role again, even if they remain a Foreman patron. "
            f"To undo, run `/foreman-grant` on the same member.",
            ephemeral=True,
        )

    return bot


def main() -> None:
    cfg = config.load()
    bot = make_bot(cfg)
    bot.run(cfg.discord_bot_token, log_handler=None)


if __name__ == "__main__":
    main()
