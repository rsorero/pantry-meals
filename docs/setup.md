# Set up your own copy

Rubadubdub runs as an artifact in your own claude.ai account, with its own database.
Nothing is shared with anyone else's copy, and nothing in this repo is tied to one account.

## What you need

- A Claude plan with artifacts and scheduled tasks.
- A Claude Code session on claude.ai (web, desktop or mobile app) with this repo: fork
  it on GitHub, or start a session from it directly.
- That's all. The app uses no API keys: Claude features run on each viewer's own Claude
  usage.

## The quick way

In the session, say:

> Set up Rubadubdub for me, following docs/setup.md.

Claude does the steps below and asks you two things: your time zone (for the lookup
schedule) and, optionally, where you live and shop.

## Steps (for Claude)

1. **Check for an existing copy.** `list_artifacts` with query `Rubadubdub`. If one
   marked `mine` exists, don't create another: deploy to it as described in `CLAUDE.md`.
2. **Test.** Run `python3 tests/smoke.py` (install with
   `pip install playwright && playwright install chromium`) and
   `python3 tools/check_secrets.py`. Both must pass.
3. **Create the artifact.** `publish_files` with no slug, title `Rubadubdub`, icon
   `kitchen`, and files:
   - `app/index.html` → `index.html`
   - `tools/lookup.py` → `tools/lookup.py.txt`
4. **Declare capabilities.** `declare_capabilities` on the new slug:
   `{db:{}, user:{}, sample:{images:true}}`. Then republish the same files with
   `mode: "patch"` and the new `base_version`, so the page loads with them.
5. **Create the lookup task.** Ask the person's time zone. Then `create_trigger`:
   - name `Rubadubdub product lookups`
   - cron `CRON_TZ=<their IANA zone> 39 7,9,11,13,17,19,21 * * *`
   - notifications off
   - prompt: the text in the code block of `docs/lookup-task.md`, with `{{ARTIFACT_SLUG}}`
     and `{{ARTIFACT_URL}}` replaced by the new artifact's slug and URL.

   If creating it is refused or needs approval, tell the person what the task does and let
   them approve it. Say which approval setting it got.
6. **Location (optional).** If the person says where they live and shop, write it with
   `db_write` op `merge` to `settings/home`, data `{"id":"home","where":"<their words>"}`.
   They can also set it on the Meals tab under "Where you live and shop".
7. **Hand over.** Give the artifact link, and tell them:
   - Add a receipt photo on the Add tab to fill the pantry.
   - Product details appear after the next scheduled run.
   - To share with the household, use the share menu on claude.ai. People who should
     edit need Editor access. Each person's Claude features use their own Claude usage.

## Network for the lookup task

Each run downloads product data from `tienda.mercadona.es` (Mercadona's Spanish online
shop) and `world.openfoodfacts.org`. If a run reports it can't reach them, allow those two
hosts in the network settings of the environment your scheduled tasks use.

## Good to know

- **Prices are shown in euros.**
- **Name-based product lookups search Mercadona's Spanish catalogue.** If you shop
  elsewhere, scan or photograph barcodes: those are looked up on Open Food Facts, which
  covers products worldwide.
- **Updating:** pull the latest changes into your fork, then ask Claude to deploy
  (`CLAUDE.md` has the steps). Your data stays in place.
