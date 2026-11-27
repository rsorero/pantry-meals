# Handoff: continuing work on Rubadubdub

For a new Claude Code session picking this up. Read `CLAUDE.md` first: it has the deploy
steps, the checks to run before publishing, the code conventions and the secrets rules.
This file adds where things stand, what's open, and what tripped us up before.

## Where things stand (27 November 2026)

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
- **Live version:** artifact version 24, published from branch `ccr-b953f308-np64mv` (Look up
  now, camera and gallery tray, live camera, more lookup sources, non-food items), which
  includes `main` up to #7. Once that branch is merged, the live app matches `main`. Until then,
  deploying `main` alone would remove those features and leave the `mcp` capability unused (see
  "Parallel sessions" below).

## What the app does

| Tab | What's there |
|---|---|
| Pantry | Stock by shelf (fruit and veg, fridge, freezer, cupboard, drinks, household), a "Use soon" group for expired and soon-expiring items, +/− and Empty, search, store filter, item sheet with product details, purchase date, "View receipt" and expiry date (scan, enter, confirm) |
| Add | Receipt photo or text, product photos (expiry dates read from the same photos), barcode, by hand. Everything Claude reads is reviewed before it's added. Past receipts open in a viewer with the photo beside the lines |
| List | Shopping list grouped by shop, with shop filter pills; each entry can have its own shop (tap its name to change shop, amount or note). Last price and place bought; the count and estimated total are in the header |
| Meals | One meal (three ranked options) or several days from what's in stock, options (servings, time, shopping, nutrition focus, kitchen equipment, notes, location), collapsible meal cards, nutrition per serving and per day, recipe, Tweak, Cooked it, favourites |
| History | Everything that happened (pantry, adding, list, meals), with search, kind, date, shop and item filters, and summaries of spend per month and shop, most bought items, meals cooked and waste. Entries from before logging started are rebuilt from receipts, plans, favourites and items |

Every tab has a line of figures in the header (Pantry: stock, low, use soon, value; Add:
receipts kept, spent this month; List: to buy, estimated; Meals: meals to cook,
favourites; History: see item 3), followed by the connection status. See backlog item 5.

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
2. **Lookup task prompt** updated on 27 November 2026 at the owner's request to the text in
   `docs/lookup-task.md` (new name, more barcode databases, web search fallback, non-food
   items, network errors left pending). Keep the two in step when either changes.
3. **Unresolved: no camera in the Claude phone app (Android), parked by the owner on
   27 November 2026.** Every photo button (Barcode, Scan barcode, Scan for expiry, the receipt,
   and "Take a photo" in Product photos) opens only the photo gallery. What we tried:
   - Version 19 and earlier: inputs with `capture="environment"`. Tapping them did nothing.
   - Version 23: `capture` removed. The buttons work but open only the gallery; the Claude
     app's file picker offers no camera.
   - Version 24: a live in-page camera (`camOpen()`, `getUserMedia`), with a fallback to the file
     picker when the camera isn't allowed. On the phone the owner still gets only the gallery
     and didn't report the camera view or the "camera isn't available" message. So `liveOK()`
     is probably false there (the frame's permissions policy doesn't allow `camera`, or
     `pm-nocam` was set by an earlier refusal), and the tap goes straight to the picker.
   - Not checked: Android Settings → Apps → Claude → Permissions → Camera; the app in a phone
     browser (Chrome on claude.ai), where `capture` and the live camera should both work.

   Next time: first find out which case it is on the phone. A small debug line on the Add tab
   could show `liveOK()`, the permissions-policy answer and `pm-nocam`. If the artifact frame
   doesn't allow the camera, it's a claude.ai limit: suggest the browser, or take photos with
   the phone camera first and pick them from the gallery. Also check with the owner whether the
   barcode scan that worked early on 27 November was in a browser.
4. **Limits for other households.**
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
  stats. (Add and Meals hid theirs at first; item 5 gave them their own.)

### 3. History tab (done, deployed 27 November 2026)

Built on branch `claude/tender-shannon-wpk5o1`, tried by the owner on a private preview copy
(test data only, no capabilities; deleted after approval), merged with main (#3, the header
figures and connection indicator) and deployed with the Artifact tool. Capabilities unchanged;
`tools/lookup.py.txt` untouched. Logging starts from this deploy, so everything earlier shows as
"Before history".

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
- **Header:** like the other tabs, History has its own figures: things recorded this month and
  receipt spend this year.
- **Smoke checks:** "unsaved pantry changes", "history log" and "history tab" in
  `tests/smoke.py`. Screenshots `7-savebar`, `8-history*`.

### 5. List amounts, list review on receipts, receipts correcting hand-added stock (done, 27 November 2026)

