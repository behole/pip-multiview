"""Real-pointer regression: header buttons must respond to genuine mouse clicks.
(v1.2 regression: startDrag swallowed pointerdown on buttons -> click never fired)"""
from playwright.sync_api import sync_playwright

OUT = "/home/behole/workspace/PIP"
fails = []

def check(name, ok, detail=""):
    print(("PASS" if ok else "FAIL"), "-", name, ("| " + str(detail) if detail else ""))
    if not ok: fails.append(name)

with sync_playwright() as pw:
    b = pw.chromium.launch(channel="chrome", headless=True,
                           args=["--autoplay-policy=no-user-gesture-required", "--mute-audio"])
    page = b.new_page(viewport={"width": 1600, "height": 900})
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.goto("http://127.0.0.1:8321/", wait_until="domcontentloaded")
    page.wait_for_timeout(8000)

    def click_btn(pane_idx, sel):
        xy = page.evaluate(f"""() => {{
          const pane = [...document.querySelectorAll('.pane')][{pane_idx}];
          const r = pane.querySelector('{sel}').getBoundingClientRect();
          return {{x: r.x + r.width/2, y: r.y + r.height/2}};
        }}""")
        page.mouse.move(xy["x"], xy["y"]); page.mouse.down(); page.mouse.up()
        page.wait_for_timeout(400)

    click_btn(0, ".audio")
    m0 = page.evaluate("() => [...window.PIP.panes.values()][0].player.isMuted()")
    check("solo btn: real click unmutes pane 0", m0 is False, f"muted={m0}")
    click_btn(0, ".audio")
    m0b = page.evaluate("() => [...window.PIP.panes.values()][0].player.isMuted()")
    check("solo btn: second click re-mutes", m0b is True, f"muted={m0b}")

    click_btn(1, ".focusb")
    w1 = page.evaluate("() => { const p=[...window.PIP.panes.values()][1]; return p.el.getBoundingClientRect().width / document.getElementById('canvas').getBoundingClientRect().width; }")
    check("focus btn: real click gives pane 1 the big cell", w1 > 0.65, f"w={w1:.2f}")
    click_btn(0, ".focusb")
    w0 = page.evaluate("() => { const p=[...window.PIP.panes.values()][0]; return p.el.getBoundingClientRect().width / document.getElementById('canvas').getBoundingClientRect().width; }")
    check("focus btn: focus moves to pane 0", w0 > 0.65, f"w={w0:.2f}")

    n_before = page.evaluate("() => window.PIP.panes.size")
    click_btn(2, ".close")
    n_after = page.evaluate("() => window.PIP.panes.size")
    check("close btn: real click removes the pane", n_after == n_before - 1, f"{n_before}->{n_after}")

    playing0 = page.evaluate("() => [...window.PIP.panes.values()][0].playing")
    click_btn(0, ".play")
    playing1 = page.evaluate("() => [...window.PIP.panes.values()][0].playing")
    check("play btn: real click toggles playback", playing1 != playing0, f"{playing0}->{playing1}")

    # drag still works after the fix: move pane 0's header by 150px
    xy = page.evaluate("""() => { const p=[...document.querySelectorAll('.pane')][0];
      const r = p.querySelector('.title').getBoundingClientRect();
      return {x: r.x + 10, y: r.y + r.height/2}; }""")
    x_before = page.evaluate("() => [...window.PIP.panes.values()][0].el.getBoundingClientRect().x")
    page.mouse.move(xy["x"], xy["y"]); page.mouse.down()
    page.mouse.move(xy["x"] + 150, xy["y"] + 60, steps=8); page.mouse.up()
    page.wait_for_timeout(300)
    x_after = page.evaluate("() => [...window.PIP.panes.values()][0].el.getBoundingClientRect().x")
    check("drag still works: header drag moves the pane", x_after - x_before > 100, f"dx={x_after-x_before:.0f}px")

    check("no page JS errors", not errors, "; ".join(errors[:3]))
    b.close()

print("RESULT:", "ALL PASS" if not fails else f"FAILURES: {fails}")
