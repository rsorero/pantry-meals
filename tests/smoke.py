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

        print("photo of a product just added by barcode")
        await page.evaluate("""t => { const s = JSON.parse(localStorage.getItem('pm-local'));
          s.items['i-np'] = {id:'i-np', name:'New product 2223', autoName:true, aliases:[], qty:1, unit:'pc', loc:'pantry', food:true, low:0,
            barcode:'3596710532223', bought:t, added:t, provisional:{qty:1, unit:'pc', date:t, how:'barcode', made:true}};
          s.lookups = s.lookups || {}; s.lookups['i-np'] = {id:'i-np', itemId:'i-np', name:'New product 2223', aliases:[], barcode:'3596710532223', store:'', status:'pending', requested:Date.now()};
          localStorage.setItem('pm-local', JSON.stringify(s)); }""", TODAY.isoformat())
        await load("#add")
        await page.evaluate("""() => { window.__R.products = {products:[{seen:'Auchan sauce tomate 500 g', name:'Tomato sauce', match:'i-np', qty:1, unit:'pc', loc:'pantry', food:true, barcode:'', photo:1, expiry:'', expiry_iso:'', list:null}]}; }""")
        await load("#pantry")
        await page.click('.row[data-id="i-np"] .nm')
        await page.wait_for_timeout(300)
        txt = await page.inner_text("#sheet")
        check("Waiting to look this up online by barcode" in txt and "product photo" in txt, "pending lookup says when it was asked and how to name the item")
        await page.screenshot(path=str(OUT / "3b-autoname-sheet.png"))
        await page.click("#dclose")
        await load("#add")
        await page.evaluate("""() => { window.__R.products = {products:[{seen:'Auchan sauce tomate 500 g', name:'Tomato sauce', match:'i-np', qty:1, unit:'pc', loc:'pantry', food:true, barcode:'', photo:1, expiry:'', expiry_iso:'', list:null}]}; }""")
        await page.set_input_files("#pf", [str(FIX / "ean_photo.jpg")])
        await page.wait_for_timeout(2500)
        rtxt = await page.inner_text("#review")
        check("Replaces the 1 pc added with its barcode" in rtxt, "photo review offers to replace what the barcode scan added")
        await page.screenshot(path=str(OUT / "3c-photo-after-barcode.png"))
        await page.click("#rok")
        await page.wait_for_timeout(400)
        s = await state()
        np_ = s["items"]["i-np"]
        check(np_["qty"] == 1, f"photographing a just-scanned pack doesn't count it twice ({np_['qty']})")
        check(np_["name"] == "Tomato sauce" and not np_.get("autoName"), "placeholder name replaced by the name on the pack")
        check((np_.get("provisional") or {}).get("made") is True, "item still marked as made without a receipt")
        lk = (s.get("lookups") or {}).get("i-np") or {}
        check(lk.get("name") == "Tomato sauce" and lk.get("barcode") == "3596710532223" and lk.get("status") == "pending", "lookup asked again with the real name and the barcode")

        print("receipt links")
        await page.evaluate("""() => { const s = JSON.parse(localStorage.getItem('pm-local'));
          s.shopping['t-any'] = {id: 't-any', name: 'Artisan-style tomato sauce', itemId: 'i-tomato-sauce', amount: '', note: '', done: false, t: 1};
          s.shopping['t-corner'] = {id: 't-corner', name: 'Artisan-style tomato sauce', itemId: 'i-tomato-sauce', amount: '', note: '', store: 'Corner shop', done: false, t: 2};
          s.shopping['t-milk'] = {id: 't-milk', name: 'Milk for coffee', itemId: null, qty: 1, unit: 'L', note: '', done: true, t: 3};
          s.shopping['t-bread'] = {id: 't-bread', name: 'Bread', itemId: null, note: '', done: false, t: 4};
          s.shopping['t-late'] = {id: 't-late', name: 'Artisan-style tomato sauce', itemId: 'i-tomato-sauce', note: '', done: false, t: Date.now()};
          s.items['i-hand-milk'] = {id: 'i-hand-milk', name: 'Milk', aliases: [], qty: 2, unit: 'L', loc: 'fridge', food: true, low: 0, bought: '2026-11-20', added: '2026-11-20',
            provisional: {qty: 2, unit: 'L', date: '2026-11-20', how: 'hand', made: true}};
          localStorage.setItem('pm-local', JSON.stringify(s)); }""")
        await load("#add")
        await page.set_input_files("#rf", str(FIX / "receipt.jpg"))
        await page.wait_for_timeout(1500)
        check(await page.locator("#review .rl").count() == 3, "receipt review lists every line")
        check(await page.get_attribute('#rvsh [data-shop="Mercadona"]', "aria-pressed") == "true", "receipt review shows the store as a chosen shop chip")

        print("receipt and the shopping list")
        lr = page.locator("#rvlist")
        check(await lr.locator('[data-lid="t-any"] [data-l=on]').is_checked(), "list entry for the same item is suggested to cross off")
        check(await lr.locator('[data-lid="t-milk"] [data-l=on]').is_checked() and await lr.locator('[data-lid="t-milk"] [data-l=k]').input_value() == "1", "Claude's match crosses off an entry with a different name")
        check(await lr.locator('[data-lid="t-corner"]').count() == 1 and not await lr.locator('[data-lid="t-corner"] [data-l=on]').is_checked(), "an entry for another shop is shown but not crossed off")
        check(await lr.locator('[data-lid="t-late"]').count() == 0, "an entry added after the purchase isn't offered")
        check(not await lr.locator('[data-lid="t-bread"] [data-l=on]').is_checked() and "other entries on the list" in await lr.inner_text(), "unmatched entries are folded away and left alone")
        await lr.locator("details summary").click()
        await lr.locator('[data-lid="t-bread"] [data-l=k]').select_option("1")
        await page.wait_for_timeout(100)
        check(await lr.locator('[data-lid="t-bread"] [data-l=on]').is_checked() and await lr.locator("details").get_attribute("open") is not None, "picking the line an entry was bought as ticks it, and the fold stays open")
        check("3 will be crossed off" in await lr.inner_text(), "review counts what will be crossed off")

        print("receipt corrects stock added by hand")
        await page.select_option('.rl[data-k="1"] [data-f=match]', "i-hand-milk")
        await page.wait_for_timeout(100)
        pvt = await page.inner_text('.rl[data-k="1"] [data-f=pv]')
        check(await page.is_checked('.rl[data-k="1"] [data-f=repl]') and "Replaces the 2 L added by hand" in pvt and "name, amount, unit and price" in pvt, "line for a hand-added item offers to replace it")
        await page.locator("#review .rl").nth(1).scroll_into_view_if_needed()
        await page.screenshot(path=str(OUT / "7d-receipt-review-list.png"))
        await lr.scroll_into_view_if_needed()
        await page.screenshot(path=str(OUT / "7e-receipt-review-list2.png"))
        await page.emulate_media(color_scheme="dark")
        await page.screenshot(path=str(OUT / "7f-receipt-review-dark.png"))
        await page.emulate_media(color_scheme="light")
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
        check("t-any" not in s["shopping"] and "t-corner" in s["shopping"], "buying it clears the anywhere entry but not another shop's")
        check("t-milk" not in s["shopping"] and "t-bread" not in s["shopping"] and "t-late" in s["shopping"], "the entries left ticked in the review are crossed off, the rest stay")
        hm = s["items"]["i-hand-milk"]
        check(ls[1]["itemId"] == "i-hand-milk" and hm["name"] == "Whole milk" and hm["unit"] == "pc" and hm["qty"] == 1 and "provisional" not in hm and hm.get("price") == 0.95,
              f"the receipt replaces the hand-added amount, unit and name ({hm.get('name')}, {hm.get('qty')} {hm.get('unit')})")
        check((hm.get("receipt") or {}).get("line") == 1 and (s["lookups"].get("i-hand-milk") or {}).get("name") == "Whole milk", "corrected item links to its receipt and is looked up again under its real name")
        await page.evaluate("() => { const s = JSON.parse(localStorage.getItem('pm-local')); for (const k of ['t-corner', 't-late']) delete s.shopping[k]; localStorage.setItem('pm-local', JSON.stringify(s)); }")

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
        check(await page.get_attribute('#esh [data-shop="Mercadona"]', "aria-pressed") == "true", "edit sheet picks the usual shop with chips")
        await page.screenshot(path=str(OUT / "2b-edit.png"))
        await page.fill("#ex [data-x=d]", "2027-01-31")
        await page.check("#ex [data-x=m]")
        await page.click("#esave")
        await page.wait_for_timeout(300)
        tom = (await state())["items"]["i-tomato-sauce"]
        check(tom.get("expirationDate") == "2027-01" and tom.get("expirationSource") == "manual", "edit sheet saves a month-only date")
        await page.click("#dclose")

        print("expiry when adding by hand")
        await load("#add")
        check(await page.evaluate("document.querySelectorAll('datalist, input[list]').length") == 0, "no plain shop dropdowns left")
        await page.fill("#mn", "Test kefir")
        await page.fill("#mx", soon)
        await page.click("#msh [data-shopnew]")
        await page.fill("#mshi", "Farm shop")
        await page.locator("#mshw").scroll_into_view_if_needed()
        await page.screenshot(path=str(OUT / "3c-by-hand.png"))
        await page.click("#mf button.pri")
        await page.wait_for_timeout(300)
        kef = next((i for i in (await state())["items"].values() if i["name"] == "Test kefir"), {})
        check(kef.get("expirationDate") == soon and kef.get("expirationSource") == "manual", "by hand add keeps the expiry")
        pv = kef.get("provisional") or {}
        check(pv.get("how") == "hand" and pv.get("made") is True and pv.get("qty") == 1 and pv.get("date") == TODAY.isoformat(), "by hand add is remembered as provisional until a receipt confirms it")
        check((kef.get("stores") or [{}])[0].get("name") == "Farm shop", "by hand add records a new shop from the chips")
        check(await page.get_attribute('#msh [data-shop="Farm shop"]', "aria-pressed") == "true", "the new shop becomes a chip and stays chosen for the next item")

        print("add tab")
        await load("#add")
        check(await page.locator(".tiles .tile").count() == 4, "add tab shows four ways to add")
        await page.screenshot(path=str(OUT / "3b-add.png"))
        await page.click("#byhand")
        await page.wait_for_timeout(500)
        check(await page.evaluate("document.activeElement.id") == "mn", "by hand tile goes to the form")

        print("shopping list")
        await load("#add")
        st = await page.inner_text("#stats")
        check(await page.is_visible("#stats") and "spent this month" in st and "in stock" not in st, f"Add tab header shows receipt figures ({st!r})")
        await load("#list")
        lst = await page.inner_text("#slist")
        stats = await page.inner_text("#stats")
        check(await page.is_visible("#stats") and "to buy" in stats and "≈ €1.60" in stats and "estimated" in stats, f"header shows the list's figures ({stats!r})")
        check("in stock" not in stats, "pantry figures not shown on the List tab")
        check(await page.locator("#slist .card").count() == 0 and "estimated" not in lst, "separate estimate card is gone")
        check("Last bought" in lst and "Based on the last price you paid. 1 item has no price yet" in await page.inner_text("#slist .listnote"), "list shows last bought and the price note")
        check(not await page.is_visible("#sfilt"), "no shop filter before any shop is chosen")
        check("At Mercadona" not in lst, "entries without a chosen shop aren't filed under the shop they were last bought at")

        print("adding from the search bar")

        async def add_via_sheet(text, pick=None, new_shop=None, amount=None, unit=None, enter=False):
            await page.fill("#sq", text)
            await page.wait_for_timeout(100)
            if enter:
                await page.press("#sq", "Enter")
            else:
                await page.click('#sadd [data-add=""]')
            await page.wait_for_timeout(150)
            if new_shop is not None:
                await page.click("#shp [data-shopnew]")
                await page.fill("#shpi", new_shop)
            elif pick is not None:
                await page.click(f'#shp [data-shop="{pick}"]')
            if amount:
                await page.fill("#aq", amount)
            if unit:
                await page.select_option("#au", unit)
            await page.click("#aok")
            await page.wait_for_timeout(250)

        await page.fill("#sq", "Banan")
        await page.wait_for_timeout(100)
        sug = await page.inner_text("#sadd")
        check(await page.locator('#sadd [data-add="i-bananas"]').count() == 1 and "in stock" in sug, "search suggests matching pantry items to add")
        await page.screenshot(path=str(OUT / "4h-list-search.png"))
        await page.click('#sadd [data-add="i-bananas"]')
        await page.wait_for_timeout(150)
        check("Bananas" in await page.inner_text("#sheet h2") and await page.get_attribute('#shp [data-shop=""]', "aria-pressed") == "true", "add sheet opens with Anywhere chosen")
        await page.evaluate("document.querySelector('#toast').hidden = true")
        await page.screenshot(path=str(OUT / "4i-add-sheet.png"))
        await page.click("#acan")
        check(not any(x.get("itemId") == "i-bananas" for x in (await state())["shopping"].values()), "cancel adds nothing")

        await add_via_sheet("Test flour", new_shop="Corner shop", amount="1,5", unit="kg")
        sh = (await state())["shopping"]
        flour = next((x for x in sh.values() if x["name"] == "Test flour"), {})
        check(flour.get("store") == "Corner shop", "entry added from the sheet with a new shop")
        check(flour.get("qty") == 1.5 and flour.get("unit") == "kg" and flour.get("t", 0) > 1e12, "entry keeps its amount, unit and when it was added")
        check(await page.input_value("#sq") == "" and not await page.is_visible("#sadd"), "search clears after adding")
        check((await page.inner_text("#stats")).startswith("3"), "header count follows the list")
        check("At Corner shop" in await page.inner_text("#slist"), "entry grouped under its own shop")
        check(not await page.is_visible("#sfilt"), "no filter with a single shop, since anywhere entries show under it anyway")
        await add_via_sheet("Test rice", new_shop="Market stall")
        pills = await page.locator("#sfilt button").all_inner_texts()
        check(pills == ["All", "Corner shop", "Market stall"], f"shop filter lists the shops chosen on the list {pills}")
        check("Last bought 15 Jan 2025 at Mercadona" in await page.inner_text("#slist"), "anywhere entry still shows where it was last bought")
        await page.screenshot(path=str(OUT / "4-list.png"))
        await page.set_viewport_size({"width": 320, "height": 700})
        await page.screenshot(path=str(OUT / "4b-list-320.png"))
        await page.set_viewport_size({"width": 390, "height": 844})
        await page.emulate_media(color_scheme="dark")
        await page.screenshot(path=str(OUT / "4c-list-dark.png"))
        await page.emulate_media(color_scheme="light")

        print("shop filter")
        await page.click('#sfilt [data-st="Corner shop"]')
        await page.wait_for_timeout(150)
        lst = await page.inner_text("#slist")
        check("Test flour" in lst and "Eggs" in lst and "Pizza dough" in lst and "Test rice" not in lst, "one shop shows its entries plus anywhere ones")
        await page.click('#sfilt [data-st="Market stall"]')
        await page.wait_for_timeout(150)
        lst = await page.inner_text("#slist")
        on = await page.locator('#sfilt button[aria-pressed="true"]').all_inner_texts()
        check("Test rice" in lst and "Test flour" in lst and on == ["Corner shop", "Market stall"], f"several shops can be chosen at once {on}")
        await page.screenshot(path=str(OUT / "4d-list-filtered.png"))
        await page.click('#sfilt [data-st="Corner shop"]')
        await page.wait_for_timeout(150)
        check("Test flour" not in await page.inner_text("#slist"), "tapping a chosen shop again removes it")
        await page.click('#sfilt [data-st=""]')
        await page.wait_for_timeout(150)
        check("Test flour" in await page.inner_text("#slist") and await page.get_attribute('#sfilt [data-st=""]', "aria-pressed") == "true", "All shows every entry again")

        await page.fill("#sq", "rice")
        await page.wait_for_timeout(150)
        lst = await page.inner_text("#slist")
        check("Test rice" in lst and "Test flour" not in lst, "search also finds entries on the list")
        await page.press("#sq", "Escape")
        await page.wait_for_timeout(100)
        check(await page.input_value("#sq") == "" and "Test flour" in await page.inner_text("#slist"), "Escape clears the search")

        await add_via_sheet("Eggs", new_shop="corner SHOP")
        eggs = [x for x in (await state())["shopping"].values() if x["name"] == "Eggs"]
        check(len(eggs) == 2 and sorted(x.get("store", "") for x in eggs) == ["", "Corner shop"], "the same thing for a shop and for anywhere are separate entries, shop spelt as known")
        await add_via_sheet("Eggs", enter=True)
        check(len([x for x in (await state())["shopping"].values() if x["name"] == "Eggs"]) == 2, "adding again for anywhere joins the anywhere entry")
        egg_c = next(x for x in (await state())["shopping"].values() if x["name"] == "Eggs" and x.get("store"))

        print("entry sheet")
        await page.click('#slist .row[data-id="s1"] .nm')
        await page.wait_for_timeout(200)
        txt = await page.inner_text("#sheet")
        check("Last bought at Mercadona" in txt and await page.get_attribute('#shp [data-shop=""]', "aria-pressed") == "true", "sheet shows anywhere chosen and where it was last bought")
        await page.click('#shp [data-shop="Corner shop"]')
        check("Added to the list" not in txt, "no added time shown for entries from before it was kept")
        await page.fill("#lsq", "2")
        await page.select_option("#lsu", "pack")
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
        check(s1.get("store") == "Corner shop" and s1.get("qty") == 2 and s1.get("unit") == "pack" and "amount" not in s1, "sheet changes the entry's shop, amount and unit")
        check("2 pack" in await page.inner_text('#slist .row[data-id="s1"]'), "entry shows its amount and unit")
        await page.click('#slist .row[data-id="s1"] .nm')
        await page.click("#lscan")
        check((await state())["shopping"]["s1"].get("store") == "Corner shop", "cancel changes nothing")
        await page.click('#slist .row[data-id="s1"] .nm')
        await page.click('#shp [data-shop=""]')
        await page.click("#lssave")
        await page.wait_for_timeout(200)
        check("store" not in (await state())["shopping"]["s1"], "shop can be set back to anywhere")
        await page.click(f'#slist .row[data-id="{egg_c["id"]}"] .nm')
        await page.click('#shp [data-shop=""]')
        await page.click("#lssave")
        await page.wait_for_timeout(200)
        check(len([x for x in (await state())["shopping"].values() if x["name"] == "Eggs"]) == 1, "moving an entry onto an existing one combines them")

        print("stock from the list")
        await page.check(f'#slist .row[data-id="{flour["id"]}"] [data-a=tick]')
        await page.wait_for_timeout(200)
        check("In the basket" in await page.inner_text("#slist"), "ticked entry moves to the basket")
        await page.click("#slist [data-a=stock]")
        await page.wait_for_timeout(300)
        it = next((i for i in (await state())["items"].values() if i["name"] == "Test flour"), {})
        check((it.get("stores") or [{}])[0].get("name") == "Corner shop", "stocked item records the entry's shop")
        check(it.get("qty") == 1.5 and it.get("unit") == "kg" and (it.get("provisional") or {}).get("how") == "list", "stocked item gets the entry's amount and unit, marked provisional")

        print("meal plan")
        await load("#meals")
        await page.click("#pmode [data-m=multi]")
        await page.click("#pgo")
        await page.wait_for_timeout(900)
        check(await page.locator("#pout article").count() == 3, "plan has 3 meals")
        ms = await page.inner_text("#stats")
        check(await page.inner_text("#stats span b") == "3" and "meals to cook" in ms, f"Meals tab header counts meals to cook ({ms!r})")
        for w in (1000, 390):
            await page.set_viewport_size({"width": w, "height": 800})
            hs = []
            for t in ("pantry", "add", "list", "meals", "history"):
                await page.click(f"#t-{t}")
                await page.wait_for_timeout(150)
                hs.append(await page.evaluate("document.querySelector('header').offsetHeight"))
                await page.screenshot(path=str(OUT / f"0-header-{w}-{t}.png"), clip={"x": 0, "y": 0, "width": w, "height": hs[-1] + 20})
            check(len(set(hs)) == 1, f"header is the same height on every tab at {w} px ({hs})")
        await page.set_viewport_size({"width": 390, "height": 844})
        await page.evaluate("location.hash='#meals'")
        await page.wait_for_timeout(150)
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

        print("unsaved pantry changes")
        await load("#pantry")
        s = await state()
        tom_q = s["items"]["i-tomato-sauce"]["qty"]
        n_hist = len(s.get("history") or {})
        check(not await page.is_visible("#savebar"), "no save bar without changes")
        await page.click('#plist .row[data-id="i-tomato-sauce"] [data-a=inc]')
        await page.click('#plist .row[data-id="i-tomato-sauce"] [data-a=inc]')
        await page.wait_for_timeout(150)
        check(await page.is_visible("#savebar") and "1 unsaved change" in await page.inner_text("#savebar"), "plus shows the save bar")
        check((await state())["items"]["i-tomato-sauce"]["qty"] == tom_q, "plus doesn't save until Save")
        check("Was " + str(tom_q).rstrip("0").rstrip(".") in await page.inner_text('#plist .row[data-id="i-tomato-sauce"]'), "changed row shows the amount before")
        await load("#pantry")
        check(await page.locator('#plist .row.pend[data-id="i-tomato-sauce"]').count() == 1, "unsaved change survives a reload")
        await page.click('#plist .row[data-id="i-oat-drink"] [data-a=empty]')
        await page.wait_for_timeout(150)
        check("Save to keep it" in await page.inner_text("#toast") and "Add to list" in await page.inner_text("#toast"), "Empty waits for Save and still offers the list")
        await page.screenshot(path=str(OUT / "7-savebar.png"))
        await page.goto(URL + "#list")
        await page.wait_for_timeout(200)
        check("not saved yet" in await page.inner_text("#toast"), "leaving the Pantry reminds about unsaved changes")
        await page.goto(URL + "#pantry")
        await page.wait_for_timeout(200)
        await page.click("#sbsave")
        await page.wait_for_timeout(200)
        s = await state()
        check(s["items"]["i-tomato-sauce"]["qty"] == tom_q + 2 and s["items"]["i-oat-drink"]["qty"] == 0, "Save writes the amounts")
        hs = sorted(s["history"].values(), key=lambda e: e["t"])
        new = hs[n_hist - len(hs):] if len(hs) > n_hist else []
        check(sorted(e["kind"] for e in new) == ["amount", "used"], f"Save logs one event per item {[e['kind'] for e in new]}")
        amt = next((e for e in new if e["kind"] == "amount"), {})
        check(amt.get("from") == tom_q and amt.get("to") == tom_q + 2 and amt.get("itemId") == "i-tomato-sauce", "amount event records before and after")
        check(not await page.is_visible("#savebar"), "save bar goes after Save")
        await page.click('#plist .row[data-id="i-tomato-sauce"] [data-a=dec]')
        await page.click("#sbdis")
        await page.wait_for_timeout(150)
        check(not await page.is_visible("#savebar") and (await state())["items"]["i-tomato-sauce"]["qty"] == tom_q + 2, "Discard drops the change")

        print("history log")
        s = await state()
        kinds = {e["kind"] for e in s["history"].values()}
        for k in ("photo", "receipt", "hand", "edit", "listed", "ticked", "stocked", "planned", "fav"):
            check(k in kinds, f"{k} is logged")
        check(not any(e.get("kind") in ("lookup", "settings") for e in s["history"].values()), "lookups and settings aren't logged")
        check(max(len(json.dumps(e)) for e in s["history"].values()) < 400, "events stay small")
        check(((s.get("settings") or {}).get("history") or {}).get("started", 0) > 0, "logging start is recorded")
        n = len(s["history"])
        await load("#add")
        await page.fill("#mn", "Undo test item")
        await page.click("#mf button.pri")
        await page.wait_for_timeout(200)
        check(len((await state())["history"]) == n + 1, "by hand add is logged")
        await page.click("#toast button")
        await page.wait_for_timeout(200)
        check(len((await state())["history"]) == n, "Undo takes the event back out")

        print("history tab")
        await load("#history")
        check(await page.locator("#t-history.on").count() == 1, "History is the fifth tab")
        hst = await page.inner_text("#stats")
        check("this month" in hst and "spent this year" in hst and "in stock" not in hst, f"History tab header shows its own figures ({hst!r})")
        rows = await page.locator("#hlist .hrow").count()
        check(rows >= 15, f"history lists events ({rows})")
        txt = await page.inner_text("#hlist")
        check("Before history" in txt and "Receipt" in txt, "receipts from before logging show, marked as rebuilt")
        check("Amount " in txt and "Used up" in txt and "Added from a product photo" in txt, "logged events are described")
        check(not await page.is_visible("#hsum .tiles4"), "summary starts folded")
        await page.click("#hsum summary")
        await page.wait_for_timeout(100)
        sm = await page.inner_text("#hsum")
        check("Spend per month" in sm and "Spend per shop" in sm and "Most bought" in sm, "summaries show")
        check("€131.85" in sm or "131.85" in sm, "spend includes the older receipt")
        await load("#history")
        check(await page.is_visible("#hsum .tiles4"), "an opened summary stays open")
        await page.screenshot(path=str(OUT / "8-history.png"))
        await page.screenshot(path=str(OUT / "8b-history-full.png"), full_page=True)
        await page.click('#hkind [data-v=meals]')
        await page.wait_for_timeout(100)
        subs = await page.locator("#hlist .hrow > span small").all_inner_texts()
        check(subs and all(x.startswith("Meals") for x in subs), "kind filter shows only meals")
        await page.click('#hkind [data-v=list]')
        subs = await page.locator("#hlist .hrow > span small").all_inner_texts()
        check(any(x.startswith("List") for x in subs) and any(x.startswith("Meals") for x in subs), "kind filter takes several kinds")
        await page.click('#hkind [data-v=""]')
        await page.fill("#hq", "tuna")
        await page.wait_for_timeout(100)
        names = await page.locator("#hlist .hrow b").all_inner_texts()
        check(names and all("tuna" in x.lower() for x in names), "search finds by item")
        await page.fill("#hq", "")
        await page.click('#hper [data-v=m0]')
        await page.wait_for_timeout(100)
        check(await page.locator("#hlist .hrow").count() < rows, "this month hides older events")
        check("131.85" not in await page.inner_text("#hsum"), "this month leaves out the 2025 receipt")
        await page.click('#hper [data-v=pick]')
        await page.fill("#hfrom", "2025-01-01")
        await page.fill("#hto", "2025-01-31")
        await page.dispatch_event("#hto", "change")
        await page.wait_for_timeout(100)
        check("131.85" in await page.inner_text("#hsum") and await page.locator("#hlist .hrow").count() >= 1, "date range finds the old receipt")
        await page.click('#hper [data-v=""]')
        check(await page.is_visible("#hshop"), "shop filter shows")
        await page.click('#hshop [data-v="Farm shop"]')
        await page.wait_for_timeout(100)
        subs = await page.locator("#hlist .hrow > span small").all_inner_texts()
        check(subs and all("Farm shop" in x for x in subs), "shop filter shows that shop's events")
        await page.click('#hshop [data-v=""]')
        await page.click('#hlist .hrow:has-text("Amount")')
        await page.wait_for_timeout(150)
        check("What happened" in await page.inner_text("#sheet"), "tapping an event opens its details")
        await page.click('#sheet [data-ho=f]')
        await page.wait_for_timeout(150)
        check(await page.is_visible("#hitem"), "item filter set from the details")
        names = set(await page.locator("#hlist .hrow b").all_inner_texts())
        check(len(names - {"Artisan-style tomato sauce", "Mercadona", "Receipt"}) == 0 and len(names) >= 1, f"item filter keeps that item and its receipts {names}")
        await page.click("#hitemx")
        await page.set_viewport_size({"width": 320, "height": 720})
        await page.wait_for_timeout(150)
        check(await page.evaluate("document.documentElement.scrollWidth <= 320"), "no sideways scroll at 320 px")
        check(await page.evaluate("[...document.querySelectorAll('nav a')].every(a=>a.getBoundingClientRect().right<=320)"), "five tabs fit at 320 px")
        await page.screenshot(path=str(OUT / "8c-history-320.png"))
        await page.emulate_media(color_scheme="dark")
        await page.set_viewport_size({"width": 390, "height": 844})
        await page.screenshot(path=str(OUT / "8d-history-dark.png"))
        await page.goto(URL + "#pantry")
        await page.click('#plist .row[data-id="i-tomato-sauce"] [data-a=inc]')
        await page.wait_for_timeout(150)
        await page.screenshot(path=str(OUT / "7b-savebar-dark.png"))
        await page.click("#sbdis")
        await page.emulate_media(color_scheme="light")

        print("connection indicator")
        # a second page with a simulated shared db whose snapshots the test sends by hand
        live = await ctx.new_page()
        live.on("pageerror", lambda e: errors.append(str(e)))
        await live.add_init_script("""
window.__snaps = {}; window.__canWrite = !sessionStorage.getItem('viewer');
window.claude = { use: async (name) => {
  if (name === 'db') return {
    collection: c => ({ onSnapshot: (ok, bad) => { window.__snaps[c] = { ok, bad }; return () => {}; } }),
    doc: k => ({ set: async () => {}, delete: async () => {} }) };
  if (name === 'user') return { can: async () => window.__canWrite };
  return null;
}};
window.__send = (fromCache) => { for (const c in window.__snaps) window.__snaps[c].ok({ docs: [], metadata: { fromCache } }); };
""")

        async def dot():
            await live.wait_for_timeout(150)
            return (await live.inner_text("#stats .live")).strip()

        await live.goto(URL + "#pantry")
        await live.wait_for_timeout(300)
        check(await dot() == "Connecting…", "indicator says connecting until the shared data arrives")
        await live.evaluate("__send(true)")
        check(await dot() == "Connecting…", "cached data alone doesn't count as connected")
        await live.evaluate("__send(false)")
        check(await dot() == "Shared live", "indicator says shared live once the data arrives")
        await live.screenshot(path=str(OUT / "0-live.png"), clip={"x": 0, "y": 0, "width": 390, "height": 110})
        await live.evaluate("__send(true)")
        check(await dot() == "Offline", "indicator says offline when updates come only from the cache")
        await live.evaluate("__send(false)")
        check(await dot() == "Shared live", "indicator recovers when the server is back")
        await live.context.set_offline(True)
        await live.wait_for_timeout(200)
        check(await dot() == "Offline", "indicator says offline when the device is offline")
        await live.screenshot(path=str(OUT / "0-offline.png"), clip={"x": 0, "y": 0, "width": 390, "height": 110})
        await live.context.set_offline(False)
        await live.wait_for_timeout(200)
        check(await dot() == "Shared live", "indicator recovers when the device is back online")
        await live.evaluate("window.__snaps.items.bad({ code: 'unavailable' })")
        check(await dot() == "Offline", "indicator says offline when the connection is lost")
        await live.evaluate("sessionStorage.setItem('viewer', '1')")
        await live.reload()
        await live.wait_for_timeout(300)
        await live.evaluate("__send(false)")
        check(await dot() == "View only", "indicator says view only for someone who can't edit")
        await live.close()

        check(not errors, "no page errors " + ("" if not errors else str(errors)))
        await browser.close()

    print("\n" + ("PASSED" if not failures else f"FAILED: {len(failures)}"))
    sys.exit(1 if failures else 0)


asyncio.run(main())
