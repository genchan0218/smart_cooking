# Smart Grocery Shopping: dashboard design (draft, 2026-11-01)

Goal: a phone-friendly dashboard on the VPS that shows what is in the house, how old it is, and which dishes
(Western + Japanese) can be made from it, with the soonest-to-go-off items pushed first.

## Views

| View | What it shows |
|---|---|
| **Tonight** (home) | Ranked dish suggestions. Tabs: *Cook now* (all ingredients on hand), *Missing 1-2*, *Use it up*. Each card: photo-less title, cuisine, time, which on-hand items it uses, what is missing, link to the source recipe. A "Cooked it" button subtracts quantities. |
| **Inventory** | Table grouped by location (kitchen fridge, kitchen freezer, garage freezer, cabinet). Columns: item, qty, added, age, best-by, status. Filters by location and category. Inline edit of qty and dates. |
| **Use soon** | Items sorted by days to best-by (or by age vs. default shelf life when no date). Colour bands: fresh / use this week / past best-by. |
| **Shopping list** | Built from the missing ingredients of dishes you pin, merged by ingredient, plus manually added items. Check-off adds the item to inventory. |
| **Add items** | Upload a photo (or several). Claude vision proposes name, category, quantity, best-by date read from the pack. You confirm or fix, pick a location. |

## Data model (SQLite)

- `items(id, name, canonical, category, location, qty, added_on, best_by, opened_on, source_photo, note)`
- `recipes(id, name, cuisine, category, url, total_time, source)` and
  `recipe_ingredients(recipe_id, raw_text, canonical, form, optional)`
- `canonical_ingredients(name, aliases, kind)` shared vocabulary; `staples(name)` always-assumed items
- `shelf_life(category, location, days)` defaults used when there is no printed date
- `events(ts, item_id, action, delta)` audit log for added / cooked / discarded

Today's files map straight in: `data/inventory.json` -> items, `data/recipes.json` -> recipes,
`data/photo_locations.json` -> location, `data/recipe_matches.json` is the first-cut matcher output.

## Matching and ranking

1. Normalise every recipe line to a canonical ingredient plus a *form* (raw, cooked, breaded, frozen, dried).
   Today's regex vocabulary treats "chicken" as satisfied by breaded frozen chunks, which is wrong for teriyaki.
2. Coverage = matched required ingredients / required ingredients (staples and optional lines excluded).
3. Score = coverage
   + bonus per matched ingredient that is near or past best-by
   - penalty per missing ingredient (larger for the main protein or noodle).
4. Past best-by is a soft warning ("past best-by 2026-10, dried, probably fine"), not "expired". Only fresh
   items (meat, fish, dairy, produce) get a hard "toss" status past their date.

## Age tracking

- Photo timestamps cannot be used (all taken on one day), so age comes from `added_on` (intake date) and the
  printed 賞味期限 / best-by date when readable.
- With no printed date, `shelf_life` supplies a default by category and location (e.g. cut cabbage in fridge ~7 days,
  frozen fish ~3 months, dried noodles ~12 months). You can override per item.

## Hosting on the VPS

- **Stack:** FastAPI + SQLite, server-rendered pages (Jinja + HTMX) so it works well on a phone without a JS build.
  Alternative if you prefer the stack from your other dashboards: Shiny.
- **Run:** one systemd service behind Caddy (automatic HTTPS), single-user login (basic auth or a magic-link),
  nightly SQLite backup to a second location.
- **Deploy:** hand to the `vps-liaison` agent when ready (staging, service, schedule, path fixes).
- **Secrets:** the Google service-account key and any Claude API key stay in environment files on the server,
  never in the repo or the web root. The app itself needs no Drive access once photos are ingested;
  only an optional "sync Drive folder" job does.
- **Photo intake cost:** vision calls only happen when you upload new items, so cost is small.

## Build order

1. Ingredient normaliser and vocabulary; staples list; shelf-life table.
2. SQLite schema + importer for the current JSON files.
3. API + Tonight and Inventory views (read-only).
4. Editing, "Cooked it", Use soon, Shopping list.
5. Photo intake with Claude vision and date reading.
6. VPS deploy, HTTPS, auth, backups.

## Household (answered 2026-11-01)

- 2 adults, a 2-year-old and a 1-month-old. The newborn eats no solids, so servings = 2 adults + 1 toddler,
  about 2.5 adult portions. Scale "is one pack enough for dinner?" on that.
- Always on hand (treated as staples, never "missing"): eggs, rice, onions, scallions, oil, butter, flour,
  plus salt, sugar, pepper, water, panko and starch.
- A newborn at home means tired cooks, so every suggestion shows total time and the Tonight view has a
  "Quick (30 min or less)" filter, plus a "freezer-only, minimal effort" filter.
- Toddler flags on each dish, derived from ingredients: *spicy* (Shin Ramyun, Tabasco, kung pao, chili oil),
  *very salty* (soy-heavy sauces, instant ramen broth, furikake), *choking risk* (whole nuts, whole grapes,
  large hard pieces), *raw fish*. Flags are prompts for you to judge, not medical advice.

## Open questions

- Should photo intake call the Claude API from the server (needs a key there), or stay a manual step here?
- Domain or sub-path on the VPS, and who else should be able to log in?
