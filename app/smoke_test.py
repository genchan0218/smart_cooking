"""Smoke test: hits every page with a throwaway database. Run from the app/ folder: python smoke_test.py"""
import os, sys, tempfile
tmp = tempfile.mkdtemp()
os.environ["GROCERY_DB"] = os.path.join(tmp, "t.db")
os.environ["GROCERY_UPLOADS"] = os.path.join(tmp, "up")
os.environ["VISION_BACKEND"] = "off"
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from fastapi.testclient import TestClient
import main

c = TestClient(main.app)
fails = 0


def check(label, r, want=200, text=None):
    global fails
    ok = r.status_code == want and (text is None or text in r.text)
    fails += not ok
    print(("PASS " if ok else "FAIL ") + label, r.status_code)


check("health", c.get("/health"))
check("tonight now", c.get("/"), text="ingredients on hand")
check("tonight miss", c.get("/?tab=miss"))
check("tonight soon", c.get("/?tab=soon"))
check("tonight filters", c.get("/?tab=now&cuisine=japanese&quick=1&kid=1&allkinds=1"))
check("inventory", c.get("/inventory"), text="Kitchen fridge")
check("inventory filter+search", c.get("/inventory?loc=cabinet&q=furikake"), text="furikake")
check("use soon", c.get("/soon"), text="Past best-by")
check("recipe page", c.get("/recipe/1"))
check("shopping page", c.get("/shopping"))
check("add page", c.get("/add"), text="Save item")
r = c.post("/add", data=dict(name="Test tofu", category="refrigerated meal", location="kitchen_fridge", qty=2, best_by="2026-11"), follow_redirects=False)
check("add item", r, want=303)
check("item shows", c.get("/inventory?q=tofu"), text="Test tofu")
r = c.post("/shopping/add", data=dict(text="eggs\nmilk"), follow_redirects=False)
check("shopping add", r, want=303)
check("shopping shows", c.get("/shopping"), text="milk")
check("shopping from recipe", c.post("/shopping/recipe/1", follow_redirects=False), want=303)
check("cook preview", c.get("/cook/1"))
print("DONE, failures:", fails)
sys.exit(1 if fails else 0)
