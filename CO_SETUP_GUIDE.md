# Co-Setup Guide

You (the builder) are walking the Patreon creator through setup on a screen-share. Everything ends up on **their** accounts — Discord developer, Patreon creator, Railway, GitHub. You never personally hold any of their tokens.

This document has two halves:

- **Part A** — copy/paste this into a DM to them *before* the call, so they show up prepared.
- **Part B** — your live checklist for the call itself.

---

## Part A — Send this to the creator before the call

> Hey! Before we hop on, please make sure you have:
>
> 1. A working login for **Patreon** as the creator of the campaign.
> 2. A working login for **Discord** with **Admin** (or "Manage Server" + "Manage Roles") permission on the server you want this bot in.
> 3. A **credit card or PayPal** ready for Railway (the hosting service). They have a free tier that should cover a tiny bot like this, but they require a card on file. Budget ~$5/mo as a safe upper bound.
> 4. About **1 hour** blocked off with no interruptions. I'll share my screen, you'll share yours, and we'll click through everything on your side together.
> 5. A **password manager** open (1Password, Bitwarden, Apple Keychain — whatever you use) so we can paste secrets in safely as we generate them. Don't put any of this in a regular text file.
>
> You won't need to write code, but you will be clicking through a bunch of menus on three different websites. I'll tell you exactly what to click.

---

## Part B — Your live checklist for the call

Steps roughly in order. Each step lists the URL, what to do, and what to copy where. Hand the keyboard to them at each step — they should do the actual clicking and typing so the accounts/credentials belong to them.

### 0. Pre-flight (2 min)

- They share their screen.
- Open a fresh note in their password manager titled "Loyal Foreman Bot" — we'll paste 7 values into it as we go.

### 1. Discord — create the bot application (10 min)

URL: <https://discord.com/developers/applications>

1. **New Application** → name it `Loyal Foreman Bot` → Create.
2. Left sidebar → **Bot**.
   - Click **Reset Token** → **Yes, do it** → copy the token → paste into their note as `DISCORD_BOT_TOKEN`.
   - Scroll down to **Privileged Gateway Intents** → toggle on **SERVER MEMBERS INTENT** → Save.
3. Left sidebar → **OAuth2 → URL Generator**.
   - **Scopes**: check `bot` and `applications.commands`.
   - **Bot Permissions**: check `Manage Roles`.
   - Copy the generated URL at the bottom, open it in a new tab, pick their server, click **Authorize**, solve the captcha.

### 2. Discord — create the role + fix role order (5 min)

