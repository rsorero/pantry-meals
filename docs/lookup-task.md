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
  `world.openfoodfacts.org`, and should reach `world.openproductsfacts.org`,
  `world.openbeautyfacts.org`, `world.openpetfoodfacts.org` and `api.upcitemdb.com` (skipped
  if blocked). The run also needs web search for barcodes no database knows.

## Prompt

```
Process pending online product lookups for the "Rubadubdub" app. It is a claude.ai artifact: slug {{ARTIFACT_SLUG}} ({{ARTIFACT_URL}}). Nobody is watching: never ask questions, and end quietly when there is nothing to do.

TOOLS
Read and write the app's database with the Artifact database tool (ArtifactData: list, get, update, set, delete, with the artifact URL above) or, if that isn't there, the claude-artifacts MCP tools db_list, db_get, db_write and read_file. Load them with one ToolSearch if they are deferred. Use the shell to run Python, and WebSearch/WebFetch for step 3d.

STEPS
1. List collection "lookups" (limit 200). Each document looks like {itemId, name, aliases, barcode, store, status, requested}. Keep only status "pending". If there are none, reply "No pending lookups." and stop.
2. Get the lookup script: read the artifact's published file "tools/lookup.py.txt" (all of it) and save the exact text as lookup.py in the working directory. It needs only the Python standard library. Commands:
   python3 lookup.py ean <barcode>      -> info record by barcode: Open Food Facts, then Open Products Facts (household goods), Open Beauty Facts, Open Pet Food Facts, then UPCitemdb
   python3 lookup.py catalog            -> caches Mercadona's online catalogue to catalog.json (takes about 2 minutes; run it at most once per run, and only if a request needs a name search)
   python3 lookup.py search <words>     -> top catalogue candidates for Spanish search words
   python3 lookup.py mercadona <id>     -> info record from a Mercadona product id, plus Open Food Facts nutrition by its barcode
3. For each pending request (at most 25 per run, oldest "requested" first):
   a. Get "items/<itemId>". If the item no longer exists, delete the request (step f) and move on.
   b. If the request has a barcode: run `ean <barcode>`. If the output has "error", Open Food Facts couldn't be reached: leave the request pending (no write) and move on. If the record does not have notFound, use it (match is "barcode"). A record with "food": false is a household or beauty product.
   c. Otherwise, or if the barcode wasn't found, and the item has a real name (not autoName) or aliases, and it is food: translate the name and its receipt labels (aliases; often in the local language) into Spanish product words and run `search` with two or three phrasings. Pick a product ONLY if it is clearly the same kind of product: same type and variant or flavour, and same brand if a brand is named. Pack size may differ. Then run `mercadona <id>` and set the record's "match" to "likely" when it is the same product and "similar" when it is the closest match but may differ. For fresh produce, meat, fish and bakery a generic product is fine as "similar". Never pick a different kind of product. If a barcode was given but only a name match was found, keep match "likely"/"similar", not "barcode".
   d. If there is still nothing and the request has a barcode: WebSearch the barcode digits (for example "3596710532223" and "EAN 3596710532223"). Accept a result only if a retailer or product-database page shows that exact barcode with the product. Then build a record with ONLY {"barcode", "fullName", "brand", "size" (if shown), "match": "web", "updated": <today YYYY-MM-DD>, "sources": [{"name": <site name>, "url": <that page, https only>}]}, plus "food": false if it is clearly not food or drink. Take nothing else from the web: no ingredients, allergens or nutrition.
   e. If you have a record: remove null fields and "unreachable", add "itemId", and write it with op "set" to "info/<itemId>" (if that info document already exists, get it first and pass its version). Then update "items/<itemId>" with the item's version: if the item has autoName true and the record has fullName, set {"name": <short natural English product name, e.g. "Tomato sauce (artisan recipe)" or "Liquid laundry detergent">, "autoName": false}; if the record has "food": false and the item's food is true, also set {"food": false}. Change nothing else on the item.
   f. On success, delete "lookups/<itemId>" with the version from step 1.
   g. If nothing usable was found, update "lookups/<itemId>" with its version and data {"status":"failed","note":<one short sentence for the person, e.g. "Not found in Open Food Facts, similar databases or on the web. Take a product photo to give it a name.">,"checked":<today YYYY-MM-DD>}.
4. Writes: one at a time, wait 2 seconds between them, and every write to an existing document needs its current version. On a version conflict, re-read that document and retry once; if it still fails, skip it.
5. Product facts (ingredients, allergens, nutrition, Nutri-Score) must come only from the script's output. Never invent or "fill in" values. Do not modify any other documents or collections.
6. Final response: one short line, e.g. "Looked up 3 items: 2 found, 1 not found."
```

## Notes

- Name searches use Mercadona's Spanish online shop (`tienda.mercadona.es`). Shops in other
  countries often carry the same or similar products, but labels and pack sizes can differ,
  hence the `match` levels. Barcode lookups use Open Food Facts and work for products from
  any shop or country.
- Non-food barcodes (detergent, shampoo) are usually in Open Products Facts or Open Beauty
  Facts. UPCitemdb's free trial allows 100 lookups a day. A web search (`match: "web"`)
  gives only the name, brand and size, never product facts.
- Open Food Facts asks clients to send a descriptive User-Agent; `lookup.py` does.
