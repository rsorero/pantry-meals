# Handoff: continuing work on Rubadubdub

For a new Claude Code session picking this up. Read `CLAUDE.md` first: it has the deploy
steps, the checks to run before publishing, the code conventions and the secrets rules.
This file adds where things stand, what's open, and what tripped us up before.

## Where things stand (26 November 2026)

- **The app** is live as the owner's claude.ai artifact, titled **Rubadubdub**
  ("Stock, shop, cook"). Find it with `list_artifacts` query `Rubadubdub`, entry marked
  `mine`. It is shared only with its owner (`read: owner`). Its database holds the
  household's real pantry: never wipe or reseed it.
- **This repo** (public, AGPL-3.0) is the source of truth. History was squashed to one
  clean commit before it went public, so personal data never appears in it.
- **Product lookups** run as the owner's scheduled task **Rubadubdub product lookups**
  (find it with `list_triggers`), seven times a day. It reads `tools/lookup.py.txt` from
  the artifact, so republish `tools/lookup.py` whenever it changes.
- **Location** (city, usual shop) is the `settings/home` document, set on the Meals tab.
  It is never in code.

## What the app does

| Tab | What's there |
|---|---|
| Pantry | Stock by shelf (fruit and veg, fridge, freezer, cupboard, drinks, household), a "Use soon" group for expired and soon-expiring items, +/− and Empty, search, store filter, item sheet with product details, purchase date, "View receipt" and expiry date (scan, enter, confirm) |
| Add | Receipt photo or text, product photos (expiry dates read from the same photos), barcode, by hand. Everything Claude reads is reviewed before it's added. Past receipts open in a viewer with the photo beside the lines |
| List | Shopping list grouped by shop, with shop filter pills; each entry can have its own shop (tap its name to change shop, amount or note). Last price and place bought; the count and estimated total are in the header |
| Meals | One meal or several days from what's in stock, options (servings, time, shopping, nutrition focus, kitchen equipment, notes, location), nutrition per serving and per day, recipe, Tweak, Cooked it, favourites |

Data model: `docs/data-model.md`. Lookup flow: `docs/lookup-task.md`. Setting up a new
copy: `docs/setup.md`.

## Design

The visual system is described in the comment at the top of the `<style>` block in
`app/index.html`:

- **Look:** a market stall. Leaf-green awning header (scalloped on phones), tomato for
  primary actions, butter for counts.
- **Type:** Instrument Sans throughout: condensed bold for titles, normal width for body text.
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

## Backlog

Requested by the owner on 26 November 2026, in their order. Each item needs the usual
checks, a smoke-test check, screenshots at 390 px, and a deploy.

### 1. Choose a nicer font (done, 27 November 2026)

- Compared three Google Fonts pairings against Fraunces + Rethink Sans in the real app.
  The owner chose **Instrument Sans** for everything: titles condensed bold
  (`font-stretch:85%`), body text at normal width. It is the lightest to load (about 55 KB).
- Google Fonts do load inside the claude.ai artifact (seen on the live page), so no
  self-hosted fonts are needed.
- Its spaces are narrow, so small secondary text gets `word-spacing:.12em` (the rule after
  the `h1,h2` font rules) to keep "Shop · €1.00" readable.

### 2. Show the shopping list total in the heading (done, not yet deployed)

- **Built:** on the List tab the header shows "N to buy" and "≈ €X estimated" for the whole
  list (`render()`, using `sumS()`), plus "Shared live" when online. The estimate card is
  gone; the price note, the count without a price and the in-basket estimate are one quiet
  line (`.listnote`) under the list. Pantry keeps its stats; Add and Meals hide them.
- **Before:** on the Pantry tab, the green header shows stats (in stock, out or low, value).
  On the List tab, the estimate sits in a separate card under the "Add to list" field
  (`renderList()`, the `.card` with `.nutl`).
- **Do:**
  - Show the list's figures in the header stats while on the List tab, for example
    "2 to buy" and "≈ €1.60 estimated", and drop the separate card.
  - Keep the "based on the last price you paid" note, and the count of items with no
    price yet, as one quiet line under the list.
- **Hint:** header stats are hidden on other tabs through `body[data-tab]`. Render
  per-tab stats into `#stats` from `render()`.

### 3. History tab (parked, 27 November 2026)

