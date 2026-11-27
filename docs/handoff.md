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
| History | Everything that happened (pantry, adding, list, meals), with search, kind, date, shop and item filters, and summaries of spend per month and shop, most bought items, meals cooked and waste. Entries from before logging started are rebuilt from receipts, plans, favourites and items |

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

### 2. Show the shopping list total in the heading (done, 27 November 2026)

- On the List tab the header shows "N to buy" and "≈ €X estimated" for the whole list
  (`render()`, using `sumS()`), plus "Shared live" when online, whatever shop filter is on.
  The separate estimate card is gone; the price note, the count without a price and the
  in-basket estimate are one quiet line (`.listnote`) under the list. Pantry keeps its
  stats; Add and Meals hide them.

### 3. History tab (built, not deployed yet, 27 November 2026)

Built on branch `claude/tender-shannon-wpk5o1` and tested on a private preview copy (test data
only, no capabilities). **Not deployed:** the owner deploys only after trying the preview.
Delete the preview artifact once they approve.

- **The owner's choices:** a fifth tab; every kind of event; summaries for spend per month,
  spend per shop, most bought items, and meals cooked and waste; keep 12 months, max 3000
  events.
- **Event log:** `history/{id}`, written by `logEv(kind, {...})` at the call sites that matter,
  never inside `put`/`del`. Undo calls `unlog(id)`. Kinds and fields are in
  `docs/data-model.md`. `settings/history.started` records when logging began.
- **Before logging:** `hRebuilt()` rebuilds entries in the browser from receipts, plans, favourites
  and items, marked "Before history", never written. It skips anything a logged event already
  covers, so nothing shows twice.
- **Pantry Save button (owner's request):** +, − and Empty no longer save straight away. They
  change the screen (`PEND`, kept in `localStorage` `pm-pend`), a bar above the nav offers
  Save or Discard, and leaving the tab reminds you. Save writes one `amount` or `used` event per
  item. Other places that change amounts (Cooked it, receipts, the barcode "Add 1") still save at
  once; the owner confirmed Cooked it stays that way. **This changes how the Pantry is used:** other household members see the new amounts
  only after Save.
- **Tab:** search (`#hq`), kind pills (multi), date pills (This month, Last month, Last 3 months,
  This year, Pick dates), shop pills (multi, shown with two or more shops), and an item filter
  set from an event's sheet ("Only this item"; it also matches receipts and cooked meals that used
  the item). A summary card on top uses the date and shop filters; it starts folded and remembers whether it was opened (`pm-hsum`). Events are grouped by
  day; tapping one opens a sheet with links to the receipt, item or plan.
- **Smoke checks:** "unsaved pantry changes", "history log" and "history tab" in
  `tests/smoke.py`. Screenshots `7-savebar`, `8-history*`.

### 4. Filter the shopping list by shop (done, 27 November 2026)

- **The owner's rule:** a shop on a list entry means "buy it there", and only the user sets
  it. Without one the entry is for **anywhere**, even if the item was last bought at a
  particular shop, and can be ticked off wherever it's bought. The last shop and price
  still show on the entry and feed the estimate. "Banana" at Mercadona and "Banana"
  anywhere are two separate entries; the shop is an attribute, never part of the name.
- Optional `store` on `shopping/{id}` (see `docs/data-model.md`); `shopOf(entry)` is just
  that. Grouping ("At Corner shop", "Anywhere") uses it.
- **Adding:** one search bar (`#sq`, styled like the Pantry search) both filters the list and
  suggests things to add (`renderAdd()`, `#sadd`): matching pantry items, plus the typed
  text as something new. Tapping one (or Enter for the first) opens `openAdd()`, a sheet
  with shop chips, amount and note. Escape clears the search.
- **Shop chips** (`shopPick()`, `wireShopPick()`, `shopRead()`): Anywhere (default), each
  known shop, and "+ New shop" with a text box. Typed names take the spelling of a known
  shop (`canonStore()`). The entry sheet (`openEntry()`, tap an entry's name) uses the same
  chips; moving an entry onto one that already exists combines the two.
- **Shop filter** (`#sfilt`, `listF` is a Set): pick any number of shops; tapping a chosen
  one again removes it, All clears. Anywhere entries show under every choice. "Clear
  ticked" and "Put ticked in pantry" act on the ticked entries shown. Pills hide with fewer
  than two shops.
- `addToList()` merges only into an entry for the same shop. `clearFromList(item, shop)`
  clears the anywhere entry and that shop's entry.
- **One design across screens** (owner's request): every shop choice uses the same chips,
  from the "shop chips" section near the top of the script: the List tab's add and entry
  sheets (none = "Anywhere"), and Add by hand, Edit item, the barcode sheet and the receipt
  and photo review (none = "Not recorded"). The browser's own suggestion list (`datalist`)
  is gone. The Add-by-hand name suggestions (`ac()`, `.acl`) use the same rows as the List
  tab's "Add to the list" suggestions.

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

- **Deploy tool names.** `CLAUDE.md` names `list_artifacts`, `get_artifact`, `publish_files` and
  `declare_capabilities`, which some sessions don't have. Then use the Artifact tool: `list` and
  find "Rubadubdub" marked mine, `read` it, and publish `app/index.html` with that `url`.
  Capabilities stay `{db:{}, user:{}, sample:{images:true}, assets:{}}`.
- **Previews.** To let the owner try a change first, publish a separate private copy as a new
  artifact, with no capabilities, and an inline script that seeds `localStorage` `pm-local`
  from `tests/fixtures/state.json`. Don't put "Rubadubdub" in its title, so the deploy search
  still finds one match. Delete it once the owner approves.

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
