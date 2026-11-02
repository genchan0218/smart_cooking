"""Match recipes to inventory. Recipe ingredient lines are free text, so each line is mapped to canonical
ingredient names by keyword; an inventory item provides canonical names by keyword on its name + category."""
import json, re
from collections import defaultdict
from datetime import date

import db

VOCAB = {
 "soy sauce": r"soy sauce|shoyu|tamari", "mirin": r"\bmirin", "sake": r"\bsake\b|cooking wine",
 "rice vinegar": r"rice (wine )?vinegar", "ponzu": r"ponzu", "mayonnaise": r"mayo",
 "ketchup": r"ketchup", "worcestershire": r"worcestershire|usuta",
 "tonkatsu sauce": r"tonkatsu sauce|katsu sauce|bulldog|okonomi.*sauce|chuno|yakisoba sauce",
 "dashi": r"dashi|hondashi|bonito|katsuobushi", "kombu": r"kombu|kelp", "shiitake": r"shiitake",
 "salmon": r"salmon", "cabbage": r"cabbage", "cucumber": r"cucumber", "potato": r"potato(?!.*starch)",
 "tomato": r"tomato(?!.*(paste|sauce|ketchup|puree))", "milk": r"\bmilk\b", "yogurt": r"yogurt|yoghurt",
 "mozzarella": r"mozzarella", "edamame": r"edamame|soybeans", "gyoza": r"gyoza|dumpling|potsticker",
 "udon": r"udon", "ramen noodles": r"ramen|noodles", "yakisoba": r"yakisoba|yaki-soba",
 "garlic": r"garlic", "ginger": r"ginger", "pasta": r"pasta|spaghetti|fettuccine|penne|linguine|macaroni",
 "gnocchi": r"gnocchi", "chicken stock": r"chicken (stock|broth)|stock|broth", "tabasco": r"tabasco|hot sauce",
 "mustard": r"mustard", "sesame dressing": r"sesame (dressing|sauce)", "yuzu": r"yuzu",
 "hot dog buns": r"hot dog bun|brioche bun", "ham": r"\bham\b", "sausage": r"sausage",
 "chicken wings": r"chicken wing|\bwings\b", "breaded chicken": r"chicken nuggets|breaded chicken|popcorn chicken",
 "chicken": r"chicken(?! (stock|broth|wing|nugget))", "shrimp/seafood": r"shrimp|prawn|seafood|squid",
 "curry roux": r"curry (roux|block|cube)|golden curry|vermont", "stew roux": r"stew roux|demi.?glace",
 "tenkasu": r"tenkasu|tempura (bits|scraps|crumb)|age.?dama", "tororo kombu": r"tororo",
 "pancake mix": r"pancake mix|hotcake", "mochi": r"mochi", "beef": r"\bbeef\b|steak", "pork": r"\bpork\b|bacon",
 "alfredo/cream sauce": r"alfredo|cream sauce", "vodka sauce": r"vodka sauce", "furikake": r"furikake",
 "nori": r"\bnori\b", "peanut butter": r"peanut butter", "bread": r"\bbread\b|\bbuns?\b", "cheese": r"cheese",
 "naan": r"naan", "pizza": r"pizza", "meatballs": r"meatball",
}
VOCAB_RE = {k: re.compile(v) for k, v in VOCAB.items()}

# keyword in an inventory item's name -> canonical ingredients it provides
PROVIDES = {
 "soy sauce": ["soy sauce"], "mirin": ["mirin"], "cooking sake": ["sake"], "vinegar": ["rice vinegar"],
 "ponzu": ["ponzu"], "mayonnaise": ["mayonnaise"], "ketchup": ["ketchup"], "worcestershire": ["worcestershire"],
 "tonkatsu": ["tonkatsu sauce"], "okonomi": ["tonkatsu sauce"], "chuno": ["tonkatsu sauce"],
 "dashi": ["dashi"], "hondashi": ["dashi"], "kombu": ["kombu", "dashi"], "tsuyu": ["dashi", "soy sauce"],
 "shiitake": ["shiitake"], "salmon": ["salmon"], "cabbage": ["cabbage"], "cucumber": ["cucumber"],
 "potato": ["potato"], "tomato": ["tomato"], "milk": ["milk"], "yogurt": ["yogurt"],
 "mozzarella": ["mozzarella", "cheese"], "edamame": ["edamame"], "gyoza": ["gyoza"], "dumpling": ["gyoza"],
 "udon": ["udon"], "ramen": ["ramen noodles"], "champon": ["ramen noodles"],
 "yaki-soba": ["yakisoba", "ramen noodles"], "garlic": ["garlic"], "ginger": ["ginger"], "pasta": ["pasta"],
 "gnocchi": ["gnocchi"], "stock": ["chicken stock"], "tabasco": ["tabasco"], "mustard": ["mustard"],
 "yuzu": ["yuzu"], "buns": ["hot dog buns", "bread"], "ham": ["ham"], "sausage": ["sausage"],
 "chicken wings": ["chicken wings"], "breast chunks": ["breaded chicken"], "bulgogi": ["beef"],
 "seafood mix": ["shrimp/seafood"], "curry roux": ["curry roux"], "stew roux": ["stew roux"],
 "demi-glace": ["stew roux"], "aage-dama": ["tenkasu"], "tororo": ["tororo kombu"],
 "pancake mix": ["pancake mix"], "mochi": ["mochi"], "alfredo": ["alfredo/cream sauce"],
 "vodka": ["vodka sauce"], "furikake": ["furikake"], "pb&j": ["peanut butter", "bread"], "naan": ["naan", "bread"],
 "pizza": ["pizza"], "meatballs": ["meatballs"], "sesame": ["sesame dressing"],
}
# these keys only count for items of these categories (stops "cabbage sauce" counting as cabbage)
ONLY_CAT = {"tonkatsu": {"sauce"}, "okonomi": {"sauce"}, "chuno": {"sauce"}, "pizza": {"frozen meal"},
            "cabbage": {"produce"}, "potato": {"produce"}, "cucumber": {"produce"}, "tomato": {"produce"},
            "milk": {"dairy"}, "salmon": {"frozen seafood"}, "edamame": {"frozen vegetable"},
            "mozzarella": {"dairy"}, "garlic": {"seasoning"}, "ginger": {"seasoning"}}

