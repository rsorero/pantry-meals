# Working on Rubadubdub

Starting a new session? Read `docs/handoff.md` for where things stand and what is open.

## Deploying

The app runs as a claude.ai artifact owned by whoever deploys it. This repo holds no
artifact IDs, keys or personal data; keep it that way (see "Keeping secrets out" below).

1. Find your copy: `list_artifacts` with query `Rubadubdub`, and take the entry marked
   `mine`. If there is none, this is a first-time setup: follow `docs/setup.md` instead.
   If there are several, ask which one.
2. `get_artifact` (that slug) for the live `version` and its `read` value.
3. `publish_files` with `mode: "patch"`, `base_version` = that version, and pass
   `shared_live` if `read` is `users`, `org` or `public`:
   - `app/index.html` → served as `index.html`
   - `tools/lookup.py` → served as `tools/lookup.py.txt` (the scheduled lookup task reads it
     from there; `.py` isn't a served type)
4. Capabilities are declared on the artifact, not in the file: `{db:{}, user:{}, sample:{images:true}}`.
   If you add one, call `declare_capabilities` *before* publishing code that uses it.

Data lives in the artifact's database and survives republishing. Never wipe or reseed it;
fix data with `db_write` using `merge` and `ifVersion`.

## Before publishing

- `python3 tests/smoke.py` must pass. Add a check for any new flow.
- `python3 tools/check_secrets.py` must pass.
- Syntax check: extract the last `<script>` and run `node --check`.
- Look at the screenshots in `tests/out/`. Most use is on a phone, so check 390 px wide.

## Conventions in app/index.html

- One file, no build, no framework. State is in `S[collection][id]`, written with
  `put(col, obj)` / `del(col, id)`, which saves to the db (or localStorage when db is
  unavailable) and re-renders.
- Anything from the db, Claude or the web is text: build HTML only through `esc()`. Links
  must start with `https://`.
- Remote fetches are blocked by the page's CSP. Internet data goes through the
  `lookups` → scheduled task → `info` route.
- Claude calls go through `SAMPLE(prompt, {cache:false, ...})`, ask for JSON only, and are
  parsed with `parseJSON`. Validate every field: ids must exist in `S.items`, numbers via
  `num()`, enums checked.
- Product facts (ingredients, allergens, nutrition) come only from the lookup sources. Meal
  nutrition prefers product data and labels Claude's estimates as estimates.
- Copy is plain English, sentence case, no emoji.

## Keeping secrets out

This repo is public. Never commit API keys, tokens, passwords, `.env` files, artifact or
scheduled-task IDs, receipts, real pantry data or anyone's address. Test data in
`tests/fixtures/` uses placeholder addresses. The user's location is an app setting
(`settings/home.where`, set on the Meals tab), never code. `tools/check_secrets.py` and the
GitHub workflow in `.github/workflows/secrets.yml` scan for this; to add your own words to
the local check (your street, your name), list them in `.private-words` (git-ignored).

## Related

- Scheduled task "Rubadubdub product lookups" (claude.ai scheduled tasks) runs the prompt in
  `docs/lookup-task.md`; find yours with `list_triggers`.