- List entries have a number and a unit (`qty`, `unit`) instead of free text; the add and
  entry sheets have Amount, Unit and Note. The entry sheet shows when it was added.
- Receipts no longer silently clear the list. The receipt (and product photo) review has a
  "Shopping list" section that suggests which entries were bought; the user confirms.
- Stock added without a receipt is marked `provisional`; a later receipt replaces it with
  what was really bought. Details in `docs/data-model.md`.

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

### 5. Header the same on every tab, and a real connection status (done, 27 November 2026)

Raised by the owner from screenshots; [rsorero/rubadubdub#3](https://github.com/rsorero/rubadubdub/pull/3),
first deployed as artifact version 15; the History deploy (item 3) carries it forward.

- **Same height on every tab.** The header jumped because Add and Meals hid the figures
  line. The owner preferred keeping the space over removing it, so each tab now has its own
  figures (`render()`): Add shows receipts kept and spent this month (receipt `total`s
  dated this month), Meals shows uncooked meals across all plans and the number of
  favourites. `.stats` has a `min-height` on wide screens. On phones the line never wraps:
  it scrolls sideways with a faded right edge.
- **No orange ring on a tapped tab.** It was the `:focus-visible` outline staying on the
  tab link after a click. Tab links now blur after a pointer click (`e.detail` is 0 for
  keyboard), and their keyboard ring is green (`--leaf2`) instead of tomato.
- **Connection status** (`liveState()`). It used to say "Shared live" whenever the db
  capability existed at startup and never changed. Now:
  - *Connecting…* (hollow dot) until every collection has had a snapshot from the server;
  - *Offline* (red) when `navigator.onLine` is false, when a loaded collection's latest
    snapshot is `fromCache` (`stale`), or after a listener error (`lost`; the banner still
    says to reopen the page);
  - *View only* (grey) when `RO`;
  - *Shared live* (yellow) otherwise; nothing when there's no db (the local-only banner
    covers that).

  On phones it comes first in the figures line so it isn't scrolled out of view.
- **Tests:** the smoke test checks the header height on every tab (five since History) at 1000
  and 390 px
  (screenshots `0-header-<width>-<tab>.png`), the Add and Meals figures, and every
  connection state, using a second page with a fake db whose snapshots the test sends by
  hand (`__send(fromCache)`).

### 6. Meals: ranked options, collapsible cards, button-style Recipe (done, deployed 27 November 2026)