STAPLE = re.compile(r"\b(salt|pepper|sugar|water|oil|flour|cornstarch|starch|baking|butter|panko|eggs?|rice|"
                    r"onions?|scallions?|green onions?|spring onions?|shallots?)\b")
OPTIONAL = re.compile(r"garnish|optional|to taste|for serving|for frying|for deep")

# toddler flags, derived from the ingredient text
FLAGS = {
 "spicy": re.compile(r"chili|chilli|spicy|sriracha|tabasco|gochujang|cayenne|jalape|kung pao|shichimi|togarashi|wasabi"),
 "salty": re.compile(r"furikake|instant (ramen|noodle)|miso|oyster sauce|fish sauce|bouillon|shin ramyun"),
 "choking": re.compile(r"\bwhole (nuts?|almonds?|peanuts?|cashews?)|peanuts|almonds|cashews|grapes|popcorn|hard candy"),
 "raw fish": re.compile(r"sashimi|raw (fish|salmon|tuna)|tartare|\bsushi\b|poke"),
}


def provides(name, category):
    n = name.lower()
    out = set()
    for key, names in PROVIDES.items():
        if key in n and category in ONLY_CAT.get(key, {category}):
            out.update(names)
    return out


def _recipe_needs(lines):
    """-> list of (line, [canonical alternatives]); staples and optional lines dropped"""
    need = []
    for line in lines:
        l = line.lower()
        if OPTIONAL.search(l):
            continue
        hits = [c for c, p in VOCAB_RE.items() if p.search(l)]
        if STAPLE.search(l) and not hits:
            continue
        need.append((line, hits))
    return need


_CACHE = {}


def _recipes():
    if not _CACHE:
        con = db.connect()
        for r in con.execute("SELECT * FROM recipes"):
            lines = json.loads(r["ingredients"])
            text = " ".join(lines).lower() + " " + r["name"].lower()
            _CACHE[r["id"]] = {"row": dict(r), "lines": lines, "need": _recipe_needs(lines),
                               "flags": [f for f, p in FLAGS.items() if p.search(text)]}
        con.close()
    return _CACHE


def recipe_info(rid):
    return _recipes().get(rid)


def score_all(today=None):
    """Score every recipe against current inventory."""
    today = today or date.today()
    con = db.connect()
    items = [dict(r) for r in con.execute("SELECT * FROM items WHERE qty>0")]
    con.close()
    have = defaultdict(list)  # canonical -> items providing it
    for it in items:
        it["status"] = db.status(it["best_by"] or db.default_best_by(it["category"], it["location"], it["added_on"]), today)
        for c in provides(it["name"], it["category"]):
            have[c].append(it)
    out = []
    for rid, info in _recipes().items():
        need = info["need"]
        if len(need) < 2:
            continue
        ok, miss, soon = [], [], []
        for line, alts in need:
            src = [it for a in alts for it in have.get(a, [])]
            if src:
                ok.append((line, src))
                soon += [it for it in src if it["status"][1] in ("soon", "past")]
            else:
                miss.append(line)
        total = len(need)
        frac = len(ok) / total
        soon_names = sorted({it["name"] for it in soon})
        score = frac * 10 + 0.4 * min(len(ok), 6) + 0.6 * len(soon_names) - 1.2 * len(miss)
        out.append({"id": rid, "r": info["row"], "flags": info["flags"], "matched": len(ok), "total": total,
                    "frac": frac, "missing": miss, "have": [(l, sorted({i["name"] for i in s})) for l, s in ok],
                    "soon": soon_names, "score": score})
    return out
