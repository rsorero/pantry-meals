# Handoff: continuing work on Rubadubdub

For a new Claude Code session picking this up. Read `CLAUDE.md` first: it has the deploy
steps, the checks to run before publishing, the code conventions and the secrets rules.
This file adds where things stand, what's open, and what tripped us up before.

## Where things stand (26 November 2026)

- **The app** is live as the owner's claude.ai artifact, titled **Rubadubdub**
  ("Stock, shop, cook"). Find it with `list_artifacts` query `Rubadubdub`, entry marked
  `mine`. It is shared only with its owner (`read: owner`). Its database holds the
  household's real pantry: never wipe or reseed it.
- **This repo** (public, GPL-3.0) is the source of truth. History was squashed to one
  clean commit before it went public, so personal data never appears in it.
- **Product lookups** run as the owner's scheduled task **Rubadubdub product lookups**
  (find it with `list_triggers`), seven times a day. It reads `tools/lookup.py.txt` from
  the artifact, so republish `tools/lookup.py` whenever it changes.
- **Location** (city, usual shop) is the `settings/home` document, set on the Meals tab.
  It is never in code.

## What the app does

| Tab | What's there |
|---|---|
| Pantry | Stock by shelf (fruit and veg, fridge, freezer, cupboard, drinks, household), +/− and Empty, search, store filter, item sheet with product details |
| Add | Receipt photo or text, product photos, barcode, by hand. Everything Claude reads is reviewed before it's added |
| List | Shopping list grouped by store, last price and place bought, estimated total |
| Meals | One meal or several days from what's in stock, options (servings, time, shopping, nutrition focus, kitchen equipment, notes, location), nutrition per serving and per day, recipe, Tweak, Cooked it, favourites |

Data model: `docs/data-model.md`. Lookup flow: `docs/lookup-task.md`. Setting up a new
copy: `docs/setup.md`.

## Design

The visual system is described in the comment at the top of the `<style>` block in
`app/index.html`:

- **Look:** a market stall. Leaf-green awning header (scalloped on phones), tomato for
  primary actions, butter for counts.
- **Type:** Fraunces (soft, wonky) for titles, Rethink Sans for body text.
- **Shapes:** pills for toggles and steppers, 14 px radius for buttons and fields, 20 px
  and up for surfaces.
- **Phone first:**
  - item names get their own line;
  - controls sit in thumb reach;
  - shelf labels are sticky;
  - meal options are folded behind a summary line;
  - the nav is a bottom bar under 600 px.

Keep new screens in that system, check them at 390 px (and 320 px for wrapping), and in
dark mode.

## Open items

1. **Standalone version (no Claude login), proposed but not started.** The owner asked
   whether the app could run fully independently. The proposal:
   - Cloudflare Pages for hosting;
   - Supabase for the database, email-link sign-in and per-household row-level security;
   - a Cloudflare Worker holding an Anthropic API key, which calls Claude and also does
     product lookups directly, so the scheduled task isn't needed.

   The owner hasn't said go yet. Next steps if they do:
   - Check current Claude API prices and estimate monthly cost.
   - Plan the schema, the Worker and the data migration.
   - The owner creates the accounts and keys and pastes secrets themselves. Never handle
     keys for them.
2. **Lookup task wording.** The scheduled task's prompt still calls the app "Pantry &
   Meals". This is cosmetic, because it finds the artifact by slug. A prompt update was
   blocked by the safety check, so do it only when the owner asks and approves.
3. **Limits for other households.**
   - Prices show in euros.
   - Name-based product lookups search only Mercadona's Spanish online shop. Barcode
     lookups use Open Food Facts and work anywhere.

## Things that tripped us up

- **Repo settings** (visibility, rename, description) can't be changed through the shell's
  GitHub proxy (403). Use the built-in browser, where the owner is signed in.
- **Downloading and running binaries** such as gitleaks is blocked here. The GitHub
  workflow runs gitleaks on every push instead; check the Actions tab.
- **Creating or editing scheduled tasks** can be stopped by a safety check. Explain what the
  change does and let the owner approve it.
- **`publish_files` won't serve `.py`,** hence `tools/lookup.py` → `tools/lookup.py.txt`.
- **The smoke test** runs the page from `file://` with a simulated Claude and localStorage.
  The "Saved on this device only" banner in its screenshots is expected. Meal options
  start folded: open `#popts` before touching fields inside it.
- **`tools/check_secrets.py`** also reads a git-ignored `.private-words` list. It isn't in
  the repo, so in a fresh clone, ask the owner whether they want one recreated with their
  own words.

## Before you finish any change

1. `python3 tests/smoke.py` passes (add a check for new flows), `python3 tools/check_secrets.py`
   passes, and `node --check` on the last `<script>` is clean.
2. Look at `tests/out/` screenshots at phone width.
3. Deploy as in `CLAUDE.md`, then commit and push to `main`.
