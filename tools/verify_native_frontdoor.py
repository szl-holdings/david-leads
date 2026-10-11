"""Render both served David fronts with local fixtures and all browser writes denied.

This does not import the backend, admit a dataset, score a record, or verify a real
receipt. Mocked controller tests cover mutation request shapes separately.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import threading
from datetime import UTC, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
WIDTHS = (320, 390, 768, 1280, 1920)
VIEWS = ("leads", "markets", "investors", "operator")
ICON_SHA = "6e2b7d72a3af3d9602b79de41df0194ede6496a9661f057108ec224c0efc92e6"
CSP = ("default-src 'self'; base-uri 'none'; connect-src 'self'; font-src 'self'; "
       "img-src 'self' data:; script-src 'self'; style-src 'self'; "
       "frame-ancestors 'self' https://huggingface.co https://*.huggingface.co")


def run(output: Path) -> int:
    output.mkdir(parents=True, exist_ok=False)
    sources = {"/": "app/static/index.html", "/v0/": "backend/static/index.html"}
    for name in ("holo.css", "app.js", "operator.js"):
        sources["/" + name] = "app/static/" + name
    for name in ("style.css", "app.js"):
        sources["/v0/static/" + name] = "backend/static/" + name
    for name in ("fonts.css", "SpaceGrotesk-Regular.ttf", "SpaceGrotesk-Medium.ttf",
                 "SpaceGrotesk-Bold.ttf", "JetBrainsMono-Regular.ttf", "JetBrainsMono-Medium.ttf"):
        sources["/fonts/" + name] = "app/static/fonts/" + name
    files = {path: (ROOT / source).read_bytes() for path, source in sources.items()}
    mode = {"value": "sample"}
    writes, outside, errors, checks = [], [], [], []
    fixture = "LOCAL PRESENTATION FIXTURE; no backend, source data or receipt execution"
    sample_sources = {"fixture": fixture, "adapters": [{
        "name": "LOCAL synthetic demonstration <img src=x onerror=alert(1)>", "kind": "DEMO",
        "truth_state": "UNKNOWN", "detail": "Only a local render fixture. No licensed source was contacted. " * 4,
    }, {"name": "LOCAL unlicensed adapter", "kind": "LICENSED", "truth_state": "UNAVAILABLE",
        "detail": "No license or connection tested by this preview."}]}
    sample_leads = {"fixture": fixture, "leads": [{
        "id": "LOCAL-SYNTHETIC-ONLY", "legal_name": "LOCAL SYNTHETIC example <img src=x onerror=alert(1)>",
        "state": "NY", "signals": [], "synthetic": True,
    }]}

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            path = urlsplit(self.path).path
            if path in files:
                body = files[path]
                self.send_response(200)
                if path in ("/", "/v0/"):
                    self.send_header("Content-Type", "text/html; charset=utf-8")
                elif path in ("/holo.css", "/v0/static/style.css", "/fonts/fonts.css"):
                    self.send_header("Content-Type", "text/css; charset=utf-8")
                elif path in ("/app.js", "/operator.js", "/v0/static/app.js"):
                    self.send_header("Content-Type", "text/javascript; charset=utf-8")
                else:
                    self.send_header("Content-Type", "font/ttf")
            elif mode["value"] == "sample" and path in ("/v0/v1/sources", "/v0/v1/leads"):
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                body = json.dumps(sample_sources if path == "/v0/v1/sources" else sample_leads).encode()
            else:
                self.send_response(503)
                self.send_header("Content-Type", "application/json")
                body = json.dumps({"detail": "LOCAL unavailable fixture; no backend started", "fixture": fixture}).encode()
            self.send_header("Content-Security-Policy", CSP)
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            try:
                self.wfile.write(body)
            except (BrokenPipeError, ConnectionResetError):
                # A local navigation cancelled this response; close its socket.
                self.close_connection = True

        def do_POST(self):
            writes.append(self.path)
            self.send_error(405)

        do_PUT = do_POST
        do_PATCH = do_POST
        do_DELETE = do_POST

        def log_message(self, *_):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    origin = f"http://127.0.0.1:{server.server_port}"

    def check(name, passed, detail=None):
        checks.append({"name": name, "passed": bool(passed), "detail": detail})

    layout_script = """() => {
      const visible=e=>e.getClientRects().length&&!e.closest('[hidden]')&&getComputedStyle(e).visibility!=='hidden';
      const identify=e=>({tag:e.tagName,id:e.id,text:e.textContent.trim().slice(0,80)});
      return {overflow:Math.max(0,document.documentElement.scrollWidth-document.documentElement.clientWidth),
        clipped:[...document.querySelectorAll('h1,h2,h3,p,button,label')].filter(e=>visible(e)&&e.scrollWidth>e.clientWidth+2).map(identify),
        shortButtons:[...document.querySelectorAll('button')].filter(e=>visible(e)&&e.getBoundingClientRect().height<43.9).map(identify),
        visiblePanels:[...document.querySelectorAll('.view-panel')].filter(visible).map(e=>e.id),
        operatorSessionHidden:document.querySelector('#operatorSession')?.hidden??null,
        text:document.querySelector('main').innerText.length};
    }"""
    contrast_script = r"""pairs => {
      const rgb=value=>{const channels=value.match(/[\d.]+/g)?.map(Number);return channels?.length===3?channels:null;};
      const luminance=color=>color.map(v=>{v/=255;return v<=.04045?v/12.92:((v+.055)/1.055)**2.4;}).reduce((n,v,i)=>n+v*[.2126,.7152,.0722][i],0);
      return pairs.map(([text,surface])=>{const a=rgb(getComputedStyle(document.querySelector(text)).color),b=rgb(getComputedStyle(document.querySelector(surface)).backgroundColor);
        if(!a||!b)return {text,surface,ratio:0};const x=luminance(a),y=luminance(b);return {text,surface,ratio:(Math.max(x,y)+.05)/(Math.min(x,y)+.05)};});
    }"""
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True, executable_path=os.environ.get("CHROME_PATH"),
                                         args=["--disable-dev-shm-usage"])
            context = browser.new_context(reduced_motion="reduce")

            def intercept(route):
                if route.request.method != "GET":
                    writes.append(route.request.url)
                    route.abort()
                elif route.request.url.startswith(origin + "/"):
                    route.continue_()
                else:
                    outside.append(route.request.url)
                    route.abort()

            context.route("**/*", intercept)
            page = context.new_page()
            page.set_default_timeout(10000)
            page.on("pageerror", lambda error: errors.append(str(error)))
            for width in WIDTHS:
                page.set_viewport_size({"width": width, "height": 1000})
                page.goto(origin, wait_until="domcontentloaded")
                page.locator("#boot.done").wait_for(state="attached")
                page.evaluate("document.fonts.ready")
                page.keyboard.press("Tab")
                check(f"main {width}: skip is first", page.locator(".skip-link").evaluate("e=>document.activeElement===e"))
                page.keyboard.press("Enter")
                check(f"main {width}: skip focuses workspace", page.evaluate("document.activeElement.id==='workspace'"))
                check(f"main {width}: absence stays unknown", page.locator("#metricOrganizations").text_content() == "UNKNOWN"
                      and "UNAVAILABLE" in page.locator("#dataStatePill").text_content())
                for view in VIEWS:
                    page.locator(f"#{view}Tab").click()
                    facts = page.evaluate(layout_script)
                    check(f"main {width}: {view} layout", facts["overflow"] <= 1 and not facts["clipped"]
                          and not facts["shortButtons"] and facts["visiblePanels"] == [view + "View"]
                          and facts["operatorSessionHidden"] and facts["text"] > 200, facts)
                    if width in (320, 1280):
                        page.locator(f"#{view}View").scroll_into_view_if_needed()
                        page.screenshot(path=str(output / f"main-{view}-{width}.png"))
                    if view != "leads":
                        page.locator(f"#{view}Tab").focus()
                        page.keyboard.press("/")
                        check(f"main {width}: {view} shortcut opens visible search", page.evaluate(
                            "document.activeElement.id==='searchInput'&&document.querySelector('#leadsTab').getAttribute('aria-selected')==='true'"))
                page.locator("#marketsTab").click()
                opener = page.locator("#openPolicyMobile") if page.locator("#openPolicyMobile").is_visible() else page.locator("#openPolicy")
                opener.click()
                check(f"main {width}: policy has an accessible name", page.get_by_role("dialog", name="Research first. Contact only after clearance.").is_visible())
                page.keyboard.press("/")
                check(f"main {width}: search shortcut respects dialog", page.evaluate(
                    "document.querySelector('#policyDialog').open&&document.querySelector('#marketsTab').getAttribute('aria-selected')==='true'&&document.querySelector('#policyDialog').contains(document.activeElement)"))
                page.keyboard.press("Escape")
                check(f"main {width}: policy returns keyboard focus", opener.evaluate("e=>document.activeElement===e"))
                page.locator("#leadsTab").focus()
                page.keyboard.press("ArrowRight")
                check(f"main {width}: arrow tab controls panel", page.evaluate(
                    "document.activeElement.id==='marketsTab'&&document.querySelector('#marketsTab').getAttribute('aria-selected')==='true'"))
                page.keyboard.press("End")
                check(f"main {width}: end tab reaches operator safely", page.evaluate(
                    "document.activeElement.id==='operatorTab'&&document.querySelector('#operatorSession').hidden"))
                paint = page.evaluate("""() => {const icon=document.querySelector('.szl-identity svg').getBoundingClientRect();
                   return {panel:getComputedStyle(document.querySelector('.view-panel.active')).backgroundColor,
                   header:getComputedStyle(document.querySelector('.app-header')).backgroundColor,
                   iconWidth:icon.width,iconHeight:icon.height};}""")
                check(f"main {width}: opaque native panels", paint["panel"] == "rgb(17, 23, 34)" and paint["header"] == "rgb(11, 16, 26)"
                      and paint["iconWidth"] == 40 and paint["iconHeight"] == 40, paint)
                contrast = page.evaluate(contrast_script, [[".territory-heading p", ".territory-panel"], [".operator-heading p", "#operatorView"], ["#operatorLogin .primary-button", "#operatorLogin .primary-button"]])
                check(f"main {width}: reading and action contrast", all(row["ratio"] >= 4.5 for row in contrast), contrast)
                page.goto(origin + "/v0/", wait_until="domcontentloaded")
                page.locator("#leads .lead").wait_for()
                page.keyboard.press("Tab")
                check(f"demo {width}: skip is first", page.locator(".skip-link").evaluate("e=>document.activeElement===e"))
                page.keyboard.press("Enter")
                check(f"demo {width}: skip focuses demonstration", page.evaluate("document.activeElement.id==='demo-workspace'"))
                facts = page.evaluate(layout_script)
                check(f"demo {width}: readable layout", facts["overflow"] <= 1 and not facts["clipped"] and not facts["shortButtons"], facts)
                check(f"demo {width}: API values remain literal", page.locator("#leads img, #sources img").count() == 0
                      and "<img" in page.locator("#leads").text_content())
                check(f"demo {width}: synthetic boundary and unavailable licenses stay visible", "SYNTHETIC — not real organizations" in page.locator("main").text_content()
                      and "UNAVAILABLE" in page.locator("#sources").text_content())
                check(f"demo {width}: no receipt action before scoring", page.locator("#verify-btn").is_disabled()
                      and not page.locator("#result").is_visible())
                table = page.locator(".table-scroll")
                table.focus()
                before = table.evaluate("e=>e.scrollLeft")
                page.keyboard.press("ArrowRight")
                page.wait_for_timeout(150)
                scrolled = table.evaluate("e=>({left:e.scrollLeft,overflow:e.scrollWidth>e.clientWidth,focus:e===document.activeElement})")
                check(f"demo {width}: table is keyboard reachable", scrolled["focus"] and (not scrolled["overflow"] or scrolled["left"] > before), scrolled)
                contrast = page.evaluate(contrast_script, [[".note", "section[aria-labelledby='source-title']"], [".lead .meta", ".lead"], [".lead button", ".lead button"]])
                check(f"demo {width}: reading and action contrast", all(row["ratio"] >= 4.5 for row in contrast), contrast)
                if width in (320, 1280):
                    table.evaluate("e=>e.scrollLeft=0")
                    page.evaluate("window.scrollTo(0,0)")
                    page.screenshot(path=str(output / f"demo-{width}.png"), full_page=True)
            mode["value"] = "unavailable"
            page.goto(origin + "/v0/", wait_until="domcontentloaded")
            page.wait_for_function("() => document.querySelector('#leads').textContent.includes('UNAVAILABLE')")
            check("demo: unavailable source and dataset clear fixture records", page.locator("#leads .lead").count() == 0
                  and "UNAVAILABLE" in page.locator("#sources tbody").text_content())
            for route in ("/", "/v0/"):
                for width in (320, 1280):
                    page.set_viewport_size({"width": width, "height": 1000})
                    page.emulate_media(forced_colors="active")
                    page.goto(origin + route, wait_until="domcontentloaded")
                    if route == "/":
                        page.locator("#boot.done").wait_for(state="attached")
                    page.keyboard.press("Tab")
                    focus = page.evaluate("""() => {const s=getComputedStyle(document.activeElement);return {width:parseFloat(s.outlineWidth),style:s.outlineStyle};}""")
                    facts = page.evaluate(layout_script)
                    check(f"{route} {width}: forced-color focus and layout", focus["width"] >= 2 and focus["style"] != "none"
                          and facts["overflow"] <= 1 and not facts["clipped"], {"focus": focus, "layout": facts})
            page.emulate_media(forced_colors="none")
            for route in ("/", "/v0/"):
                for zoom in (2, 4):
                    page.set_viewport_size({"width": 1280, "height": 1000})
                    page.goto(origin + route, wait_until="domcontentloaded")
                    if route == "/":
                        page.locator("#boot.done").wait_for(state="attached")
                    page.evaluate("z=>document.documentElement.style.zoom=String(z)", zoom)
                    facts = page.evaluate(layout_script)
                    check(f"{route}: {zoom * 100}% reflow", facts["overflow"] <= 1 and not facts["clipped"], facts)
            browser.close()
    except (PlaywrightError, OSError, ValueError, TypeError, KeyError) as error:
        check("browser qualification completed", False, str(error))
    finally:
        server.shutdown()
        server.server_close()
    for route in ("/", "/v0/"):
        icon = re.search(r'<a class="szl-identity"[^>]*>(<svg.*?</svg>)</a>', files[route].decode(), re.DOTALL)
        digest = hashlib.sha256((icon.group(1) + "\n").encode()).hexdigest() if icon else None
        check(f"{route}: exact approved inline Orbit", digest == ICON_SHA, digest)
    check("no browser writes, outside requests or page errors", not writes and not outside and not errors,
          {"writes": writes, "outside": outside, "errors": errors})
    report = {"schema": "szl.david-native-preview/v1", "observed_at": datetime.now(UTC).isoformat(),
              "scope": fixture, "live_verified": False, "backend_started": False, "effects_executed": False,
              "asset_sha256": {sources[path]: hashlib.sha256(body).hexdigest() for path, body in files.items()},
              "checks": checks, "passed": all(item["passed"] for item in checks)}
    (output / "results.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"checks": len(checks), "passed": sum(item["passed"] for item in checks), "report": str(output / "results.json")}))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    raise SystemExit(run(parser.parse_args().output))
