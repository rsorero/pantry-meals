#!/usr/bin/env python3
"""Product lookups for the Pantry & Meals app (pantry, shopping and meal planning).

Sources (public, no keys):
  - Mercadona online shop API (tienda.mercadona.es): name, brand, EAN barcode,
    ingredients, allergens, origin, pack size, product page.
  - Open Food Facts (world.openfoodfacts.org): nutrition per 100 g/ml,
    Nutri-Score, NOVA group, ingredients/allergens when Mercadona has none.

Usage:
  python3 lookup.py catalog                 # cache the Mercadona catalogue -> catalog.json
  python3 lookup.py search "masa pizza"     # top candidates from the catalogue
  python3 lookup.py mercadona <id>          # build an info record from a Mercadona product id
  python3 lookup.py ean <barcode>           # build an info record from a barcode (OFF, + Mercadona if cached)
Each record command prints one JSON object (the app's `info/<itemId>` document body, minus itemId).
"""
import json, os, re, sys, time, unicodedata, urllib.request, html

UA = {"User-Agent": "PantryMealsApp/1.0 (personal kitchen inventory)"}
HERE = os.path.dirname(os.path.abspath(__file__))
CAT = os.path.join(HERE, "catalog.json")


def get(url, tries=3):
    for i in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=25) as r:
                return json.loads(r.read().decode())
        except Exception as e:  # noqa
            if i == tries - 1:
                raise
            time.sleep(1.5 * (i + 1))


def norm(s):
    s = unicodedata.normalize("NFD", str(s or "")).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9 ]+", " ", s)


def clean(s):
    s = html.unescape(re.sub(r"<[^>]+>", "", str(s or ""))).strip()
    s = re.sub(r"^(ingredientes|ingredients)\s*:\s*", "", s, flags=re.I)
    return re.sub(r"\s+", " ", s).strip(" .") or None


def catalog():
    top = get("https://tienda.mercadona.es/api/categories/")["results"]
    out = []
    for t in top:
        for c in t.get("categories", []):
            try:
                d = get(f"https://tienda.mercadona.es/api/categories/{c['id']}/")
            except Exception:
                continue
            for sub in d.get("categories", []):
                for p in sub.get("products", []):
                    pi = p.get("price_instructions") or {}
                    out.append({"id": p["id"], "name": p.get("display_name"), "pack": p.get("packaging"),
                                "size": pi.get("unit_size"), "fmt": pi.get("size_format"),
                                "price_es": pi.get("unit_price"), "cat": f"{t['name']} / {sub.get('name')}",
                                "url": p.get("share_url")})
            time.sleep(0.15)
    json.dump(out, open(CAT, "w"), ensure_ascii=False)
    print(json.dumps({"products": len(out)}))


def search(q, n=10):
    cat = json.load(open(CAT))
    qt = [w for w in norm(q).split() if len(w) > 1]
    scored = []
    for p in cat:
        nm = norm(p["name"]) + " " + norm(p.get("cat"))
        words = nm.split()
        s = sum(2 if w in words else (1 if any(x.startswith(w[:5]) for x in words) else 0) for w in qt)
        if s:
            scored.append((s, p))
    scored.sort(key=lambda x: -x[0])
    return [dict(score=s, **p) for s, p in scored[:n]]


def off(ean):
    try:
        d = get(f"https://world.openfoodfacts.org/api/v2/product/{ean}.json?fields=code,product_name,product_name_pt,brands,stores,quantity,ingredients_text_pt,ingredients_text_es,ingredients_text_en,ingredients_text,allergens_tags,traces_tags,nutriments,nutriscore_grade,nova_group,labels_tags")
    except Exception:
        return None
    if d.get("status") != 1:
        return None
    return d["product"]


def nutri(p):
    n = (p or {}).get("nutriments") or {}
    keys = {"kcal": "energy-kcal_100g", "fat": "fat_100g", "sat": "saturated-fat_100g", "carbs": "carbohydrates_100g",
            "sugars": "sugars_100g", "fiber": "fiber_100g", "protein": "proteins_100g", "salt": "salt_100g"}
    out = {k: round(float(n[v]), 2) for k, v in keys.items() if isinstance(n.get(v), (int, float))}
    return out or None


ALG = [("gluten", ("gluten", "trigo", "cebada", "centeno", "avena", "espelta")), ("milk", ("leche", "lactosa", "milk")),
       ("eggs", ("huevo", "egg")), ("soy", ("soja", "soy")), ("tree nuts", ("frutos de cascara", "nuts", "nueces")),
       ("peanuts", ("cacahuete", "peanut")), ("fish", ("pescado", "fish")), ("crustaceans", ("crustaceo", "crustacean")),
       ("molluscs", ("molusco", "mollusc")), ("celery", ("apio", "celery")), ("mustard", ("mostaza", "mustard")),
       ("sesame", ("sesamo", "sesame")), ("sulphites", ("sulfito", "azufre", "sulphite", "sulfite")), ("lupin", ("altramuz", "lupin"))]