Raised by the owner from phone screenshots; [rsorero/rubadubdub#7](https://github.com/rsorero/rubadubdub/pull/7),
first live in artifact version 21, carried forward in 22.

- **Three options for one meal.** "One meal" asks Claude for `NOPT` (3) alternatives, ranked
  best first by expiring items, little to buy, nutrition focus and time. Each meal has `rank`
  and `why` (one line on the ranking); the plan has `opts: true`. The top one is labelled
  "Best match". Details in `docs/data-model.md`.
  - An options plan counts as one meal to cook in the header until one option is cooked
    (`toCookIn()`).
  - Tweaking an option never adjusts the others, and keeps its rank and reason.
  - Several-days plans are unchanged: one meal per slot.
- **Collapsible meal cards.** Every meal (both modes) is `article.mcard > details.mc`. The
  summary shows the tag, time, servings, star, title and one line of facts (rank, kcal,
  "N to buy" or "All in your kitchen"). A newly shown plan opens its first meal still to cook
  (`#pout` `data-pid` marks the plan last opened). After that `keepOpen()` keeps the user's
  choice. The star sits in the summary, so the `#pout` click handler calls `preventDefault()`
  for buttons there.
- **Recipe and Nutrition details** are `details.m` rows with a border and a chevron, contents
  in `.mb`. Recipe comes first. `details.m` is also used by "Paste receipt text instead" on
  the Add tab, which picks up the same look.
- **Spacing:** `#pout` gets a gap and a divider under "Suggest meals". Sections inside a card are
  `.msec` with a hairline, and the action row has its own divider.
- **Smoke checks:** the "meal options" block (fixture `tests/fixtures/options.json`, chosen
  when the prompt contains "different options for one"). Screenshot `5a-options.png`. The
  multi-day header check expects 4: 3 meals plus 1 for the options plan.

## Barcode then photo (fixed 27 November 2026, artifact version 19)

- A product photo of something added the same day (for example scanned by barcode a minute earlier)
  now offers "Replaces the 1 pc added with its barcode", ticked by default, so it isn't counted twice
  (`provOf()` allows photos when the provisional stock is from the same day).
- An item still called "New product 1234" (`autoName`) takes the name read from the pack or receipt
  when a line matches it, and its lookup is asked again under that name.
- The item sheet says when a pending lookup was asked and that runs happen a few times a day.
- `tools/lookup.py ean` no longer reports "not found" when Open Food Facts can't be reached: it
  prints `error` (with `notFound`, so the older task prompt doesn't save it) and exits 2.
  The task prompt leaves such requests pending.

## More lookup sources and a camera tray (27 November 2026, artifact version 22)

- `lookup.py ean` tries Open Food Facts, then Open Products Facts, Open Beauty Facts, Open Pet
  Food Facts and UPCitemdb. A product found in the products or beauty database gets `food: false`.
  Then the task can web-search the barcode (`match: "web"`: name, brand and size only).
- Product photos open a tray sheet (`openTray()`): "Take a photo" (camera input, one shot each)
  and "From gallery" (several), up to 6, then "Read N photos".
- Merged branch `claude/recipe-ui-spacing-collapsible-r05n9w` (meal options), which another
  session had deployed as version 21.
- Fixed in version 23: in the Claude phone app, tapping a file input with `capture="environment"`
  (Barcode, Scan barcode, Scan for expiry, Take a photo) did nothing. No input uses `capture` now;
  the phone asks camera or files instead. Smoke check "no file input forces the camera".
- Version 24, live camera: the Claude app's file picker offers no camera at all, so file buttons
  marked `data-cam` ("barcode" or "photo") open an in-page camera (`camOpen()`, `getUserMedia`).
  Barcode mode reads codes from the video (BarcodeDetector, else ZXing on a centre strip);
  photo mode has Take photo and hands the picture to the input as if chosen. If the camera is
  refused or missing it says so, offers the file picker, and `pm-nocam` skips it on that device
  for a week. Not yet confirmed inside the Claude phone app. Smoke checks "live camera".

## Look up now (added 27 November 2026, artifact version 20)

- Owner's question: why do lookups take hours? The page can't reach other websites (CSP), and
  Claude inside the page can't browse, so lookups wait for the scheduled task's next run.
- A pending lookup's item sheet now has **Look up now** (`lookNow()`). Through the Claude Code
  connector (`mcp` capability, tools `list_triggers` and `fire_trigger`) it finds the scheduled task
  by its name, "Rubadubdub product lookups", and starts it straight away. The task's id is never in
  the code. `settings/lookups.fired` records the start, so every device shows "Looking this up
  online now" for 15 minutes and hides the button.
- The button shows only when `use('mcp')` resolves. The first press asks the owner to allow the
  connector. Each error code gets its own message (`LOOK_ERR`). Not yet confirmed to work inside
  the phone app.
- If the task is renamed, update `LOOK_TASK`. Smoke check: "look up now".

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
  Capabilities are the set listed in `CLAUDE.md` (they include `mcp` since version 20). Leave
  `capabilities` out of the publish call so they carry forward.
- **Previews.** To let the owner try a change first, publish a separate private copy as a new
  artifact, with no capabilities, and an inline script that seeds `localStorage` `pm-local`
  from `tests/fixtures/state.json`. Don't put "Rubadubdub" in its title, so the deploy search
  still finds one match. Delete it once the owner approves.

- **Parallel sessions.** Several sessions may work on the app at once, and the live page can
  come from a branch that isn't merged yet. Before deploying, compare the live page with
  `main` and with the open `ccr-*`/`claude/*` branches (`Artifact` `read`, then `diff` against
  `git show <branch>:app/index.html`; only the wrapper skeleton lines should differ). If
  live is another branch, merge it with yours in a throwaway worktree (`git worktree add
  --detach`), run the checks there and publish that file, keeping your PR branch clean.
  Then tell the other session with `send_message` (`list_sessions` finds it) what is live,
  so its next deploy starts from a tip that has your work.

- **Repo settings** (visibility, rename, description) can't be changed through the shell's
  GitHub proxy (403). Use the built-in browser, where the owner is signed in.
- **Downloading and running binaries** such as gitleaks is blocked here. The GitHub
  workflow runs gitleaks on every push instead; check the Actions tab.
- **Creating or editing scheduled tasks** can be stopped by a safety check. Explain what the
  change does and let the owner approve it.
- **`publish_files` won't serve `.py`,** hence `tools/lookup.py` → `tools/lookup.py.txt`.
- **The Artifact publish tool refuses an update until the live version has been viewed.**
  The first publish comes back with a diff of the live page against yours. If every line
  in it is your own change (compare the live file with `git show <base>:app/index.html`),
  publish the same file again, unchanged, and it goes through.
- **The smoke test** serves `app/` from a local HTTP server (so `/_blob/` photo URLs can be
  answered) with a simulated Claude, asset store and localStorage. Install the Python
  `playwright` package at the same version as the preinstalled browser (in the cloud
  sessions that is `pip install playwright==1.63.0`; check with
  `node -e "console.log(require('playwright/package.json').version)"`).
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
