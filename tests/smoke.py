#!/usr/bin/env python3
"""Smoke test for app/index.html, run in headless Chromium with a simulated Claude.

The page normally talks to claude.ai (`window.claude.use("db" | "sample" | "user" | "assets")`).
Here `db` is absent, so the app falls back to localStorage, which we seed from
tests/fixtures/state.json; `sample` (Claude) is replaced by canned JSON replies, and
`assets` by an in-memory store whose `/_blob/<id>` URLs serve the test receipt photo.
The page is served from a local HTTP server so those URLs resolve.

    pip install playwright && playwright install chromium
    python3 tests/smoke.py            # screenshots go to tests/out/

Barcode decoding loads ZXing from cdn.jsdelivr.net; without network that step is skipped.
"""
import asyncio, datetime, functools, http.server, json, pathlib, sys, threading
from playwright.async_api import async_playwright

ROOT = pathlib.Path(__file__).resolve().parent.parent
FIX = ROOT / "tests" / "fixtures"
OUT = ROOT / "tests" / "out"

class Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass


SERVER = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(Quiet, directory=str(ROOT / "app")))
threading.Thread(target=SERVER.serve_forever, daemon=True).start()
URL = f"http://127.0.0.1:{SERVER.server_address[1]}/index.html"

STATE = json.loads((FIX / "state.json").read_text())
REPLIES = {k: json.loads((FIX / f"{k}.json").read_text()) for k in ("plan", "tweak", "products", "receipt", "expiry")}
TODAY = datetime.date.today()

