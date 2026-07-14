# Loyal Foreman Bot

Grants a **Loyal Foreman** Discord role to Patreon members who've been on the **Foreman** tier for 3+ continuous months. Removes it the moment they drop off.

The bot **auto-detects** the campaign, the tier, the server, and the role — so the only things the operator ever has to paste are two tokens.

---

## Quick deploy (for the Patreon creator)

You'll need 3 things and about 15 minutes.

### 1. Get a Discord bot token (5 min)

1. Go to <https://discord.com/developers/applications> → **New Application** → name it whatever you want.
2. Left sidebar → **Bot** → **Reset Token** → copy it. Save it somewhere safe.
3. On the same **Bot** page, scroll down → toggle **SERVER MEMBERS INTENT** to ON → Save.

### 2. Get a Patreon Creator Access Token (3 min)

1. Logged in as the campaign creator, go to <https://www.patreon.com/portal/registration/register-clients>.
2. Click **Create Client**, fill in any reasonable values (the redirect URI just needs to be `http://localhost`).
3. Expand the new client → copy the **Creator's Access Token**.

### 3. Deploy on Railway (5 min)

> *(After you, the bot operator, create a Railway template — see the "Operator setup" section below — replace this line with your actual button.)*

[![Deploy on Railway](https://railway.app/button.svg)](#REPLACE-WITH-TEMPLATE-URL)

Click the button. Railway will:

- Ask for `DISCORD_BOT_TOKEN` → paste from step 1.
- Ask for `PATREON_CREATOR_TOKEN` → paste from step 2.
- Auto-provision a persistent volume at `/data` (so the bot remembers tenure history across redeploys).
- Deploy.

### 4. Invite the bot to your Discord server (2 min)

In the Discord developer portal:

1. Sidebar → **OAuth2 → URL Generator**.
2. Check `bot` and `applications.commands`.
3. Under **Bot Permissions**, check `Manage Roles`.
4. Copy the URL at the bottom, open it, pick your server, **Authorize**.

### 5. Fix the role hierarchy (1 min)

In your Discord server: **Server Settings → Roles**. After invite, Discord auto-created a role for the bot (same name as your bot). **Drag it above the position you want `Loyal Foreman` to sit.**

> The bot can only assign roles ranked below its own. If you skip this step, the bot will log a warning and assign nothing.

### 6. Done

Within ~30 seconds the bot will:

- Post a message in your server's system channel confirming it's online.
- Create the `Loyal Foreman` role automatically.
- **Backfill existing long-time patrons**: anyone who's already been pledging to your campaign for 3+ months is granted the role on the first cycle. You don't have to wait 3 months from deploy day.
- Start checking Patreon every hour.

To test: run `/foreman-status` in Discord. (You'll need Manage Roles permission.) On first deploy you should see a big number in `granted` — that's the backfill.

> **How backfill is calculated**: on first sighting of each patron, the bot fetches their real charge history from Patreon and finds their most recent **unbroken monthly streak** of successful charges **on the Foreman tier specifically** (a gap bigger than one billing cycle + the grace period breaks the streak). Someone who paid for a month in 2025, lapsed, and came back last month gets credit only from last month. Months paid on a cheaper tier earn nothing — an upgrader's clock starts when they started paying for Foreman. If Patreon's records for a very old charge are missing tier information, that charge earns no credit (the bot always errs toward under-crediting); `/foreman-grant` is the manual fix for any patron who gets short-changed.

---

## Things not to do after deploy

- **Don't rename the `Loyal Foreman` role** in Server Settings. The bot remembers the role's ID after first run, so a rename is harmless *while the bot stays running* — but if the role is also deleted and the bot restarts, it'll create a fresh one with the original name. Safer to leave the name alone and just change the role's color/permissions.
- **Don't delete the Railway volume.** That's where tenure history lives. Deleting it resets every patron's 3-month clock to 0.
- **Don't change the `FOREMAN_TIER_NAME` env var** after deploy unless you actually renamed the tier on Patreon. The bot uses it to verify it's still pointed at the right tier on each startup.

## Configuration knobs (optional)

All seven of these can be overridden in Railway's **Variables** tab if you want different behavior:

| Variable | Default | What it does |
|---|---|---|
| `FOREMAN_TIER_NAME` | `Foreman` | Patreon tier the bot watches |
| `LOYAL_FOREMAN_ROLE_NAME` | `Loyal Foreman` | Discord role the bot grants |
| `TENURE_DAYS` | `90` | Days of continuous membership needed |
| `LAPSE_GRACE_DAYS` | `7` | Days a failed charge can stay declined without resetting the clock |
| `CHECK_INTERVAL_MINUTES` | `60` | How often to reconcile with Patreon |
| `DB_PATH` | `/data/tenure.db` | Where to store tenure history. Leave on `/data` on Railway. |

---

## Admin commands

Run in Discord; only visible to members with **Manage Roles** permission.

| Command | What it does |
|---|---|
| `/foreman-status` | Forces an immediate reconciliation; shows counts of foremen seen, tracked, granted, revoked. |
| `/foreman-check @user` | Shows that user's tenure: days continuous, last active charge, whether the role is granted. |
| `/foreman-health` | Runs every precondition check (Discord guild, role, hierarchy, members intent, DB, Patreon API, last cycle result) and reports a ✅/❌ list. Use this first when something seems off. |
| `/foreman-grant @user` | Manually grant the Loyal Foreman role and mark the user as fully tenured. Also clears any prior exclusion. Permanent — the hourly checks never remove a manual grant — until `/foreman-revoke` is run. If the user later appears on Patreon as a normally-linked Foreman, automatic tracking takes over. |
| `/foreman-revoke @user` | Remove the Loyal Foreman role and add the user to a sticky exclusion list. The reconciler will never auto-grant this role to them again — even if they keep paying — until you run `/foreman-grant` to clear the exclusion. |

## Automatic DM on first grant

When the bot grants the Loyal Foreman role to a member for the very first time (the tracker flips from "not granted" to "granted"), it sends them a short DM:

> Congrats! You've been a continuous Foreman patron of **[Server Name]** for 90+ days. You've just earned the **Loyal Foreman** role. Thanks for the loyal support.

If the member has DMs from server members disabled, the DM silently fails and the role is granted anyway — no error, no retry.

---

## Operator setup (one-time, for whoever publishes the template)

**You only need to do this once**, before sharing the bot. The recipient never sees these steps.

### A. Push the code to a public GitHub repo

```bash
cd discord_foreman_bot
git init
git add .
git commit -m "Initial commit"
gh repo create loyal-foreman-bot --public --source=. --push
```

(No secrets are in the repo — `.env` is gitignored.)

### B. Deploy it to Railway yourself, once

1. <https://railway.com/new/github> → pick your repo.
2. Paste your *own* `DISCORD_BOT_TOKEN` and `PATREON_CREATOR_TOKEN` to test (or just deploy and let it fail at startup — that's enough to make the template).
3. **Settings → Volumes** → add a volume mounted at `/data`, 1 GB.

### C. Turn the project into a public template

1. In the Railway project: **Settings → Templates → Create Template**.
2. Mark the two tokens as **required user inputs** (they'll be prompted to fill these on deploy).
3. Leave the rest as defaults (so the recipient never has to think about them).
4. Publish. Railway gives you a template URL like `https://railway.com/template/abc123`.

### D. Update the README with the template URL

Replace `#REPLACE-WITH-TEMPLATE-URL` in step 3 of the Quick Deploy section above with that URL. Commit + push. Now anyone clicking the "Deploy on Railway" button gets a one-screen form deploy.

### E. Send the creator this README

That's it. They click the button, paste two tokens, invite the bot, drag a role. Done.

---

## What it does NOT do

- It does not assign the base tier-based roles — Patreon's own Discord integration already does that.
- It does not DM anyone on grant/revoke. If you want a "congrats, you hit 3 months!" DM, add it to `scheduler.py` in the grant branch.
- It does not check pledge $ amount — only tier name. If you want $-based logic, that's a different rule than what we built.
- It is single-tenant — one bot instance per Discord server. If the same creator runs multiple servers, deploy it multiple times.

---

## File layout

```
discord_foreman_bot/
├── bot.py                Discord client, slash commands, startup auto-discovery
├── scheduler.py          Hourly Patreon→Discord reconciliation
├── patreon_client.py     Async Patreon API v2 wrapper + discover()
├── tenure_tracker.py     SQLite tenure store
├── config.py             Env-var loader
├── fetch_patreon_ids.py  Standalone helper — list campaigns+tiers (useful if discover() fails)
├── requirements.txt
├── Procfile / railway.json / runtime.txt
├── .env.example
├── .gitignore
├── README.md             This file
└── CO_SETUP_GUIDE.md     Manual setup walkthrough (fallback if Railway template isn't used)
```
