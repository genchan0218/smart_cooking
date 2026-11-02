import json, re, collections
P = r"C:/Users/genki/Documents/Personal Project/Smart Grocery Shopping/data/"
rec = json.load(open(P + "recipes.json", encoding="utf-8"))
inv = json.load(open(P + "inventory.json", encoding="utf-8"))

# canonical ingredient -> regex that finds it in a recipe ingredient line
VOCAB = {
 "soy sauce": r"soy sauce|shoyu|tamari", "mirin": r"\bmirin", "sake": r"\bsake\b|cooking wine",
 "rice vinegar": r"rice (wine )?vinegar", "ponzu": r"ponzu", "mayonnaise": r"mayo",
 "ketchup": r"ketchup", "worcestershire": r"worcestershire|usuta", "tonkatsu sauce": r"tonkatsu sauce|katsu sauce|bulldog|okonomi.*sauce|chuno|yakisoba sauce",
 "dashi": r"dashi|hondashi|bonito|katsuobushi", "kombu": r"kombu|kelp", "shiitake": r"shiitake",
 "salmon": r"salmon", "cabbage": r"cabbage", "cucumber": r"cucumber", "potato": r"potato(?!.*starch)",
 "tomato": r"tomato(?!.*(paste|sauce|ketchup|puree|puree))", "milk": r"\bmilk\b", "yogurt": r"yogurt|yoghurt",
 "mozzarella": r"mozzarella", "edamame": r"edamame|soybeans", "gyoza": r"gyoza|dumpling|potsticker",
 "udon": r"udon", "ramen noodles": r"ramen|noodles", "yakisoba": r"yakisoba|yaki-soba",
 "garlic": r"garlic", "ginger": r"ginger", "pasta": r"pasta|spaghetti|fettuccine|penne|linguine|macaroni",
 "gnocchi": r"gnocchi", "chicken stock": r"chicken (stock|broth)|stock|broth", "tabasco": r"tabasco|hot sauce",
 "mustard": r"mustard", "sesame dressing": r"sesame (dressing|sauce)", "yuzu": r"yuzu",
 "hot dog buns": r"hot dog bun|brioche bun", "ham": r"\bham\b", "sausage": r"sausage",
 "chicken wings": r"chicken wing|\bwings\b", "breaded chicken": r"chicken (nuggets|tenders)|breaded chicken",
 "chicken": r"chicken(?! (stock|broth|wing|nugget|tender))", "shrimp/seafood": r"shrimp|prawn|seafood|squid",
 "curry roux": r"curry (roux|block|cube)|golden curry|vermont", "stew roux": r"stew roux|demi.?glace",
 "tenkasu": r"tenkasu|tempura (bits|scraps|crumb)|age.?dama", "tororo kombu": r"tororo",
 "pancake mix": r"pancake mix|hotcake", "mochi": r"mochi", "beef": r"\bbeef\b|steak", "pork": r"\bpork\b|bacon",
 "alfredo/cream sauce": r"alfredo|cream sauce", "vodka sauce": r"vodka sauce",
 "furikake": r"furikake", "nori": r"\bnori\b", "peanut butter": r"peanut butter", "bread": r"\bbread\b|\bbuns?\b",
 "cheese": r"cheese", "naan": r"naan", "pizza": r"pizza", "meatballs": r"meatball",
}
# inventory item -> canonical names it provides
PROVIDES = {
 "soy sauce": ["soy sauce"], "mirin": ["mirin"], "cooking sake": ["sake"], "vinegar": ["rice vinegar"],
 "ponzu": ["ponzu"], "mayonnaise": ["mayonnaise"], "ketchup": ["ketchup"], "worcestershire": ["worcestershire"],
 "tonkatsu": ["tonkatsu sauce"], "okonomi": ["tonkatsu sauce"], "chuno": ["tonkatsu sauce"],
 "dashi": ["dashi"], "hondashi": ["dashi"], "kombu": ["kombu", "dashi"], "tsuyu": ["dashi", "soy sauce"],
 "shiitake": ["shiitake"], "salmon": ["salmon"], "cabbage": ["cabbage"], "cucumber": ["cucumber"],
 "potato": ["potato"], "tomato": ["tomato"], "milk": ["milk"], "yogurt": ["yogurt"], "mozzarella": ["mozzarella", "cheese"],
 "edamame": ["edamame"], "gyoza": ["gyoza"], "dumpling": ["gyoza"], "udon": ["udon"], "ramen": ["ramen noodles"],
 "champon": ["ramen noodles"], "yaki-soba": ["yakisoba", "ramen noodles"], "garlic": ["garlic"], "ginger": ["ginger"],
 "pasta": ["pasta"], "gnocchi": ["gnocchi"], "stock": ["chicken stock"], "tabasco": ["tabasco"], "mustard": ["mustard"],
 "yuzu": ["yuzu"], "buns": ["hot dog buns", "bread"], "ham": ["ham"], "sausage": ["sausage"],
 "chicken": ["chicken"], "seafood mix": ["shrimp/seafood"], "shrimp": ["shrimp/seafood"], "curry roux": ["curry roux"],
 "stew roux": ["stew roux"], "demi-glace": ["stew roux"], "aage-dama": ["tenkasu"], "tororo": ["tororo kombu"],
 "pancake mix": ["pancake mix"], "mochi": ["mochi"], "beef": ["beef"], "alfredo": ["alfredo/cream sauce"],
 "vodka": ["vodka sauce"], "furikake": ["furikake"], "pb&j": ["peanut butter", "bread"], "naan": ["naan", "bread"],
 "pizza": ["pizza"], "meatballs": ["meatballs"], "sesame": ["sesame dressing"],
}
# drop over-broad keys; replace with specific ones
for k in ("chicken", "shrimp", "beef", "tomato", "potato", "cabbage", "cucumber", "milk", "pizza", "naan"):
    PROVIDES.pop(k, None)
