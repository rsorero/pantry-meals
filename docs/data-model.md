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
`{name, itemId|null, amount, note, done, t, store?}`

- `store`: a shop chosen for this entry (from the "Add to list" form or the entry's sheet).
  Optional; entries without it, including all older ones, follow the item. An entry's shop is
  its own `store`, else where the item was last bought (`stores[0].name`), else "Anywhere".
  The list is grouped and filtered by that shop. When a ticked entry with its own `store` is
  put in the pantry, that shop is recorded on the item.

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
`{title, multi, t, kit[], focus, note, useM, meals[]}`. Each meal:
`{day, slot, title, summary, time_min, servings, equipment[], uses[{id,name,amount,qty_used,grams,n[8]}],
buy[{name,amount,grams,n[8]}], steps[], cooked, change, favId?}`.
`n` = Claude's estimate per 100 g: [kcal, protein, carbs, sugars, fat, sat, fibre, salt].
The app keeps the 15 newest plans.

## favs/{id}
A saved meal (same fields as a meal, without day) plus `saved, cookedCount, lastCooked`.

## settings/kitchen
`{custom: string[]}`: appliances the household added.

## settings/home
`{where: string}`: where the household lives and shops, in their own words (max 80
characters). Set on the Meals tab; added to the meal, tweak, receipt and photo prompts.