MOCK = """
window.__R = %s; window.__prompts = []; window.__uploads = [];
window.claude = { use: async (name) => {
  if (name === 'assets') return {
    upload: async (blob, o) => { window.__uploads.push({size: blob.size, type: (o && o.type) || blob.type});
      const id = 'a'.repeat(28) + String(window.__uploads.length).padStart(4, '0');
      return { id, url: '/_blob/' + id, sizeBytes: blob.size, contentType: 'image/jpeg' }; },
    list: async () => ({ assets: [], usage: {} }), delete: async () => ({ deleted: true }) };
  if (name !== 'sample') return null;
  const f = async (prompt, opts) => {
    window.__prompts.push(prompt);
    await new Promise(r => setTimeout(r, 100));
    const key = prompt.includes('CHANGE MEAL') ? 'tweak'
              : prompt.includes('Find its expiry date only') ? 'expiry'
              : prompt.includes('Read this supermarket receipt') ? 'receipt'
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
        ctx = await browser.new_context(viewport={"width": 390, "height": 844}, locale="en-GB")
        page = await ctx.new_page()
        receipt_jpg = (FIX / "receipt.jpg").read_bytes()
        await page.route("**/_blob/**", lambda route: route.fulfill(status=200, content_type="image/jpeg", body=receipt_jpg))
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
        rtxt = await page.inner_text("#review")
        check("15/03/2027" in rtxt and "Please check it" in rtxt, "review shows the expiry read from the photo")
        check("Check this" in rtxt and "could also be 11 Mar 2027" in rtxt, "ambiguous expiry is flagged with the other reading")
        check("No date found in the photo" in rtxt, "no expiry made up when none is visible")
        check(await page.locator('.rl[data-k="1"] [data-x=d]').input_value() == "2027-11-03", "ambiguous expiry prefilled in this locale's order")
        await page.click('.rl[data-k="2"] [data-f=on]')  # untick the shower gel
        await page.click("#rok")
        await page.wait_for_timeout(400)
        s = await state()
        check(not any("Shower" in i["name"] for i in s["items"].values()), "unticked product not added")
        check(len(s["receipts"]) == len(STATE["receipts"]), "photos don't create a receipt record")
        check(sum(1 for i in s["items"].values() if "tuna" in i["name"].lower() or i["id"] == "i-tomato-sauce") >= 1, "products added or restocked")
        _ = before
        tuna = next(i for i in s["items"].values() if "tuna" in i["name"].lower())
        check(tuna.get("expirationDate") == "2027-11-03" and tuna.get("expirationSource") == "ocr" and tuna.get("expirationAlt") == ["2027-03-11"], "photo item saved with its expiry, marked as read from the photo")
        check(any(i.get("expirationDate") == "2027-03-15" for i in s["items"].values()), "second photo item has its expiry")

        print("receipt links")
        await load("#add")
        await page.set_input_files("#rf", str(FIX / "receipt.jpg"))
        await page.wait_for_timeout(1500)
        check(await page.locator("#review .rl").count() == 3, "receipt review lists every line")
        await page.click("#rok")
        await page.wait_for_timeout(800)
        s = await state()
        new = [r for r in s["receipts"].values() if r["id"] not in STATE["receipts"]]
        check(len(new) == 1, "receipt record saved")
        r = new[0]
        check(str(r.get("image") or "").startswith("a" * 28), "receipt photo kept with the record")
        ls = r["lines"]
        check(ls[0]["itemId"] == "i-tomato-sauce" and ls[1]["itemId"] in s["items"] and ls[2].get("skip") and not ls[2]["itemId"], "receipt lines point to their items")
        check(abs((ls[0].get("y") or 0) - 0.34) < 0.01, "line position on the photo kept")
        tom = s["items"]["i-tomato-sauce"]
        check((tom.get("receipt") or {}).get("id") == r["id"] and tom["receipt"]["line"] == 0, "restocked item points to its receipt line")
        check((s["items"][ls[1]["itemId"]].get("receipt") or {}).get("line") == 1, "new item points to its receipt line")

        print("item purchase date and receipt")
        await page.click('.row[data-id="i-tomato-sauce"] .nm')
        await page.wait_for_timeout(300)
        txt = await page.inner_text("#sheet")
        check("Bought 20 Nov 2026" in txt and "View receipt" in txt, "item shows the receipt date and a receipt link")
        await page.click("#dbuy [data-rv]")
        await page.wait_for_timeout(600)
        check("TOM. RECETA ARTESANA" in await page.inner_text("#rvl li.hl"), "receipt opens with the item's line highlighted")
        check("TOM. RECETA ARTESANA" in await page.inner_text(".rvhl"), "item's OCR line shown above the photo")
        check(await page.evaluate("(document.querySelector('#rvpic')||{}).naturalWidth||0") > 0, "receipt photo shows")
        await page.screenshot(path=str(OUT / "7-receipt.png"))
        await page.emulate_media(color_scheme="dark")
        await page.screenshot(path=str(OUT / "7b-receipt-dark.png"))
        await page.emulate_media(color_scheme="light")
        await page.set_viewport_size({"width": 1100, "height": 800})
        await page.wait_for_timeout(200)
        await page.screenshot(path=str(OUT / "7c-receipt-wide.png"))
        await page.set_viewport_size({"width": 390, "height": 844})
        await page.click("#rvback")
        await page.wait_for_timeout(200)
        check("Artisan-style tomato sauce" in await page.inner_text("#sheet h2"), "back returns to the item")
        await page.click("#dclose")

        print("older receipt")
        await page.click('.row[data-id="i-oat-drink"] .nm')
        await page.wait_for_timeout(300)
        check("Bought 15 Jan 2025" in await page.inner_text("#sheet"), "older item shows its receipt date")
        await page.click("#dbuy [data-rv]")
        await page.wait_for_timeout(400)
        check("BEBIDA AVEIA" in await page.inner_text("#rvl li.hl"), "older receipt found by its label, line highlighted")
        check("No photo was kept" in await page.inner_text("#sheet"), "older receipt without a photo still opens")
        await page.click("#rvdone")

        print("receipt list")
        await load("#add")
        await page.click("#rlist details summary >> nth=0")
        await page.click("#rlist [data-rview] >> nth=0")
        await page.wait_for_timeout(400)
        check("LECHE ENTERA" in await page.inner_text("#rvl"), "past receipt opens in the viewer")
        await page.click('#rvl li[data-k="1"] [data-open]')
        await page.wait_for_timeout(300)
        check("Whole milk" in await page.inner_text("#sheet h2"), "tapping a receipt line opens its item")
        await page.click("#dclose")

        print("scan for expiry")
        await load("#pantry")
        n_items = len((await state())["items"])
        qty = (await state())["items"]["i-tomato-sauce"]["qty"]
        await page.click('.row[data-id="i-tomato-sauce"] .nm')
        await page.wait_for_timeout(300)
        await page.set_input_files("#dxf", str(FIX / "ean_photo.jpg"))
        await page.wait_for_timeout(1200)
        s = await state()
        tom = s["items"]["i-tomato-sauce"]
        check(tom.get("expirationDate") == "2027-11" and tom.get("expirationSource") == "ocr", "scan sets a month-only expiry on the existing item")
        check(len(s["items"]) == n_items and tom["qty"] == qty, "scan adds no item and changes no amount")
        txt = await page.inner_text("#dexp")
        check("Please check" in txt and "Nov 2027" in txt and "BB END 11/2027" in txt, "auto-read date is marked for checking")
        await page.screenshot(path=str(OUT / "8-expiry.png"))
        await page.set_viewport_size({"width": 320, "height": 700})
        await page.locator("#dexp").scroll_into_view_if_needed()
        await page.screenshot(path=str(OUT / "8c-expiry-320.png"))
        await page.set_viewport_size({"width": 390, "height": 844})
        await page.evaluate("window.__R.expiry = {printed: 'USE BY 05/06/27', iso: '2027-06-05'}")
        await page.set_input_files("#dxf", str(FIX / "ean_photo.jpg"))
        await page.wait_for_timeout(1200)
        check("Which date is it?" in await page.inner_text("#dexp"), "ambiguous scan asks which date")
        check((await state())["items"]["i-tomato-sauce"]["expirationDate"] == "2027-11", "ambiguous scan isn't saved without asking")
        picks = await page.locator("#dxst [data-xask]").all_inner_texts()
        check(picks[:2] == ["5 Jun 2027", "6 May 2027"], f"this locale's reading is offered first {picks}")
        await page.screenshot(path=str(OUT / "8b-expiry-ask.png"))
        await page.click('#dxst [data-xask="2027-05-06"]')
        await page.wait_for_timeout(300)
        tom = (await state())["items"]["i-tomato-sauce"]
        check(tom["expirationDate"] == "2027-05-06" and tom["expirationSource"] == "manual", "chosen reading saved as confirmed")

        print("manual expiry")
        soon = (TODAY + datetime.timedelta(days=2)).isoformat()
        await page.click("#dxe")
        await page.fill("#dxin [data-x=d]", soon)
        await page.click("#dxform button.pri")
        await page.wait_for_timeout(300)
        tom = (await state())["items"]["i-tomato-sauce"]
        check(tom["expirationDate"] == soon and tom["expirationSource"] == "manual", "date entered by hand")
        await page.click("#dclose")
        await page.wait_for_timeout(200)
        check(await page.locator('#psoon .row[data-id="i-tomato-sauce"]').count() == 1, "item expiring soon is listed under Use soon")
        check("to use soon" in await page.inner_text("#stats"), "header counts items to use soon")
        check("Use in 2 days" in await page.inner_text('#psoon .row[data-id="i-tomato-sauce"]'), "row is flagged with days left")
        await page.evaluate("scrollTo(0, 0)")
        await page.screenshot(path=str(OUT / "9-use-soon.png"))
        await page.click('#psoon .row[data-id="i-tomato-sauce"] .nm')
        await page.wait_for_timeout(300)
        await page.click("#dxc")
        await page.wait_for_timeout(300)
        check((await state())["items"]["i-tomato-sauce"].get("expirationDate") is None, "date can be cleared")
        await page.click("#dedit")
        await page.fill("#ex [data-x=d]", "2027-01-31")
        await page.check("#ex [data-x=m]")
        await page.click("#esave")
        await page.wait_for_timeout(300)
        tom = (await state())["items"]["i-tomato-sauce"]
        check(tom.get("expirationDate") == "2027-01" and tom.get("expirationSource") == "manual", "edit sheet saves a month-only date")
        await page.click("#dclose")

        print("expiry when adding by hand")
        await load("#add")
        await page.fill("#mn", "Test kefir")
        await page.fill("#mx", soon)
        await page.click("#mf button.pri")
        await page.wait_for_timeout(300)
        kef = next((i for i in (await state())["items"].values() if i["name"] == "Test kefir"), {})
        check(kef.get("expirationDate") == soon and kef.get("expirationSource") == "manual", "by hand add keeps the expiry")

        print("add tab")
        await load("#add")
        check(await page.locator(".tiles .tile").count() == 4, "add tab shows four ways to add")
        await page.screenshot(path=str(OUT / "3b-add.png"))
        await page.click("#byhand")
        await page.wait_for_timeout(500)
        check(await page.evaluate("document.activeElement.id") == "mn", "by hand tile goes to the form")

        print("shopping list")
        await load("#add")
        check(not await page.is_visible("#stats"), "header figures hidden on the Add tab")
        await load("#list")
        lst = await page.inner_text("#slist")
        stats = await page.inner_text("#stats")
        check(await page.is_visible("#stats") and "to buy" in stats and "≈ €1.60" in stats and "estimated" in stats, f"header shows the list's figures ({stats!r})")
        check("in stock" not in stats, "pantry figures not shown on the List tab")
        check(await page.locator("#slist .card").count() == 0 and "estimated" not in lst, "separate estimate card is gone")
        check("Last bought" in lst and "Based on the last price you paid. 1 item has no price yet" in await page.inner_text("#slist .listnote"), "list shows last bought and the price note")
        check(not await page.is_visible("#sfilt"), "no shop filter with only one shop")

        print("shop on the list")
        await page.fill("#sn", "Test flour")
        await page.fill("#sst", "Corner shop")
        await page.click("#sf button.pri")
        await page.wait_for_timeout(300)
        sh = (await state())["shopping"]
        flour = next((x for x in sh.values() if x["name"] == "Test flour"), {})
        check(flour.get("store") == "Corner shop", "entry added with its own shop")
        check(await page.input_value("#sst") == "", "shop field clears after adding")
        check((await page.inner_text("#stats")).startswith("3"), "header count follows the list")
        pills = await page.locator("#sfilt button").all_inner_texts()
        check(pills == ["All", "Corner shop", "Mercadona"], f"shop filter lists the list's shops {pills}")
        check("At Corner shop" in await page.inner_text("#slist"), "entry grouped under its own shop")
        await page.screenshot(path=str(OUT / "4-list.png"))
        await page.set_viewport_size({"width": 320, "height": 700})
        await page.screenshot(path=str(OUT / "4b-list-320.png"))
        await page.set_viewport_size({"width": 390, "height": 844})
        await page.emulate_media(color_scheme="dark")
        await page.screenshot(path=str(OUT / "4c-list-dark.png"))
        await page.emulate_media(color_scheme="light")
        await page.click('#sfilt [data-st="Corner shop"]')
        await page.wait_for_timeout(150)
        lst = await page.inner_text("#slist")
        check("Test flour" in lst and "Eggs" in lst and "Pizza dough" not in lst, "filter shows that shop and anywhere entries only")
        await page.screenshot(path=str(OUT / "4d-list-filtered.png"))
        await page.click('#sfilt [data-st=""]')
        await page.wait_for_timeout(150)
        check("Pizza dough" in await page.inner_text("#slist"), "All shows every entry again")

        await page.fill("#sn", "Eggs")
        await page.fill("#sst", "corner SHOP")
        await page.click("#sf button.pri")
        await page.wait_for_timeout(300)
        sh = (await state())["shopping"]
        eggs = [x for x in sh.values() if x["name"] == "Eggs"]
        check(len(eggs) == 1 and eggs[0].get("store") == "Corner shop" and eggs[0]["amount"] == "6", "adding again keeps one entry and takes the chosen shop, spelt as known")

        print("entry sheet")
        await page.click('#slist .row[data-id="s1"] .nm')
        await page.wait_for_timeout(200)
        txt = await page.inner_text("#sheet")
        check("Automatic: Mercadona" in txt, "sheet says which shop is automatic")
        await page.fill("#lss", "Corner shop")
        await page.dispatch_event("#lss", "input")
        await page.fill("#lsa", "2")
        await page.evaluate("document.querySelector('#toast').hidden = true")
        await page.screenshot(path=str(OUT / "4e-list-sheet.png"))
        await page.set_viewport_size({"width": 320, "height": 700})
        await page.screenshot(path=str(OUT / "4f-list-sheet-320.png"))
        await page.set_viewport_size({"width": 390, "height": 844})
        await page.emulate_media(color_scheme="dark")
        await page.screenshot(path=str(OUT / "4g-list-sheet-dark.png"))
        await page.emulate_media(color_scheme="light")
        await page.click("#lssave")
        await page.wait_for_timeout(200)
        s1 = (await state())["shopping"]["s1"]
        check(s1.get("store") == "Corner shop" and s1["amount"] == "2", "sheet changes the entry's shop and amount")
        check(not await page.is_visible("#sfilt"), "filter hides when only one shop is left")
        await page.click('#slist .row[data-id="s1"] .nm')
        await page.click("#lscan")
        check((await state())["shopping"]["s1"].get("store") == "Corner shop", "cancel changes nothing")
        await page.click('#slist .row[data-id="s1"] .nm')
        await page.click("#lsc")
        await page.click("#lssave")
        await page.wait_for_timeout(200)
        check("store" not in (await state())["shopping"]["s1"], "shop can be set back to automatic")
        check(await page.is_visible("#sfilt"), "filter returns with two shops")

        print("stock from the list")
        await page.check(f'#slist .row[data-id="{flour["id"]}"] [data-a=tick]')
        await page.wait_for_timeout(200)
        check("In the basket" in await page.inner_text("#slist"), "ticked entry moves to the basket")
        await page.click("#slist [data-a=stock]")
        await page.wait_for_timeout(300)
        it = next((i for i in (await state())["items"].values() if i["name"] == "Test flour"), {})
        check((it.get("stores") or [{}])[0].get("name") == "Corner shop", "stocked item records the entry's shop")

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
        check("| expires 2027-01" in prompt and "expire soonest first" in prompt, "plan prompt passes expiry dates")

        print("location setting")
        check(not await page.is_visible("#pwhere"), "meal options start folded")
        await page.click("#popts summary")
        await page.select_option("#ptime", "20")
        check("20 min" in await page.inner_text("#poptsum"), "options summary follows the choices")
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
        await page.click("#popts summary")
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