PROVIDES.update({"chicken wings": ["chicken wings"], "breast chunks": ["breaded chicken"], "bulgogi": ["beef"],
                 "cherry tomato": ["tomato"], "tomatoes": ["tomato"]})
# keys that only count for items in these categories (stops "cabbage sauce" counting as cabbage)
ONLY_CAT = {"cabbage": {"produce"}, "potato": {"produce"}, "cucumber": {"produce"}, "milk": {"dairy"},
            "salmon": {"frozen seafood"}, "edamame": {"frozen vegetable"}, "mozzarella": {"dairy"},
            "garlic": {"seasoning"}, "ginger": {"seasoning"}, "cherry tomato": {"produce"}}
PROVIDES.update({"cabbage": ["cabbage"], "potato": ["potato"], "cucumber": ["cucumber"], "milk": ["milk"]})
have = collections.defaultdict(list)
for it in inv:
    n = it["name"].lower()
    for key, names in PROVIDES.items():
        if key in n and it["category"] in ONLY_CAT.get(key, {it["category"]}):
            for c in names:
                have[c].append(it["id"])
# basics assumed on hand (not in the photos)
STAPLE = r"\b(salt|pepper|sugar|water|oil|flour|cornstarch|starch|baking|vegetable oil|olive oil|sesame oil|butter|panko|eggs?|rice|onions?|scallions?|green onions?|spring onions?|shallots?)\b"
OPTIONAL = r"garnish|optional|to taste|for serving|for frying|for deep"

def parse(line):
    l = line.lower()
    if re.search(STAPLE, l) and not any(re.search(p, l) for p in VOCAB.values()):
        return None  # staple only
    hits = [c for c, p in VOCAB.items() if re.search(p, l)]
    return hits  # may be empty -> unknown ingredient (treated as missing)

results = []
for r in rec:
    need = []  # list of (line, [canonical alternatives]) ; empty alternatives = unknown
    for line in r["ingredients"]:
        if re.search(OPTIONAL, line.lower()):
            continue
        p = parse(line)
        if p is None:
            continue
        need.append((line, p))
    if not need:
        continue
    ok, miss = [], []
    for line, alts in need:
        if alts and any(a in have for a in alts):
            ok.append(line)
        else:
            miss.append(line)
    frac = len(ok) / len(need)
    used = sorted({c for line, alts in need for c in alts if c in have})
    results.append({"id": r["id"], "name": r["name"], "cuisine": r["cuisine"], "category": r["category"], "url": r["url"],
                    "matched": len(ok), "total": len(need), "frac": round(frac, 2), "missing": miss, "uses": used})
json.dump(results, open(P + "recipe_matches.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)

def main(r): return not set(r["category"]) & {"Dessert", "Drinks", "Side Dish", "Snack", "Appetizer"}
good = [r for r in results if main(r) and r["total"] >= 3 and r["matched"] >= 3]
good.sort(key=lambda r: (-r["frac"], -r["matched"]))
print("recipes scored:", len(results), "| can make (>=90% of ingredients, >=3 matched):",
      len([r for r in good if r["frac"] >= 0.9]), "| missing 1-2 items:", len([r for r in good if 0.6 <= r["frac"] < 0.9 and r["total"] - r["matched"] <= 2]))
for r in good[:25]:
    print(f'{r["frac"]:.2f} {r["matched"]}/{r["total"]} [{r["cuisine"][0]}] {r["name"]} | miss: {[m[:30] for m in r["missing"]][:3]}')