The owner widened "receipt history" into a **History tab covering everything**: pantry
changes, additions (receipts, photos, barcodes, by hand), the shopping list and meals.
It should be easy to filter and search, with summaries (spend per month and per shop and
the like). Parked for now because it changes how the app is used. When it's picked up,
build it on its own branch and test it separately before merging.

- **Design point:** the app stores current state, not events. Only receipts (`receipts/`),
  meal plans (`plans/`) and cooked meals can be rebuilt for the past. Everything else needs
  a new event log (e.g. `history/{id}` = `{t, kind, itemId?, ...}`) written from `put`/`del`
  call sites from the day it ships. Mind the db size: keep events small and prune old ones.
- **Already there:** the "Past receipts" list on the Add tab, receipt photos (`image`), each
  line's `itemId`, and `openReceipt(id, line)`, which shows the photo beside the lines.

### 4. Filter the shopping list by shop (done, not yet deployed)

- **Built:**
  - Optional `store` on `shopping/{id}`; `shopOf(entry)` gives its own shop, else the item's
    last shop, else "" (Anywhere). Grouping and the filter both use it.
  - `#sfilt` pills (All, then each named shop among the entries, open or ticked), hidden with
    fewer than two shops. A shop filter also shows "Anywhere" entries, and "Clear ticked" and
    "Put ticked in pantry" act on the ticked entries shown.
  - "Add to list" has an optional shop field (`#sst`, `#storeDL`); typed names are matched
    to known shops case-insensitively (`canonStore()`). Adding something already on the list
    sets the chosen shop on that entry.
  - Tapping an entry's name opens `openEntry()`: shop, amount, note, Save, Cancel and "Back
    to automatic".
  - Putting a ticked entry with its own shop in the pantry records that shop on the item.
- **Before:**
  - The List tab groups items by the shop they were last bought at
    (`mainStore(item).name`), with "Anywhere" for the rest.
  - There's no filter.
  - A list entry can't name a shop of its own.
- **Do:**
  - Add shop filter pills above the list, like the Pantry tab's `#pfilt`: All, then each
    shop that appears in the list.
  - When adding to the list by hand, offer an optional shop. Choose from known shops
    (`allStores()`; the `#storeDL` datalist already exists) or type a new one.
- **Data:** add an optional `store` to `shopping/{id}`. The entry's shop is its own
  `store` if set, otherwise the item's last shop, otherwise "Anywhere". Update
  `docs/data-model.md`.
- **Also:** let an entry's shop be changed later, for example from a small sheet when
  tapping the entry.

## Receipt links and expiry dates (added 26 November 2026)

- **Deployed** on 26 November 2026 as artifact version 12, with `assets` declared. The publish
  tool now wraps the page in its standard document skeleton; the smoke test passes against
  the published file as served.

- Items remember the receipt and line they came from (`receipt`); receipts remember each
  line's item (`itemId`) and keep the photo through the `assets` capability. **`assets:{}`
  must be declared on the artifact before this version is published**, or receipts save
  without photos (lines still work).
- Expiry: `expirationDate` (`YYYY-MM-DD` or `YYYY-MM`) with `expirationSource`
  (`ocr` | `manual`). Claude only copies the date as printed; the app's `expCands()` works
  out what it can mean, in the browser locale's day/month order. One reading is saved as
  `ocr` and flagged "please check"; several readings are offered as a choice (or, in the
  product photo review, prefilled with the alternatives shown) rather than saved silently.
- Not done: the date input shows in the phone's own format, and "Month only" is a checkbox
  because date inputs can't hold a month alone.

## Things that tripped us up

- **Repo settings** (visibility, rename, description) can't be changed through the shell's
  GitHub proxy (403). Use the built-in browser, where the owner is signed in.
- **Downloading and running binaries** such as gitleaks is blocked here. The GitHub
  workflow runs gitleaks on every push instead; check the Actions tab.
- **Creating or editing scheduled tasks** can be stopped by a safety check. Explain what the
  change does and let the owner approve it.
- **`publish_files` won't serve `.py`,** hence `tools/lookup.py` → `tools/lookup.py.txt`.
- **The smoke test** serves `app/` from a local HTTP server (so `/_blob/` photo URLs can be
  answered) with a simulated Claude, asset store and localStorage. Install the Python
  `playwright` package at the same version as the preinstalled browser.
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
