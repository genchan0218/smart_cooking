"""Smart Grocery Shopping dashboard. Run: uvicorn main:app --host 0.0.0.0 --port 8080  (from the app/ folder)
Env: GROCERY_DB (sqlite path), APP_PASSWORD (turns on HTTP basic auth, user 'home'), VISION_BACKEND (ollama|groq|off)."""
import base64, hmac, os, secrets
from datetime import date
from pathlib import Path

from fastapi import FastAPI, File, Form, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

import db, matcher, planner, vision

HERE = Path(__file__).resolve().parent
UPLOADS = Path(os.environ.get("GROCERY_UPLOADS", HERE / "uploads"))
UPLOADS.mkdir(parents=True, exist_ok=True)
db.init()

app = FastAPI(title="Smart Grocery Shopping")
app.mount("/static", StaticFiles(directory=HERE / "static"), name="static")
app.mount("/uploads", StaticFiles(directory=UPLOADS), name="uploads")
tpl = Jinja2Templates(directory=HERE / "templates")
tpl.env.globals.update(LOCATIONS=db.LOCATIONS, LOC_LABEL=db.LOC_LABEL, CATEGORIES=db.CATEGORIES,
                       vision_on=vision.enabled(), today=lambda: date.today().isoformat())
PASSWORD = os.environ.get("APP_PASSWORD")
QUICK_MIN = 30
SKIP_KINDS = {"Dessert", "Drinks", "Side Dish", "Side", "Snack", "Appetizer", "Condiments"}


@app.middleware("http")
async def auth(request: Request, call_next):
    if PASSWORD and request.url.path != "/health":
        h = request.headers.get("authorization", "")
        ok = False
        if h.lower().startswith("basic "):
            try:
                _, _, pw = base64.b64decode(h[6:]).decode().partition(":")
                ok = hmac.compare_digest(pw, PASSWORD)
            except Exception:
                ok = False
        if not ok:
            return Response("Login required", 401, headers={"WWW-Authenticate": 'Basic realm="grocery"'})
    return await call_next(request)


@app.get("/health")
def health():
    return {"ok": True}


def item_rows(where="", args=()):
    con = db.connect()
    rows = [dict(r) for r in con.execute(f"SELECT * FROM items WHERE qty>0 {where} ORDER BY name", args)]
    con.close()
    for r in rows:
        eff = r["best_by"] or db.default_best_by(r["category"], r["location"], r["added_on"])
        r["eff_best_by"] = eff
        r["estimated"] = not r["best_by"]
        r["status"] = db.status(eff)
        r["age_days"] = (date.today() - date.fromisoformat(r["added_on"])).days
    return rows


def go(url):
    return RedirectResponse(url, status_code=303)


@app.get("/", response_class=HTMLResponse)
def tonight(request: Request, tab: str = "now", cuisine: str = "all", quick: int = 0, kid: int = 0, allkinds: int = 0):
    res = [r for r in matcher.score_all() if r["matched"] >= 3]
    if not allkinds:
        res = [r for r in res if not set(r["r"]["category"].split(",")) & SKIP_KINDS]
    if cuisine != "all":
        res = [r for r in res if r["r"]["cuisine"].lower() == cuisine]
    if quick:
        res = [r for r in res if r["r"]["minutes"] and r["r"]["minutes"] <= QUICK_MIN]
    if kid:
        res = [r for r in res if not ({"spicy", "salty", "choking", "raw fish"} & set(r["flags"]))]
    now = [r for r in res if not r["missing"]]
    miss = [r for r in res if 1 <= len(r["missing"]) <= 2]
    soon = [r for r in res if r["soon"] and r["frac"] >= 0.6]
    shown = {"now": now, "miss": miss, "soon": soon}.get(tab, now)
    shown = sorted(shown, key=lambda r: -r["score"])[:40]
    counts = {"now": len(now), "miss": len(miss), "soon": len(soon)}
    return tpl.TemplateResponse(request, "tonight.html", dict(recipes=shown, tab=tab, cuisine=cuisine, quick=quick,
                                kid=kid, allkinds=allkinds, counts=counts, QUICK_MIN=QUICK_MIN))


@app.get("/recipe/{rid}", response_class=HTMLResponse)
def recipe(request: Request, rid: int):
    info = matcher.recipe_info(rid)
    r = next((x for x in matcher.score_all() if x["id"] == rid), None)
    return tpl.TemplateResponse(request, "recipe.html", dict(info=info, r=r))


@app.get("/inventory", response_class=HTMLResponse)
def inventory(request: Request, loc: str = "all", q: str = ""):
    where, args = "", ()
    if loc != "all":
        where, args = "AND location=?", (loc,)
    rows = item_rows(where, args)
    if q:
        rows = [r for r in rows if q.lower() in r["name"].lower()]
    return tpl.TemplateResponse(request, "inventory.html", dict(rows=rows, loc=loc, q=q,
                                units=sum(r["qty"] for r in rows)))


@app.post("/inventory/{iid}")
def update_item(iid: int, qty: int = Form(...), best_by: str = Form(""), location: str = Form(...), back: str = Form("/inventory")):
    con = db.connect()
    old = con.execute("SELECT qty FROM items WHERE id=?", (iid,)).fetchone()
    con.execute("UPDATE items SET qty=?, best_by=?, location=? WHERE id=?", (max(qty, 0), best_by or None, location, iid))
    if old and old["qty"] != qty:
        con.execute("INSERT INTO events(item_id,action,delta) VALUES(?,?,?)", (iid, "edit", qty - old["qty"]))
    con.commit(); con.close()
    return go(back)


