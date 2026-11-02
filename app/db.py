"""SQLite storage: schema, first-run import of the JSON files in ../data, shelf-life defaults."""
import json, os, re, sqlite3
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
DB_PATH = Path(os.environ.get("GROCERY_DB", ROOT / "app" / "grocery.db"))

LOCATIONS = [("kitchen_fridge", "Kitchen fridge"), ("kitchen_freezer", "Kitchen freezer"),
             ("garage_freezer", "Garage freezer"), ("cabinet", "Cabinet")]
LOC_LABEL = dict(LOCATIONS)
CATEGORIES = ["produce", "dairy", "refrigerated meal", "frozen meal", "frozen meat", "frozen seafood",
              "frozen dumplings", "frozen bread", "frozen vegetable", "noodles", "pasta", "pasta sauce", "sauce",
              "seasoning", "stock", "dashi", "dried goods", "furikake", "soup mix", "sauce mix", "roux",
              "rice mix", "baking", "snack", "dessert", "other"]

# default shelf life in days when no printed date is known (fridge/cabinet); freezers use FREEZER_DAYS
SHELF_DAYS = {"produce": 7, "dairy": 10, "refrigerated meal": 5, "stock": 7, "sauce": 180, "seasoning": 180,
              "pasta sauce": 365, "dashi": 365, "dried goods": 365, "furikake": 365, "soup mix": 365,
              "sauce mix": 365, "roux": 365, "rice mix": 365, "baking": 365, "snack": 180, "noodles": 270,
              "pasta": 540, "other": 90}
FREEZER_DAYS = 120
# categories that "Cooked it" counts down by one unit (sauces, seasonings and stocks are not used up per meal)
CONSUMABLE = {"produce", "dairy", "refrigerated meal", "frozen meal", "frozen meat", "frozen seafood",
              "frozen dumplings", "frozen bread", "frozen vegetable", "noodles", "pasta", "roux", "soup mix",
              "sauce mix", "rice mix", "dessert"}

SCHEMA = """
CREATE TABLE IF NOT EXISTS items(
  id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, category TEXT NOT NULL, location TEXT NOT NULL,
  qty INTEGER NOT NULL DEFAULT 1, added_on TEXT NOT NULL, best_by TEXT, note TEXT DEFAULT '', photo TEXT);
CREATE TABLE IF NOT EXISTS recipes(
  id INTEGER PRIMARY KEY, name TEXT, cuisine TEXT, category TEXT, url TEXT, minutes INTEGER, yield TEXT,
  ingredients TEXT);
CREATE TABLE IF NOT EXISTS shopping(id INTEGER PRIMARY KEY AUTOINCREMENT, text TEXT NOT NULL, recipe TEXT,
  done INTEGER DEFAULT 0);
CREATE TABLE IF NOT EXISTS events(id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT DEFAULT CURRENT_TIMESTAMP,
  item_id INTEGER, action TEXT, delta INTEGER, note TEXT);
"""


def connect():
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    return con


def minutes_from_iso(s):
    if not s:
        return None
    m = re.fullmatch(r"P(?:T)?(?:(\d+)D)?(?:(\d+)H)?(?:(\d+)M)?", str(s))
    if not m:
        return None
    d, h, mi = (int(x or 0) for x in m.groups())
    total = d * 1440 + h * 60 + mi
    return total or None


def default_best_by(category, location, added_on):
    days = FREEZER_DAYS if location.endswith("freezer") else SHELF_DAYS.get(category, 90)
    return (date.fromisoformat(added_on) + timedelta(days=days)).isoformat()


def init():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    con = connect()
    con.executescript(SCHEMA)
    if not con.execute("SELECT 1 FROM items LIMIT 1").fetchone() and (DATA / "inventory.json").exists():
        for it in json.load(open(DATA / "inventory.json", encoding="utf-8")):
            added = "2026-11-01"
            con.execute("INSERT INTO items(name,category,location,qty,added_on,best_by,note,photo) VALUES(?,?,?,?,?,?,?,?)",
                        (it["name"], it["category"], it["location"], it["quantity"], added,
                         _norm_date(it.get("best_by")), it.get("note", ""), (it["photos"] or [None])[0]))
    if not con.execute("SELECT 1 FROM recipes LIMIT 1").fetchone() and (DATA / "recipes.json").exists():
        for r in json.load(open(DATA / "recipes.json", encoding="utf-8")):
            con.execute("INSERT INTO recipes VALUES(?,?,?,?,?,?,?,?)",
                        (r["id"], r["name"], r["cuisine"], ",".join(c for c in r["category"] if c), r["url"],
                         minutes_from_iso(r.get("total_time")), str(r.get("yield") or ""),
                         json.dumps(r["ingredients"], ensure_ascii=False)))
    con.commit()
    con.close()


def _norm_date(s):
    """'2026-10' -> '2026-10-31' (end of month, a best-by with no day means that whole month)."""
    if not s:
        return None
    if re.fullmatch(r"\d{4}-\d{2}", s):
        y, m = int(s[:4]), int(s[5:])
        nxt = date(y + (m == 12), (m % 12) + 1, 1)
        return (nxt - timedelta(days=1)).isoformat()
    return s


def status(best_by, today=None):
    """-> (label, css class, days left)"""
    today = today or date.today()
    if not best_by:
        return ("no date", "none", None)
    left = (date.fromisoformat(best_by) - today).days
    if left < 0:
        return (f"past best-by {-left}d", "past", left)
    if left <= 7:
        return (f"{left}d left", "soon", left)
    return (f"{left}d left", "ok", left)