1. In their Discord server: **Server Settings → Roles → Create Role**.
   - Name: `Loyal Foreman` (exactly — color/permissions don't matter for the bot, but pick a nice color).
2. Still in the role list — find the auto-created **Loyal Foreman Bot** role (Discord made this when the bot joined). **Drag it ABOVE** the `Loyal Foreman` role.
   - This is the #1 thing that trips people up. The bot can only manage roles ranked *below* its own.

### 3. Discord — copy server + role IDs (3 min)

1. **User Settings → Advanced → Developer Mode** → ON.
2. Right-click their server name in the sidebar → **Copy Server ID** → paste into note as `DISCORD_GUILD_ID`.
3. **Server Settings → Roles** → right-click `Loyal Foreman` → **Copy Role ID** → paste into note as `LOYAL_FOREMAN_ROLE_ID`.

### 4. Patreon — get a Creator Access Token (5 min)

URL: <https://www.patreon.com/portal/registration/register-clients>

1. They must be logged in as the **creator** (not a patron) of the Foreman campaign.
2. Click **Create Client**.
   - App Name: `Loyal Foreman Bot`
   - Description: `Internal Discord role-grant bot`
   - App Category: any (e.g. "Bot")
   - Redirect URI: `http://localhost` (unused, but required)
   - Privacy Policy / TOS URL: any of their own URLs, or just their Patreon page URL
3. After it's created, expand the client → reveal **Creator's Access Token** → paste into note as `PATREON_CREATOR_TOKEN`.

### 5. Patreon — get campaign + tier IDs (5 min)

This is the one step a non-tech person can't easily do in a browser. Use the helper script:

1. On *their* computer (or yours if you're sharing), install Python if needed (<https://python.org/downloads/>) and run:
   ```bash
   pip install aiohttp
   python fetch_patreon_ids.py
   ```
2. Paste the Patreon token from step 4 when prompted (input is hidden).
3. The script prints a table like:
   ```
   CAMPAIGN  id = 1234567   name = Foreman's Workshop
       TIER  id = 9876543    $5.00/mo   Apprentice
       TIER  id = 9876544   $15.00/mo   Foreman
       TIER  id = 9876545   $50.00/mo   Master
   ```
4. Copy the **campaign id** → note as `PATREON_CAMPAIGN_ID`.
5. Copy the **Foreman tier id** (the row whose title says "Foreman") → note as `PATREON_FOREMAN_TIER_ID`.

> If they can't / don't want to install Python locally, you can run the helper on *your* machine, but they'll need to paste their token to you — which breaks the "nothing private touches you" principle. Prefer running it on their side.

### 6. GitHub — get a copy of the repo onto their account (5 min)

You presumably have this code in a GitHub repo. Options:

- **Easiest**: make your repo **public** (no secrets are in it — `.env` is gitignored), they don't need their own copy. Railway can deploy directly from your public repo.
- **Private + handoff**: invite them to your private repo as a collaborator OR fork it into their account. Then point Railway at their fork.

For non-technical owners, the public-repo path avoids them needing to learn GitHub.

### 7. Railway — deploy (15 min)

URL: <https://railway.app>

1. **Sign up** with their GitHub account.
2. **New Project → Deploy from GitHub repo** → pick the repo (yours public, or theirs).
3. Wait for the first build. It'll likely **fail** because env vars aren't set — that's fine.
4. **Variables** tab → click **Raw Editor** → paste:
   ```
   DISCORD_BOT_TOKEN=<from note>
   DISCORD_GUILD_ID=<from note>
   LOYAL_FOREMAN_ROLE_ID=<from note>
   PATREON_CREATOR_TOKEN=<from note>
   PATREON_CAMPAIGN_ID=<from note>
   PATREON_FOREMAN_TIER_ID=<from note>
   TENURE_DAYS=90
   LAPSE_GRACE_DAYS=7
   CHECK_INTERVAL_MINUTES=60
   DB_PATH=/data/tenure.db
   ```
5. **Settings → Volumes** → **+ New Volume** → mount path `/data`, size 1 GB. (Without this, the SQLite DB resets on every redeploy and everyone's tenure clock restarts.)
6. **Deployments** tab → click **Redeploy**.
7. Open the **Logs** tab. Within ~30 seconds you should see:
   ```
   Logged in as Loyal Foreman Bot (id=...)
   Slash commands synced to guild ...
   Reconciliation cycle starting at ...
   Reconciliation done: {...}
   ```

### 8. Smoke test in Discord (5 min)

1. In their Discord server, type `/foreman-status` — they should see a Slash-command suggestion.
2. Run it. They get an ephemeral reply with counts: how many Foremen the bot saw, how many it's tracking, granted, revoked.
3. If they already have patrons who've been Foreman 3+ months, you can run `/foreman-check @someone` to verify the tenure math is right.

### 9. Wrap (5 min)

- Confirm the Discord note in the password manager is saved (and shared between you if appropriate).
- Tell them: **the bot will run automatically forever**. It checks Patreon every hour. There's nothing they need to do day-to-day.
- Things that *will* need them later:
  - If they rotate the Patreon Creator Access Token, they need to update `PATREON_CREATOR_TOKEN` in Railway Variables.
  - If they rotate the Discord bot token (e.g. it leaks), same — update `DISCORD_BOT_TOKEN`.
  - If they ever rename or delete the Foreman tier on Patreon, the bot stops finding members on that tier — they'd need to give you the new tier ID.
- Send them the Railway dashboard URL — that's where they go to see logs / change things later. Tell them to **not** delete the volume.

---

## Things to flag during the call

- **Permissions hierarchy** (step 2.2) is the most common bug. Double-check the bot role is above `Loyal Foreman`.
- **Members Intent** (step 1.2) — if forgotten, the bot can't see who's in the server and grants nothing. The logs will show "no member found" repeatedly.
- **Volume mount** (step 7.5) — without it, every redeploy wipes tenure history. If you skip it, do it later before any patron crosses 3 months.
- **Token leak**: if a token ever shows up in a screenshot, log file, or chat, treat it as compromised — go back to the developer portal / Patreon clients page and rotate it. Then update the Railway variable.
