# Rubadubdub

Stock, shop, cook.


A household kitchen app built to take the daily thinking out of meals: know what's in the
kitchen, get meals planned from it, and shop for only what's missing.

**Run your own copy:** open a Claude Code session on claude.ai with this repo (fork it
first if you want to keep changes) and say *"Set up Rubadubdub for me, following
docs/setup.md."* Details in [docs/setup.md](docs/setup.md).

## What it does

- **Pantry**: stock by place (fruit & veg, fridge, freezer, cupboard, drinks, household),
  +/−/Empty, low-stock alerts, filter by store, item details.
- **Add**: Claude reads receipt photos or text, product photos and barcodes, then you review
  everything before it's added. You can also add items by hand, with autocomplete.
- **Product details from the internet**: barcode, brand, ingredients, allergens (contains /
  may contain), nutrition per 100 g, Nutri-Score and NOVA, from Mercadona's online shop and
  Open Food Facts. Each record says how it was matched (barcode, same product, or closest).
- **Where it was bought**: store, address, date and price paid, taken from receipts.
- **List**: grouped by store, with where and when each item was last bought, the last
  price, and an estimated total.
- **Meals**: one meal or several days, built from what's in stock (perishables first),
  limited to the kitchen equipment you tick (custom appliances too), with a nutrition focus.
  Shows nutrition per serving and per day, and a simple recipe.
  - **Tweak** a meal: remove, add or resize ingredients, or ask for adjustments (more
    protein, fewer calories…). Changes are kept to a minimum, and in a multi-day plan the
    other uncooked meals are rebalanced only where needed.
  - **Cooked it** takes the ingredients out of the pantry. **Favourites**: star a meal to
    keep it, repeat it with "Cook again", or let new plans reuse it.
- **Shared**: everyone you share it with on claude.ai sees the same data, live.
- **Where you live and shop** (Meals tab) helps with seasonal food, local products and
  reading receipts.

## How it's built

One self-contained page (`app/index.html`, plain HTML/CSS/JS, no build step) hosted as a
claude.ai artifact. It uses the artifact runtime's capabilities:

| capability | used for |
|---|---|
| `db` | shared, live data store (collections listed in `docs/data-model.md`) |
| `sample` (with images) | Claude: reading receipts and photos, meal plans, tweaks, translation, barcode digits as a fallback |
| `user` | whether the viewer may edit |

The page can't reach other websites, so product lookups run outside it. The page queues a
request in `lookups/`; a scheduled Claude task runs `tools/lookup.py` (Mercadona shop API +
Open Food Facts) and writes the results to `info/`. See `docs/lookup-task.md`.

Barcodes are read on the device: the browser's BarcodeDetector, then ZXing
(`@zxing/library@0.21.3` from jsDelivr), then Claude reading the printed digits.

## Repository

```
app/index.html            the whole app
tools/lookup.py           product lookups (stdlib only)
tools/check_secrets.py    scans the repo for keys, tokens and personal data
docs/setup.md             set up your own copy
docs/handoff.md           current state and open items, for the next work session
docs/data-model.md        db collections and fields
docs/lookup-task.md       the scheduled lookup task (prompt template)
tests/smoke.py            headless browser test with a simulated Claude
tests/fixtures/           test state, canned Claude replies, barcode images
CLAUDE.md                 how to deploy and work on this with Claude
```

## Privacy and secrets

The app holds no API keys or passwords. Claude features run through claude.ai on each
viewer's own account, and your pantry data stays in your own artifact's database, never in
this repo. `tools/check_secrets.py` and a GitHub workflow (gitleaks) check every push for
keys, tokens and personal data.

## Running the test

```
pip install playwright && playwright install chromium
python3 tests/smoke.py
python3 tools/check_secrets.py
```

## License

AGPL-3.0. See [LICENSE](LICENSE).

You can use, change and share Rubadubdub, including commercially. If you share a modified
version, or let other people use a modified version over the internet, you must make your
source code available to them under the same license.
