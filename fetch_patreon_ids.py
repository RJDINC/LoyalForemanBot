"""
Standalone helper: prints every Patreon campaign + tier visible to a given
Creator Access Token. Use during setup to figure out which IDs to paste into
the bot's env vars.

Usage:
    pip install aiohttp
    python fetch_patreon_ids.py

You'll be prompted for the token (input is hidden, NOT stored anywhere).
"""

from __future__ import annotations

import asyncio
import getpass
import sys

import aiohttp

API = "https://www.patreon.com/api/oauth2/v2"


async def main() -> int:
    print("This script will list every campaign and tier your Patreon token can see.")
    print("It does NOT save the token anywhere — it's only used for this one API call.\n")

    token = getpass.getpass("Paste your Patreon Creator Access Token (input hidden): ").strip()
    if not token:
        print("No token entered — aborting.")
        return 1

    headers = {"Authorization": f"Bearer {token}"}
    async with aiohttp.ClientSession(headers=headers) as session:
        params = {
            "include": "tiers",
            "fields[campaign]": "creation_name,vanity",
            "fields[tier]": "title,amount_cents",
        }
        async with session.get(f"{API}/campaigns", params=params) as resp:
            if resp.status != 200:
                body = await resp.text()
                print(f"\nPatreon API error {resp.status}: {body[:400]}")
                return 1
            payload = await resp.json()

    tiers_by_id = {
        item["id"]: item["attributes"]
        for item in payload.get("included", [])
        if item.get("type") == "tier"
    }

    campaigns = payload.get("data", [])
    if not campaigns:
        print("\nNo campaigns found for this token. Are you signed in as the creator?")
        return 1

    bar = "=" * 72
    print(f"\n{bar}\n YOUR PATREON CAMPAIGNS + TIERS\n{bar}")
    for c in campaigns:
        cid = c["id"]
        attrs = c.get("attributes", {})
        name = attrs.get("creation_name") or attrs.get("vanity") or "(unnamed)"
        print(f"\nCAMPAIGN   id = {cid}   name = {name}")

        refs = (c.get("relationships", {}).get("tiers") or {}).get("data") or []
        if not refs:
            print("   (no tiers visible)")
            continue
        for ref in refs:
            t = tiers_by_id.get(ref["id"], {})
            title = t.get("title", "(unknown)")
            amount = (t.get("amount_cents") or 0) / 100
            print(f"   TIER    id = {ref['id']:<10}  ${amount:>6.2f}/mo   {title}")

    print(f"\n{bar}")
    print("Put these into Railway's Variables tab:")
    print("   PATREON_CAMPAIGN_ID       = the campaign id above")
    print("   PATREON_FOREMAN_TIER_ID   = the tier id whose title is 'Foreman'")
    print(bar)
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