@app.get("/soon", response_class=HTMLResponse)
def soon(request: Request):
    rows = sorted(item_rows(), key=lambda r: (r["status"][2] if r["status"][2] is not None else 9999))
    groups = {"past": [r for r in rows if r["status"][1] == "past"], "soon": [r for r in rows if r["status"][1] == "soon"]}
    return tpl.TemplateResponse(request, "soon.html", dict(groups=groups))


@app.get("/plan", response_class=HTMLResponse)
def plan_page(request: Request):
    days = planner.load()
    seen, week_missing = set(), []
    for d in days:
        for m in d["missing"]:
            if m not in seen:
                seen.add(m); week_missing.append(m)
    return tpl.TemplateResponse(request, "plan.html", dict(days=days, week_missing=week_missing))


@app.post("/plan/generate")
def plan_generate():
    planner.save(planner.generate())
    return go("/plan")


@app.post("/plan/shopping")
def plan_shopping():
    con = db.connect()
    have = {r["text"] for r in con.execute("SELECT text FROM shopping WHERE done=0")}
    for d in planner.load():
        for m in d["missing"]:
            if m not in have:
                have.add(m)
                con.execute("INSERT INTO shopping(text,recipe) VALUES(?,?)", (m, d["info"]["row"]["name"] if d["info"] else None))
    con.commit(); con.close()
    return go("/shopping")


@app.get("/shopping", response_class=HTMLResponse)
def shopping(request: Request):
    con = db.connect()
    rows = [dict(r) for r in con.execute("SELECT * FROM shopping ORDER BY done, id")]
    con.close()
    return tpl.TemplateResponse(request, "shopping.html", dict(rows=rows))


@app.post("/shopping/add")
def shopping_add(text: str = Form(...), recipe: str = Form(""), back: str = Form("/shopping")):
    con = db.connect()
    for line in [t.strip() for t in text.split("\n") if t.strip()]:
        con.execute("INSERT INTO shopping(text,recipe) VALUES(?,?)", (line, recipe or None))
    con.commit(); con.close()
    return go(back)


@app.post("/shopping/recipe/{rid}")
def shopping_recipe(rid: int):
    r = next((x for x in matcher.score_all() if x["id"] == rid), None)
    con = db.connect()
    for line in (r["missing"] if r else []):
        con.execute("INSERT INTO shopping(text,recipe) VALUES(?,?)", (line, r["r"]["name"]))
    con.commit(); con.close()
    return go("/shopping")


@app.post("/shopping/{sid}/toggle")
def shopping_toggle(sid: int):
    con = db.connect()
    con.execute("UPDATE shopping SET done=1-done WHERE id=?", (sid,))
    con.commit(); con.close()
    return go("/shopping")


@app.post("/shopping/clear")
def shopping_clear():
    con = db.connect()
    con.execute("DELETE FROM shopping WHERE done=1")
    con.commit(); con.close()
    return go("/shopping")


@app.get("/cook/{rid}", response_class=HTMLResponse)
def cook_preview(request: Request, rid: int):
    r = next((x for x in matcher.score_all() if x["id"] == rid), None)
    names = {n for _, ns in (r["have"] if r else []) for n in ns}
    rows = [i for i in item_rows() if i["name"] in names and i["category"] in db.CONSUMABLE]
    return tpl.TemplateResponse(request, "cook.html", dict(r=r, rows=rows))


@app.post("/cook/{rid}")
async def cook_apply(request: Request, rid: int):
    form = await request.form()
    con = db.connect()
    for iid in form.getlist("use"):
        con.execute("UPDATE items SET qty=MAX(qty-1,0) WHERE id=?", (int(iid),))
        con.execute("INSERT INTO events(item_id,action,delta,note) VALUES(?,?,?,?)", (int(iid), "cooked", -1, f"recipe {rid}"))
    con.commit(); con.close()
    return go("/inventory")


@app.get("/add", response_class=HTMLResponse)
def add_form(request: Request, name: str = "", category: str = "other", best_by: str = "", qty: int = 1,
             location: str = "cabinet", photo: str = "", msg: str = ""):
    return tpl.TemplateResponse(request, "add.html", dict(f=dict(name=name, category=category, best_by=best_by, qty=qty,
                                location=location, photo=photo), msg=msg))


@app.post("/add")
def add_item(name: str = Form(...), category: str = Form(...), location: str = Form(...), qty: int = Form(1),
             best_by: str = Form(""), photo: str = Form("")):
    con = db.connect()
    con.execute("INSERT INTO items(name,category,location,qty,added_on,best_by,photo) VALUES(?,?,?,?,?,?,?)",
                (name.strip(), category, location, max(qty, 1), date.today().isoformat(), db._norm_date(best_by) or None, photo or None))
    con.commit(); con.close()
    return go("/inventory?loc=" + location)


@app.post("/add/photo")
async def add_photo(file: UploadFile = File(...), location: str = Form("cabinet")):
    if not vision.enabled():
        return go("/add?msg=Photo+intake+is+off+on+this+server")
    jpeg = vision.to_jpeg(await file.read())
    fn = secrets.token_hex(6) + ".jpg"
    (UPLOADS / fn).write_bytes(jpeg)
    try:
        d = vision.read(jpeg)
    except Exception as e:
        return go(f"/add?photo={fn}&location={location}&msg=Could+not+read+photo:+{type(e).__name__}")
    cat = d.get("category") if d.get("category") in db.CATEGORIES else "other"
    from urllib.parse import urlencode
    q = urlencode(dict(name=d.get("name") or "", category=cat, best_by=d.get("best_by") or "", photo=fn, location=location,
                       qty=int(d.get("quantity") or 1), msg="Check the details, then save"))
    return go("/add?" + q)
