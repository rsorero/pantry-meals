# Scheduled task: product lookups

The app can't reach other websites, so product details (barcode, ingredients, allergens,
nutrition) are fetched by a scheduled Claude task. The page queues requests in the
`lookups` collection; each run looks them up with `tools/lookup.py` and writes the results
to `info`.

Create it once per copy of the app (see `docs/setup.md`):

- **Name:** Rubadubdub product lookups
- **Schedule:** a few times a day in your time zone, on an odd minute, for example
  `CRON_TZ=<your IANA time zone> 39 7,9,11,13,17,19,21 * * *`
- **Notifications:** off
- Keep this exact name: the app's "Look up now" button finds the task by it.
- **Prompt:** the text below, with `{{ARTIFACT_SLUG}}` and `{{ARTIFACT_URL}}` replaced by
  your artifact's slug and claude.ai URL (from `list_artifacts` or `get_artifact`)
- **Network:** the run's shell must reach `tienda.mercadona.es` and
  `world.openfoodfacts.org`. If your environment limits network access, allow those two
  hosts.

## Prompt

```
Process pending online product lookups for the "Rubadubdub" app. It is a claude.ai artifact: slug {{ARTIFACT_SLUG}} ({{ARTIFACT_URL}}). Nobody is watching: never ask questions, and end quietly when there is nothing to do.

TOOLS
Use the claude-artifacts MCP tools db_list, db_get, db_write and read_file (load them with one ToolSearch if they are deferred). Use the shell to run Python. The shell can reach tienda.mercadona.es and world.openfoodfacts.org.

STEPS
1. db_list collection "lookups" (limit 200). Each document looks like {itemId, name, aliases, barcode, store, status, requested}. Keep only status "pending". If there are none, reply "No pending lookups." and stop.
2. Get the lookup script: read_file path "tools/lookup.py.txt" (read every line, paging with offset/limit if needed) and save the exact text as lookup.py in the working directory. It needs only the Python standard library. Commands:
   python3 lookup.py ean <barcode>      -> info record from Open Food Facts by barcode ({"error": ...} and exit code 2 if the site couldn't be reached)
   python3 lookup.py catalog            -> caches Mercadona's online catalogue to catalog.json (takes about 2 minutes; run it at most once per run, and only if a request needs a name search)
   python3 lookup.py search <words>     -> top catalogue candidates for Spanish search words
   python3 lookup.py mercadona <id>     -> info record from a Mercadona product id, plus Open Food Facts nutrition by its barcode
3. For each pending request (at most 25 per run, oldest "requested" first):
   a. db_get "items/<itemId>". If the item no longer exists, delete the request (step e) and move on.
   b. If the request has a barcode: run `ean <barcode>`. If the output has "error", Open Food Facts couldn't be reached: leave the request pending (no write) and move on; it is retried next run. If the record does not have notFound, use it (match is "barcode").
   c. Otherwise, or if the barcode wasn't found: translate the item name and its receipt labels (aliases; often in the local language) into Spanish product words and run `search` with two or three phrasings. Pick a product ONLY if it is clearly the same kind of product: same type and variant or flavour, and same brand if a brand is named. Pack size may differ. Then run `mercadona <id>` and set the record's "match" to "likely" when it is the same product and "similar" when it is the closest match but may differ. For fresh produce, meat, fish and bakery a generic product is fine as "similar". Never pick a different kind of product. If a barcode was given but only a name match was found, keep match "likely"/"similar", not "barcode".
   d. If you have a record: remove null fields, add "itemId", and write it with db_write op "set" to path "info/<itemId>". If that info document already exists, db_get it first and pass ifVersion. Then, if the item has autoName true and the record has fullName, db_write op "merge" on "items/<itemId>" with the item's ifVersion and data {"name": <short natural English product name, e.g. "Tomato sauce (artisan recipe)">, "autoName": false}. Change nothing else on the item.
   e. On success, db_write op "delete" on "lookups/<itemId>" with ifVersion from step 1.
   f. If nothing usable was found, db_write op "merge" on "lookups/<itemId>" with ifVersion and data {"status":"failed","note":<one short sentence for the person, e.g. "Not found on Open Food Facts or in Mercadona’s online shop. Try scanning the barcode.">,"checked":<today YYYY-MM-DD>}.
4. db_write rules: at most 50 ops per call, one call at a time, wait 2 seconds between calls, and every op on an existing document needs its current ifVersion. On a version conflict, re-read that document and retry once; if it still fails, skip it.
5. Product facts (ingredients, allergens, nutrition, Nutri-Score) must come only from the script's output. Never invent or "fill in" values. Do not modify any other documents or collections.
6. Final response: one short line, e.g. "Looked up 3 items: 2 found, 1 not found."
```

## Notes

- Name searches use Mercadona's Spanish online shop (`tienda.mercadona.es`). Shops in other
  countries often carry the same or similar products, but labels and pack sizes can differ,
  hence the `match` levels. Barcode lookups use Open Food Facts and work for products from
  any shop or country.
- Open Food Facts asks clients to send a descriptive User-Agent; `lookup.py` does.
