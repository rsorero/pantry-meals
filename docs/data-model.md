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
`{name, itemId|null, amount, note, done, t}`

## receipts/{id}
`{store, addr, date, total, lines[{raw,name,qty,unit,total}], t}`

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
