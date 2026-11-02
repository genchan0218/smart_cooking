"""Weekly dinner planner. Picks one dish per day:
  - simulates the inventory day by day, so one pack is only counted once across the week
  - re-scores each day with that day's date, so items about to pass best-by get pulled forward
  - avoids repeating a cuisine more than two days in a row, prefers quick dishes (newborn at home)
  - leaves out toddler-unfriendly dishes (spicy, raw fish, choking risk) when kid_safe
Run from the app folder:  python planner.py            (regenerates the plan, stores it in the database)
A weekly systemd timer runs this on the VPS (see deploy/pantry-plan.timer)."""
import json, sys
from datetime import date, timedelta

import db, matcher

SKIP_KINDS = {"Dessert", "Drinks", "Side Dish", "Side", "Snack", "Appetizer", "Condiments", "Salad"}
KID_BLOCK = {"spicy", "raw fish", "choking"}
QUICK_MIN = 30


def _use_up(items, have_lines):
    """Take one unit of each consumable item the dish used; returns the names used."""
    used = []
    names = {n for _, ns in have_lines for n in ns}
    for n in names:
        cand = sorted((i for i in items if i["name"] == n and i["qty"] > 0 and i["category"] in db.CONSUMABLE),
                      key=lambda i: i["best_by"] or "9999")
        if cand:
            cand[0]["qty"] -= 1
            used.append(n)
    return used


def generate(days=7, start=None, kid_safe=True):
    start = start or date.today()
    con = db.connect()
    items = [dict(r) for r in con.execute("SELECT * FROM items WHERE qty>0")]
    con.close()
    chosen, plan, cuisines = set(), [], []
    for d in range(days):
        day = start + timedelta(days=d)
        best, best_s = None, -1e9
        for r in matcher.score_all(day, items):
            if r["id"] in chosen or r["matched"] < 3 or len(r["missing"]) > 2:
                continue
            if set(r["r"]["category"].split(",")) & SKIP_KINDS:
                continue
            if kid_safe and set(r["flags"]) & KID_BLOCK:
                continue
            s = r["score"]
            if r["r"]["minutes"] and r["r"]["minutes"] <= QUICK_MIN:
                s += 1.0
            if cuisines[-2:].count(r["r"]["cuisine"]) == 2:
                s -= 3.0
            if s > best_s:
                best, best_s = r, s
        if not best:
            plan.append({"day": day.isoformat(), "recipe_id": None, "uses": [], "missing": []})
            continue
        chosen.add(best["id"])
        cuisines.append(best["r"]["cuisine"])
        plan.append({"day": day.isoformat(), "recipe_id": best["id"], "uses": _use_up(items, best["have"]),
                     "missing": best["missing"]})
    return plan


def save(plan):
    con = db.connect()
    con.execute("DELETE FROM plan")
    for p in plan:
        con.execute("INSERT INTO plan VALUES(?,?,?,?,?)", (p["day"], p["recipe_id"], json.dumps(p["uses"]),
                    json.dumps(p["missing"]), date.today().isoformat()))
    con.commit()
    con.close()


def load():
    con = db.connect()
    rows = [dict(r) for r in con.execute("SELECT * FROM plan ORDER BY day")]
    con.close()
    out = []
    for r in rows:
        info = matcher.recipe_info(r["recipe_id"]) if r["recipe_id"] else None
        out.append({"day": r["day"], "weekday": date.fromisoformat(r["day"]).strftime("%A"), "info": info,
                    "uses": json.loads(r["uses"] or "[]"), "missing": json.loads(r["missing"] or "[]"),
                    "generated_on": r["generated_on"]})
    return out


if __name__ == "__main__":
    db.init()
    p = generate()
    save(p)
    for x in p:
        info = matcher.recipe_info(x["recipe_id"]) if x["recipe_id"] else None
        print(x["day"], (info["row"]["name"] if info else "(no match)"), "| missing:", len(x["missing"]))
