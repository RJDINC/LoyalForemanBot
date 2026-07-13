# Loyal Foreman Bot — Complete Setup Instructions

These instructions are written for the **Patreon creator** — the person whose Discord server and Patreon campaign the bot will work with. You do not need to know how to code. You will be clicking around three websites: Discord, Patreon, and Railway (a cloud hosting service).

Expect to spend about **30–45 minutes** the first time. Once it's running, you don't have to touch it again unless something breaks.

---

## What this bot does

It watches your Patreon campaign and automatically gives the **Loyal Foreman** role in your Discord server to anyone who has been on the **Foreman tier** for **90 days in a row** with no missed payments. If they fall behind on payments for more than 7 days, or drop off the tier, the bot takes the role back.

It uses Patreon's official Discord integration (the one that already auto-assigns tier roles), so your existing patrons don't have to link anything new. They just have to have their Discord connected on Patreon — which most of them already do.

---

## What you need before starting

Gather these so you don't have to stop mid-setup:

1. **A computer** (the bot itself runs in the cloud, but you'll use your computer to set things up).
2. **Login credentials** for:
   - Your Patreon **creator** account (the one that owns the campaign).
   - Your Discord account, with **Admin** or **Manage Server** + **Manage Roles** permissions on the server you want the bot in.
3. **A credit card or PayPal**. You'll be signing up for Railway, which hosts the bot. Their free tier should cover this — budget around **$5/month** as a safe upper bound; you'll almost certainly use less.
4. **A password manager** open (1Password, Bitwarden, Apple Keychain, your browser's built-in one — whichever you use). You'll be generating two secret tokens during setup, and they need to go somewhere safe. **Do not put them in a normal text file, a Discord DM, or an email.**
5. **About 45 minutes** uninterrupted.

---

## Step 1 — Create a Discord bot application (10 min)

A "Discord bot application" is just an account that the bot uses to log into Discord. You're going to create one.

1. Open <https://discord.com/developers/applications> in a new tab. Sign in with your Discord account if asked.
2. Click the blue **New Application** button in the top right.
3. Name it `Loyal Foreman Bot` (or whatever you want — it's just the bot's display name in Discord). Check the box agreeing to Discord's developer terms. Click **Create**.
4. You should land on the application's settings page. On the **left sidebar**, click **Bot**.
5. On the Bot page, scroll down to **Privileged Gateway Intents**. You'll see three toggles. **Turn ON** the one labeled **SERVER MEMBERS INTENT**. The others can stay off. Click **Save Changes** at the bottom.

   > This intent lets the bot see who's in your server. Without it, the bot can't assign anyone a role. If you skip this step, nothing will work — and there's no error message that says exactly that. Don't skip it.

6. Scroll back to the top of the same Bot page. Click the blue **Reset Token** button. Confirm "Yes, do it!" if it asks. A long string of characters appears underneath — **this is your DISCORD_BOT_TOKEN**.
7. **Copy that token.** Paste it into a new entry in your password manager labeled "Loyal Foreman Bot — Discord Token." Don't share it with anyone. Anyone who has this token can control the bot.

---

## Step 2 — Invite the bot into your Discord server (5 min)

1. Still on the Discord developer site, on the **left sidebar**, click **OAuth2**, then **URL Generator** (it might be a sub-item).
2. Under **SCOPES** (top section), check **two** boxes:
   - `bot`
   - `applications.commands`
3. After checking those, a new section called **BOT PERMISSIONS** appears below. Scroll down. Check **one** box:
   - `Manage Roles`
   - Leave everything else unchecked.
4. At the very bottom of the page, a **Generated URL** appears. Copy that URL and open it in a new tab.
5. The page that opens asks you to pick a server. Choose the Discord server you want the bot in. Click **Continue**, then **Authorize**, then solve any captcha. You should see "Authorized!" — close the tab.
6. Open your Discord server. You should see the bot has joined and is offline (it'll go online once we finish setup).

---

## Step 3 — Fix the role hierarchy in Discord (3 min)

This is the #1 thing people forget. The bot can only manage roles that are **ranked below its own role** in your Discord server. So:

1. In your Discord server, open **Server Settings → Roles**.
2. You'll see a role with the same name as your bot (e.g. "Loyal Foreman Bot"). Discord created this automatically when the bot joined.
3. **Drag that role upward.** You want it positioned ABOVE wherever you eventually want the "Loyal Foreman" role to sit. A safe choice is to drag it to the top of all non-admin roles.

   > If the bot's role is BELOW the Loyal Foreman role, the bot can see the role but can't assign or remove it from anyone. The bot will silently do nothing forever. This catches almost everyone. Make sure it's above.

4. You don't need to create a "Loyal Foreman" role yourself — the bot will create it automatically on first run.

---

## Step 4 — Get a Patreon Creator Access Token (5 min)

1. Open <https://www.patreon.com/portal/registration/register-clients> in a new tab. Make sure you're signed in as the campaign **creator**, not as a patron.
2. Click **Create Client**.
3. Fill in the form:
   - **App Name**: `Loyal Foreman Bot`
   - **Description**: `Internal Discord role bot for tenured patrons`
   - **App Category**: Anything (pick "Bot")
   - **Redirect URI**: `http://localhost` (this won't be used, but Patreon requires something)
   - **Privacy Policy URL** and **Terms of Service URL**: Use your Patreon page URL for both, e.g. `https://www.patreon.com/your-name`
4. Click **Create**. The new client appears on the same page.
5. Expand the client (click its name or an arrow). Look for **Creator's Access Token**. Click to reveal it. **This is your PATREON_CREATOR_TOKEN.**
6. Copy that token. Paste into your password manager as "Loyal Foreman Bot — Patreon Token." Like the Discord token, don't share this with anyone.

   > This token gives whoever holds it the ability to read your full patron list, including names, emails, and pledge amounts. Keep it safe like a password.

---

## Step 5 — Deploy the bot on Railway (15 min)

Railway is a service that runs the bot 24/7 in the cloud. You'll create a free account, paste in your two tokens, and click Deploy.

1. Open <https://railway.com/login> in a new tab. Click **Login with GitHub**. If you don't have a GitHub account, create one — it's free. If asked to authorize Railway to access your GitHub, say yes.
2. Once on the Railway dashboard, click **+ New Project** (top right) → **Deploy from GitHub repo**.
3. The bot's code lives at <https://github.com/RJDINC/LoyalForemanBot>. To deploy it, you first need a copy on your own GitHub account:
   - Open that link (sign into GitHub — you'll have created an account in the previous step when signing up for Railway).
   - Click the **Fork** button near the top right, then **Create fork** on the next screen. That's it — GitHub now shows the copy under your own account.
   - Back in Railway, pick **LoyalForemanBot** from the repo list. (If the list is empty, click **Configure GitHub App** and grant Railway access to your repositories.)
4. Railway starts building. The first build will probably FAIL — that's expected because we haven't set the tokens yet. Don't panic.
5. Click into the project. You'll see your bot as a "service" tile. Click the tile.
6. Click the **Variables** tab.
7. Click **Raw Editor**. Paste in this block, replacing the two `paste-here` lines with your tokens from your password manager:

   ```
   DISCORD_BOT_TOKEN=paste-here
   PATREON_CREATOR_TOKEN=paste-here
   TENURE_DAYS=90
   LAPSE_GRACE_DAYS=7
   CHECK_INTERVAL_MINUTES=60
   FOREMAN_TIER_NAME=Foreman
   LOYAL_FOREMAN_ROLE_NAME=Loyal Foreman
   DB_PATH=/data/tenure.db
   ```

   > If your Patreon tier is named something different than "Foreman" (capitalization-insensitive), change `FOREMAN_TIER_NAME` to match. Same for `LOYAL_FOREMAN_ROLE_NAME` if you want the Discord role named differently.

8. Click **Update Variables**.
9. Click the **Settings** tab. Scroll to **Volumes**. Click **+ Mount Volume**. Set:
   - **Mount Path**: `/data`
   - **Size**: 1 GB is plenty
   - Click **Add**.

   > This volume is where the bot stores its tenure database. Without it, every redeploy wipes everyone's 3-month progress. Don't skip this.

10. Click **Deployments** tab → click the latest deployment → click **Redeploy**.
11. Click the **View Logs** button on the deployment. You're watching the bot start up. Within ~30 seconds you should see something like:

    ```
    2026-06-24 ... Logged in as Loyal Foreman Bot (id=...)
    2026-06-24 ... Slash commands synced to guild ...
    2026-06-24 ... Patreon resolved: campaign=..., tier_name='Foreman', tier_id=...
    2026-06-24 ... Reconciliation cycle starting at ...
    2026-06-24 ... Reconciliation done: {'foremen_seen': N, 'granted': M, ...}
    ```

    If `granted` shows a number greater than 0, **the bot just gave the Loyal Foreman role to your existing long-time patrons.** Check your Discord server — they should have it now.

---

## Step 6 — Verify it's working (3 min)

Back in your Discord server, type `/foreman` in any text channel. Discord should auto-suggest several slash commands (only visible to people with Manage Roles permission):

- `/foreman-health` — **run this first**. It'll show a green/red checklist:
  - ✅ Bot initialized
  - ✅ Discord server resolved
  - ✅ Loyal Foreman role exists
  - ✅ Bot's top role is ABOVE the Loyal Foreman role
  - ✅ Server Members Intent appears enabled
  - ✅ SQLite database is writable
  - ✅ Patreon API + 'Foreman' tier found
  - ✅ Last cycle: ... (seen=N, tracked=N)

  If anything has a ❌, the description tells you what's wrong. The most common issues:
  - ❌ Hierarchy → go back to Step 3.
  - ❌ Members Intent → go back to Step 1.5.
  - ❌ Patreon API → your token is wrong or expired. Go back to Step 4, generate a fresh one, update it in Railway Variables, redeploy.

- `/foreman-status` — forces a fresh check against Patreon right now and reports counts.
- `/foreman-check @somepatron` — shows that specific person's tenure (how many days they've been continuous, when the bot last saw them paid, whether they have the role).

If `/foreman-health` is all green and `/foreman-status` shows reasonable numbers, **you're done with setup**.

---

## Day-to-day operation

After setup, the bot runs on its own. You don't have to do anything. Here's what happens automatically:

- **Every hour**, the bot checks Patreon for every Foreman-tier member, updates their tenure record, and grants/revokes the role as appropriate.
- **When a member crosses 90 days continuous**, they get the Loyal Foreman role AND a DM saying congrats. (If they have DMs disabled, they just get the role with no message — no error.)
- **If a member's payment fails** for more than 7 days, the role is removed and their clock resets to zero. They have to rebuild 90 days again.
- **If a member drops off the Foreman tier** entirely (canceled, downgraded), the role is removed immediately on the next hourly check.
- **If a long-time Foreman just joined your server**, the bot grants their role on the next hourly check (up to 1 hour wait — this is deliberate, it gives Patreon's data time to sync).

### Admin commands you can use anytime

| Command | What it does |
|---|---|
| `/foreman-status` | Force a fresh check now. See counts. |
| `/foreman-health` | Run all the green/red checks. Use this whenever something seems off. |
| `/foreman-check @user` | See one specific person's tenure data. |
| `/foreman-grant @user` | Manually give someone the role and mark them as already-tenured. Useful if their Discord wasn't linked on Patreon and the bot missed them. The grant is permanent (the hourly checks won't undo it) until you run `/foreman-revoke` on them. |
| `/foreman-revoke @user` | Take the role away and add the person to a permanent exclusion list. The bot will never auto-grant it to them again (even if they keep paying) until you run `/foreman-grant` on them to undo. |

All of these are **invisible to non-admins** — only people with the Manage Roles permission see them.

---

## Things NOT to do after setup

- ❌ **Don't rename the `Loyal Foreman` role** in your Discord server. The bot remembers the role's internal ID after the first run, so renaming is harmless **while the bot is running** — but if it ever restarts and finds the role deleted, it will create a new one with the original name. Easier to just leave the name alone and only change its color or position.
- ❌ **Don't delete the Railway volume.** That's where the tenure history lives. Deleting it resets everyone's 3-month progress to zero on the next deploy.
- ❌ **Don't share your Patreon Creator Access Token or Discord Bot Token with anyone.** Both give full bot/account access. If you suspect either was leaked, rotate it (regenerate at the same page you got it from), update the Railway env var, and redeploy.
- ❌ **Don't add the bot to multiple Discord servers.** It's built for one. It'll log a warning and pick the first one it sees — which might not be the one you wanted.

---

## Troubleshooting

### "The bot is in my server but never gives anyone the role"

Run `/foreman-health` first. If everything's green, the most likely causes are:

1. **No one has hit 90 days yet.** Run `/foreman-check @somepatron` on a known long-time patron — does it show 90+ days?
2. **The patron hasn't linked their Discord account on Patreon.** The bot can only act on patrons who've connected their Discord through Patreon's official integration. Ask them to go to <https://www.patreon.com/settings/apps> and connect Discord.
3. **You're checking the wrong tier name.** Open `/foreman-status` — if `foremen_seen` is 0, the bot isn't finding any Foreman-tier patrons. Either the tier doesn't exist or the name doesn't match. Double-check the `FOREMAN_TIER_NAME` variable in Railway matches your Patreon tier exactly (case doesn't matter).

### "The bot gave someone the role but they don't deserve it"

The bot might be over-counting tenure for patrons who upgraded to Foreman from a lower tier. Patreon's API tells us when they first pledged to your campaign, not when they specifically joined the Foreman tier — so someone who was Apprentice for a year and upgraded to Foreman last week will get the role. If this is wrong for a specific person, run `/foreman-revoke @them` to take it away permanently.

### "The bot is offline"

Open the Railway dashboard. Click your project. Look at the **Deployments** tab.

- If the latest deployment shows "Crashed" or "Failed", click into it and read the logs. Most common cause: an env var was deleted or has a typo.
- If it's stuck in "Building" for more than a few minutes, click "Cancel" then "Redeploy".
- If the latest deployment shows "Active" but `/foreman-health` says "Bot initialized" is ❌, the bot is connected to Discord but failed to start up. Re-read the logs — it'll tell you what's wrong (usually a bad Patreon token or wrong tier name).

### "I'm getting charged more than I expected on Railway"

Railway charges for usage (CPU + memory + storage). This bot is tiny — should cost under $5/month at most. If it's higher:

- Check **Settings → Usage** in Railway. There's a graph of what's consuming resources.
- Make sure you only have ONE service in this project (the bot), not multiple.
- If you accidentally invited the bot to a very large Discord server, member-fetching could spike costs. Kick the bot from any server you didn't intend.

### "I want to change something later"

| Change | How |
|---|---|
| Different tier name (e.g. you renamed it on Patreon) | Update `FOREMAN_TIER_NAME` in Railway Variables → redeploy. |
| Different role name (e.g. you want it called "Veteran" instead) | Update `LOYAL_FOREMAN_ROLE_NAME` in Railway Variables → redeploy. The bot will create the new role on next startup. **Manually delete the old role** in Discord afterward. |
| Different tenure (e.g. 60 days instead of 90) | Update `TENURE_DAYS` in Railway Variables → redeploy. |
| Different grace period (e.g. 30 days instead of 7) | Update `LAPSE_GRACE_DAYS` in Railway Variables → redeploy. |
| Tokens leaked or rotated | Update the relevant variable in Railway → redeploy. Don't reuse the old token, even briefly. |

After any change, run `/foreman-health` to confirm the bot picked up the new value.

---

## What the bot stores about your patrons

For transparency:

- **Discord user ID** (a number, not a username) — so the bot knows who to grant the role to.
- **Patreon member ID** (another number) — so the bot can match Patreon data to its records.
- **Tenure dates** — when they first hit the Foreman tier, when the bot last saw their charge succeed.
- **Role status** — whether the bot has granted them the Loyal Foreman role yet.

The bot does NOT store:
- Names, emails, addresses, or payment information.
- Anything posted in your Discord server.
- DMs.
- Anything outside what's strictly needed to decide "do they deserve the role today?"

All data lives in a SQLite file on the Railway volume. If you ever decommission the bot, deleting the Railway project deletes everything.

---

## Getting help

If something's going wrong and `/foreman-health` doesn't make the cause obvious:

1. Open Railway → your project → **View Logs**.
2. Take a screenshot of the last 30 lines.
3. Send it to the person who set this up for you, along with a description of what's happening (e.g. "ran `/foreman-status`, got no response").

The logs almost always show exactly what's wrong — they'll either reveal the issue or give a clear error message that points at one.