def allergen_names(txt):
    t = norm(txt)
    return [en for en, keys in ALG if any(k in t for k in keys)]


def parse_allergens(text):
    """Spanish Mercadona allergen sentences -> (contains, may_contain) in English."""
    has, may = [], []
    for sent in re.split(r"[.;]", text or ""):
        t = norm(sent).strip()
        if not t or t.startswith("libre de"):
            continue
        target = may if ("puede contener" in t or "trazas" in t) else has if "contiene" in t else None
        if target is None:
            continue
        for a in allergen_names(t):
            if a not in target:
                target.append(a)
    may = [a for a in may if a not in has]
    return has or None, may or None


def tags(t):
    out = []
    for x in t or []:
        a = allergen_names(x.split(":", 1)[-1].replace("-", " "))
        out += [y for y in a if y not in out]
    return out or None


def labels(t):
    return [x.split(":", 1)[-1].replace("-", " ") for x in (t or [])] or None


def from_off(ean, rec):
    p = off(ean)
    if not p:
        return rec
    rec["sources"].append({"name": "Open Food Facts", "url": f"https://world.openfoodfacts.org/product/{ean}"})
    rec["nutrition"] = nutri(p)
    g = (p.get("nutriscore_grade") or "").lower()
    rec["nutriscore"] = g.upper() if g in "abcde" and g else None
    rec["nova"] = p.get("nova_group")
    rec.setdefault("brand", None)
    rec["brand"] = rec["brand"] or (p.get("brands") or "").split(",")[0].strip() or None
    rec["fullName"] = rec.get("fullName") or p.get("product_name_pt") or p.get("product_name")
    rec["size"] = rec.get("size") or p.get("quantity")
    rec["ingredients"] = rec.get("ingredients") or clean(p.get("ingredients_text_pt") or p.get("ingredients_text_es") or p.get("ingredients_text_en") or p.get("ingredients_text"))
    rec["allergens"] = rec.get("allergens") or tags(p.get("allergens_tags"))
    rec["traces"] = rec.get("traces") or tags(p.get("traces_tags"))
    labs = [l for l in labels(p.get("labels_tags")) or [] if any(k in l for k in ("vegan", "vegetarian", "gluten", "lactose", "organic", "bio"))]
    rec["labels"] = labs or None
    return rec


def mercadona(mid):
    d = get(f"https://tienda.mercadona.es/api/products/{mid}/")
    ni = d.get("nutrition_information") or {}
    pi = d.get("price_instructions") or {}
    det = d.get("details") or {}
    al = clean(ni.get("allergens"))
    if al and re.fullmatch(r"x\d+", al or ""):
        al = None
    size = f"{pi.get('unit_size')} {pi.get('size_format')}".strip() if pi.get("unit_size") else None
    rec = {"barcode": d.get("ean"), "fullName": d.get("display_name"), "brand": d.get("brand") or det.get("brand"),
           "origin": d.get("origin") or det.get("origin"), "size": size, "packaging": d.get("packaging"),
           "ingredients": clean(ni.get("ingredients")), "allergensText": al,
           "allergens": parse_allergens(al)[0], "traces": parse_allergens(al)[1],
           "sources": [{"name": "Mercadona shop (Spain)", "url": d.get("share_url")}],
           "match": "name", "updated": time.strftime("%Y-%m-%d")}
    if d.get("ean"):
        rec = from_off(d["ean"], rec)
    return rec


def tidy(rec):
    has = rec.get("allergens") or []
    rec["traces"] = [t for t in (rec.get("traces") or []) if t not in has] or None
    rec["allergens"] = has or None
    return rec


def by_ean(ean):
    rec = {"barcode": ean, "sources": [], "match": "barcode", "updated": time.strftime("%Y-%m-%d"), "brand": None}
    rec = from_off(ean, rec)
    if not rec["sources"]:
        rec["notFound"] = True
    return rec


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "catalog":
        catalog()
    elif cmd == "search":
        print(json.dumps(search(" ".join(sys.argv[2:])), ensure_ascii=False, indent=0))
    elif cmd == "mercadona":
        print(json.dumps(tidy(mercadona(sys.argv[2])), ensure_ascii=False))
    elif cmd == "ean":
        print(json.dumps(tidy(by_ean(sys.argv[2])), ensure_ascii=False))
    else:
        print(__doc__)
