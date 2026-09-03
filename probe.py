"""Probe: codec support in this headless chrome + verify hit-test theory for swap."""
from playwright.sync_api import sync_playwright

with sync_playwright() as pw:
    b = pw.chromium.launch(channel="chrome", headless=True, args=["--mute-audio"])
    page = b.new_page()
    page.goto("http://127.0.0.1:8321/", wait_until="domcontentloaded")
    print("h264:", page.evaluate("() => document.createElement('video').canPlayType('video/mp4; codecs=\"avc1.42E01E,mp4a.40.2\"')"))
    print("vp9 :", page.evaluate("() => document.createElement('video').canPlayType('video/webm; codecs=\"vp9\"')"))
    # hit-test theory: dragged pane covers target center?
    page.wait_for_timeout(6000)
    r = page.evaluate("""() => {
      const panes = [...document.querySelectorAll('.pane')];
      const src = panes[0].getBoundingClientRect();
      const dst = panes[1].getBoundingClientRect();
      // simulate: grab src head center-ish, land on dst center
      const grab = {x: src.x + 100, y: src.y + 15};
      const land = {x: dst.x + dst.width/2, y: dst.y + dst.height/2};
      return {grab, land};
    }""")
    page.mouse.move(r["grab"]["x"], r["grab"]["y"]); page.mouse.down()
    page.evaluate("() => document.body.classList.add('dragging')")
    page.mouse.move(r["land"]["x"], r["land"]["y"], steps=8)
    hit = page.evaluate(f"""() => {{
      const el = document.elementFromPoint({r['land']['x']}, {r['land']['y']});
      return el ? (el.className || el.tagName) + ' -> pane:' + !!el.closest('.pane') : 'null';
    }}""")
    print("hit-test while dragging (with iframes inert):", hit)
    page.mouse.up()
    b.close()
