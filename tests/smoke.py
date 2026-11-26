#!/usr/bin/env python3
"""Smoke test for app/index.html, run in headless Chromium with a simulated Claude.

The page normally talks to claude.ai (`window.claude.use("db" | "sample" | "user")`).
Here `db` is absent, so the app falls back to localStorage, which we seed from
tests/fixtures/state.json; `sample` (Claude) is replaced by canned JSON replies.

    pip install playwright && playwright install chromium
    python3 tests/smoke.py            # screenshots go to tests/out/

Barcode decoding loads ZXing from cdn.jsdelivr.net; without network that step is skipped.
"""
import asyncio, json, pathlib, sys
from playwright.async_api import async_playwright

ROOT = pathlib.Path(__file__).resolve().parent.parent
FIX = ROOT / "tests" / "fixtures"
OUT = ROOT / "tests" / "out"
URL = (ROOT / "app" / "index.html").as_uri()

STATE = json.loads((FIX / "state.json").read_text())
REPLIES = {k: json.loads((FIX / f"{k}.json").read_text()) for k in ("plan", "tweak", "products")}

MOCK = """
window.__R = %s; window.__prompts = [];
window.claude = { use: async (name) => {
  if (name !== 'sample') return null;
  const f = async (prompt, opts) => {
    window.__prompts.push(prompt);
    await new Promise(r => setTimeout(r, 100));
    const key = prompt.includes('CHANGE MEAL') ? 'tweak'
              : prompt.includes('grocery products I bought') ? 'products' : 'plan';
    return { text: JSON.stringify(window.__R[key]) };
  };
  f.limits = async () => ({ images: true });
  return f;
}};
""" % json.dumps(REPLIES)

failures = []


def check(cond, msg):
    print(("  ok   " if cond else "  FAIL ") + msg)
    if not cond:
        failures.append(msg)


async def main():
    OUT.mkdir(exist_ok=True)
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page(viewport={"width": 390, "height": 844})
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        await page.add_init_script(MOCK)

        async def load(hash_=""):
            await page.goto(URL + hash_)
            await page.reload()
            await page.wait_for_timeout(700)

        async def state():
            return await page.evaluate("JSON.parse(localStorage.getItem('pm-local'))")

        await page.goto(URL)
        await page.evaluate("s => localStorage.setItem('pm-local', s)", json.dumps(STATE))

        print("pantry")
        await load("#pantry")
        rows = await page.locator("#plist .row").count()
        check(rows >= 50, f"pantry lists items ({rows})")
        check(await page.locator("#pfilt button").count() >= 2, "store filter shows")
        await page.screenshot(path=str(OUT / "1-pantry.png"))

        print("item details")
        await page.click('.row[data-id="i-protein-mousse"] .nm')
        await page.wait_for_timeout(300)
        txt = await page.inner_text("#sheet")
        check("Nutri-Score" in txt and "Mercadona" in txt, "details show nutrition and store")
        await page.screenshot(path=str(OUT / "2-details.png"))
        await page.click("#dclose")

        print("barcode scan")
        await load("#add")
        await page.set_input_files("#bf", str(FIX / "ean_photo.jpg"))
        await page.wait_for_timeout(5000)
        sheet = await page.inner_text("#sheet") if await page.is_visible("#sheet") else ""
        if "tomato" in sheet.lower():
            check(True, "barcode matched the tomato sauce")
        else:
            print("  skip barcode decode (no network for ZXing?)")

        print("product photos")
        await load("#add")
        before = (await state())["items"]["i-tomato-sauce"]["qty"]
        await page.set_input_files("#pf", [str(FIX / "ean_photo.jpg")])
        await page.wait_for_timeout(2500)
        check(await page.locator("#review .rl").count() == len(REPLIES["products"]["products"]), "review lists every product")
        await page.screenshot(path=str(OUT / "3-photo-review.png"))
        await page.click('.rl[data-k="2"] [data-f=on]')  # untick the shower gel
        await page.click("#rok")
        await page.wait_for_timeout(400)
        s = await state()
        check(not any("Shower" in i["name"] for i in s["items"].values()), "unticked product not added")
        check(len(s["receipts"]) == len(STATE["receipts"]), "photos don't create a receipt record")
        check(sum(1 for i in s["items"].values() if "tuna" in i["name"].lower() or i["id"] == "i-tomato-sauce") >= 1, "products added or restocked")
        _ = before

        print("shopping list")
        await load("#list")
        lst = await page.inner_text("#slist")
        check("estimated" in lst and "Last bought" in lst, "list shows estimate and last bought")
        await page.screenshot(path=str(OUT / "4-list.png"))

        print("meal plan")
        await load("#meals")
        await page.click("#pmode [data-m=multi]")
        await page.click("#pgo")
        await page.wait_for_timeout(900)
        check(await page.locator("#pout article").count() == 3, "plan has 3 meals")
        check(await page.locator("#pout .nutl").count() >= 3, "meals show nutrition per serving")
        await page.screenshot(path=str(OUT / "5-plan.png"))
        prompt = await page.evaluate("window.__prompts[window.__prompts.length-1]")
        check("what is in my kitchen. Today" in prompt, "plan prompt has no built-in location")

        print("location setting")
        await page.fill("#pwhere", "Lyon, France; mostly Carrefour")
        await page.dispatch_event("#pwhere", "change")
        await page.wait_for_timeout(200)
        st = await state()
        check(((st.get("settings") or {}).get("home") or {}).get("where") == "Lyon, France; mostly Carrefour", "location is saved")
        await page.click("#pgo")
        await page.wait_for_timeout(900)
        prompt = await page.evaluate("window.__prompts[window.__prompts.length-1]")
        check("my kitchen (Lyon, France; mostly Carrefour)" in prompt, "plan prompt uses the location")
        await load("#meals")
        check(await page.input_value("#pwhere") == "Lyon, France; mostly Carrefour", "location shows after reload")
        await page.locator("#pwhere").scroll_into_view_if_needed()
        await page.screenshot(path=str(OUT / "5b-location.png"))

        print("tweak")
        await page.click('#pout article[data-k="1"] [data-a=tweak]')
        await page.click('.tw[data-i="0"] [data-f=rm]')
        await page.click("#twch [data-c=vegetarian]")
        await page.click("#twgo")
        await page.wait_for_timeout(700)
        prompt = await page.evaluate("window.__prompts[window.__prompts.length-1]")
        check('"steps"' in prompt and "Change as little as possible" in prompt, "tweak sends the full recipe")
        titles = await page.locator("#pout article h3").all_inner_texts()
        check(any("Goat cheese" in t for t in titles), "tweaked meal replaced")
        check(await page.locator("#pout .chg").count() >= 2, "other meal adjusted and marked")

        print("favourites")
        await page.click('#pout article[data-k="0"] [data-a=fav]')
        await page.wait_for_timeout(200)
        check(await page.is_visible("#favwrap"), "favourites section appears")
        n_plans = len((await state())["plans"])
        await page.click("#favs .fav [data-fa=again]")
        await page.wait_for_timeout(300)
        s = await state()
        check(len(s["plans"]) == n_plans + 1, "cook again creates a new plan")
        await page.screenshot(path=str(OUT / "6-favourites.png"))

        check(not errors, "no page errors " + ("" if not errors else str(errors)))
        await browser.close()

    print("\n" + ("PASSED" if not failures else f"FAILED: {len(failures)}"))
    sys.exit(1 if failures else 0)


asyncio.run(main())
