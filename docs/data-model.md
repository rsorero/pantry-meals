# Data model

All collections live in the artifact's `db`, one document per entity, with `id` repeated in
the body. Default access rules apply: everyone admitted reads, Contributors and up write.

## items/{id}
| field | type | notes |
|---|---|---|
| name | string | display name (English) |
| aliases | string[] | receipt labels seen for this item, used to match receipts |
| qty | number | amount on hand, in `unit` |
| unit | `pc` `pack` `kg` `g` `L` `ml` | |
| loc | `produce` `fridge` `freezer` `pantry` `drinks` `household` | |
| food | bool | false = not used in meal plans |
| low | number | low-stock alert threshold (0 = only when empty) |
| price | number | last unit price paid |
| stores | {name, addr, date, price}[] | most recent first, max 6 |
| bought | YYYY-MM-DD | last purchase |
| barcode | string? | scanned EAN |
| autoName | bool? | placeholder name; the lookup task renames it |
| added | YYYY-MM-DD? | when the item was first added (items made before Nov 2026 don't have it) |
| receipt | {id, line, raw}? | the receipt it was last bought on: `receipts/{id}`, the line index, and the line as printed. Null for items not added from a receipt |
| expirationDate | `YYYY-MM-DD` \| `YYYY-MM` \| null | expiry or best-before date; `YYYY-MM` when only month and year are printed (treated as the end of that month) |
| expirationSource | `ocr` \| `manual` \| null | `ocr`: read from a photo and not yet checked, so the app asks the user to check it. `manual`: typed, or a reading the user confirmed |
| expirationRaw | string? | the date as printed on the pack, e.g. `EXP 03/11/27` |
| expirationAlt | string[]? | other possible readings of an ambiguous printed date (dd/mm vs mm/dd, two-digit years) |
| provisional | {qty, unit, date, how, made}? | stock added without a receipt: by hand (`how: "hand"`), by barcode (`"barcode"`), from the shopping list (`"list"`) or from product photos (`"photo"`). `qty` is the total added that way, in the item's unit; `made` is true when that add created the item. A later receipt line for the item can replace it (see below), which removes the field |

All of these are optional, so older items load unchanged; no migration is needed. A date
read from a photo never replaces one the user typed, except when the user scans that item
on purpose ("Scan for expiry") or changes the date in the review.

## info/{itemId}
Product data from the internet (written by the lookup task, plus `ingredientsEn` from the
in-app translation). Fields: `barcode, fullName, brand, origin, size, packaging,
ingredients, ingredientsEn, allergensText, allergens[], traces[], labels[],
nutrition{kcal,fat,sat,carbs,sugars,fiber,protein,salt} (per 100 g/ml), nutriscore, nova,
sources[{name,url}], match ("barcode" | "likely" | "similar"), updated, itemId`.

## lookups/{itemId}
Lookup requests: `{itemId, name, aliases[], barcode, store, status: "pending"|"failed",
note?, requested (ms), checked?}`. Deleted when done.

## shopping/{id}
`{name, itemId|null, qty?, unit, amount?, note, done, t, doneAt?, store?}`

- `qty` and `unit` (one of the item units): how much to buy. `qty` is missing when no amount
  was given. Older entries have a free-text `amount` instead; the app reads it as a number and
  unit when it can (`sQty()`), and replaces it with `qty`/`unit` when the entry is saved.
  Amounts from meal plans are read the same way, or go into the note.
- `t`: when the entry was added (ms). `doneAt`: when it was ticked.
- The estimate converts the amount to the item's unit (g/kg, ml/L) before multiplying by its
  last price. "Put ticked in pantry" adds the entry's amount, converted the same way.

- `store`: the shop the user wants this bought at, chosen in the "Add to list" form or the
  entry's sheet. Optional: without it (including all older entries) the entry is for
  **anywhere**, even if the item was last bought somewhere. The item's last shop and price
  are shown on the entry as information and used for the estimate, but never place it.
- The list is grouped and filtered by `store`. A shop filter also shows the anywhere entries.
- The same item can be listed once per shop and once for anywhere: these are separate
  entries. Adding merges only into an open entry for the same shop (or both anywhere).
- The estimate for an entry with a `store` uses the item's last price at that shop when
  known (`stores[]`), else its last price anywhere.
- Adding a receipt or product photos shows the list in the review. Entries added before the
  end of the purchase day (open or ticked) are matched to lines: by Claude (`list` on each
  line), by the line's pantry item, or by name. Matched entries are ticked to be crossed off,
  except entries for another shop. The user can untick them, or pick the line an entry was
  bought as. Only the entries left ticked are deleted when the purchase is added. When a
  ticked entry with a `store` is put in the pantry, that shop is recorded on the item.

## Receipts and provisional stock
When a receipt line goes to an item with `provisional` stock, the review offers "Replaces the
… added by hand". It is ticked when the provisional add is within 7 days of the receipt date.
If kept ticked, the provisional amount is taken back and the line's amount put in, so what was
used since stays used. If the item was created by that add (`made`), it also takes the line's
unit, name, place and food flag, and is looked up online again under its new name. Without
it, the line is added on top as usual. Line amounts are converted to the item's unit.

## receipts/{id}
`{store, addr, date, total, lines[{raw,name,qty,unit,total,itemId,skip?,y?}], image?, text?, t}`

- `lines[].itemId`: the pantry item the line was added to, or null (for unticked lines, which
  also have `skip: true`). Receipts added before Nov 2026 have no `itemId`; the app matches
  their lines to items by receipt label (`aliases`) or name when showing them.
- `lines[].y`: roughly where the line sits on the photo, 0 (top) to 1 (bottom), so the
  viewer can scroll the photo to it. Claude's estimate, used only for scrolling.
- `image`: asset id of the receipt photo (one JPEG, at most 1200 px wide), shown from
  `/_blob/{image}`. Stored with the `assets` capability, which only Editors and the owner get,
  so a receipt added by anyone else has no photo. Missing on older receipts.
- `text`: the pasted receipt text, for receipts read from text (max 8000 characters).

Deleting a receipt record leaves its photo in the asset store, so Undo keeps working.

## plans/{id}
`{title, multi, opts?, t, kit[], focus, note, useM, meals[]}`. Each meal:
`{day, slot, title, summary, time_min, servings, equipment[], uses[{id,name,amount,qty_used,grams,n[8]}],
buy[{name,amount,grams,n[8]}], steps[], cooked, change, favId?, rank?, why?}`.
`opts: true` marks a one-meal request: its meals are alternatives (three, ranked best first by
Claude, `rank` 1 = best, `why` = one line on the ranking), not a plan. They count as one meal to
cook in the header until one is cooked, and tweaking one never changes the others.
`n` = Claude's estimate per 100 g: [kcal, protein, carbs, sugars, fat, sat, fibre, salt].
The app keeps the 15 newest plans.

## favs/{id}
A saved meal (same fields as a meal, without day) plus `saved, cookedCount, lastCooked`.

## history/{id}
What happened, one small document per event, written from the day the History tab shipped
(27 November 2026). The other collections only hold what's there now.

`{id, t, kind, name, itemId?, unit?, qty?, from?, to?, store?, receiptId?, planId?, k?, favId?, listId?, total?, note?, expired?}`

- `t`: time in ms. `name`: the item, shop, plan or meal name at the time (max 80 characters;
  `note` max 160). Empty fields are left out, so most events are under 200 bytes.
- `kind`, by group:
  - **pantry:** `amount` (`from` → `to`, saved with the Pantry's Save button), `used` (saved at 0;
    `expired: 1` when the item's expiry date had passed), `edit` (`note` says what changed, in
    words), `delete`;
  - **adding:** `receipt` (one per receipt: `receiptId`, `total`, `qty` = items added), `photo`,
    `barcode`, `hand` (`qty` added, `store` when chosen);
  - **list:** `listed`, `ticked` (unticking removes it), `removed`, `cleared`, `stocked`
    (`listId` = the `shopping/{id}` entry, which may be gone);
  - **meals:** `planned` (`qty` = meals), `cooked` (`planId`, `k` = meal index), `fav`, `unfav`.
- Written only by the app's call sites for these actions (`logEv()`), never by `put`/`del`, so
  lookups, info, settings and housekeeping aren't logged. Undo removes the event it made.
- Kept for 12 months and at most 3000 events (`pruneHist()`, on load and when over the cap).
- Optional: older data has no `history` and loads unchanged.

The History tab also shows the time **before** logging started, rebuilt in the browser and
never written: receipts, plans and their cooked meals (no cook date, so the plan's date),
favourites (`saved`, `lastCooked`, `cookedCount`), items' `added` dates and `stores[]` purchases
not already on a receipt. These are marked "Before history". Spend always comes from
`receipts/`.

## settings/history
`{started: ms}`: when logging started, written with the first event. Rebuilt entries are
only made for dates before it.

## Unsaved pantry changes (this device only)
+, − and Empty on the Pantry rows are held in `localStorage` `pm-pend`
(`{itemId: {from, to}}`) until Save, then written to `items/` with one `history` event each.
Save applies the change to the amount saved now (`to − from`), so a change someone else made
meanwhile isn't lost; Empty always saves 0.

## settings/kitchen
`{custom: string[]}`: appliances the household added.

## settings/home
`{where: string}`: where the household lives and shops, in their own words (max 80
characters). Set on the Meals tab; added to the meal, tweak, receipt and photo prompts.
