"""PIP v0 headless test drive: load, verify players, solo audio, presets, persistence."""
import json, time
from playwright.sync_api import sync_playwright

OUT = "/home/behole/workspace/PIP"
URL = "http://127.0.0.1:8321/"
res = {"steps": []}

def step(name, ok, detail=""):
    res["steps"].append({"step": name, "ok": bool(ok), "detail": detail})
    print(("PASS" if ok else "FAIL"), "-", name, ("| " + str(detail) if detail else ""))

def pip_state(page):
    return page.evaluate("""() => {
      const P = window.PIP; if (!P) return {err:'no PIP'};
      const panes = [];
      P.panes.forEach(p => {
        let state=null, muted=null, dur=null, cur=null, t='';
        try {
          state = p.player.getPlayerState();
          muted = p.player.isMuted();
          dur = Math.round(p.player.getDuration());
          cur = Math.round(p.player.getCurrentTime());
          t = (p.title||'').slice(0,48);
        } catch(e) { state = 'ERR '+e.message; }
        panes.push({id:p.id, vid:p.vid, title:t, state, muted, dur, cur});
      });
      return {count: P.panes.size, panes, note: document.querySelector('#note')?.textContent||''};
    }""")

with sync_playwright() as pw:
    browser = pw.chromium.launch(channel="chrome", headless=True,
                                 args=["--autoplay-policy=no-user-gesture-required",
                                       "--mute-audio"])
    page = browser.new_page(viewport={"width": 1600, "height": 900})
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.goto(URL, wait_until="domcontentloaded")
    page.wait_for_timeout(9000)  # iframe_api + 3 players

    st = pip_state(page)
    step("boot: PIP global + 3 demo panes", st.get("count") == 3, f"count={st.get('count')} note={st.get('note')}")
    playing = [p for p in st.get("panes", []) if p["state"] in (1, 3)]  # PLAYING or BUFFERING
    all_muted = all(p["muted"] for p in st.get("panes", []))
    step("players started muted (mute-wall)", len(playing) >= 2 and all_muted,
         f"active={len(playing)} all_muted={all_muted}")
    have_dur = [p["vid"] for p in st.get("panes", []) if (p["dur"] or 0) > 0]
    step("durations reporting (API wired)", len(have_dur) >= 2, str(have_dur))
    page.screenshot(path=f"{OUT}/shot-boot.png")

    # --- solo audio toggle: pane 0 ---
    ids = [p["id"] for p in st["panes"]]
    page.evaluate(f"() => window.PIP.solo('{ids[0]}')")
    page.wait_for_timeout(400)
    st2 = pip_state(page)
    m = {p["id"]: p["muted"] for p in st2["panes"]}
    step("solo: pane0 unmuted, others muted", m.get(ids[0]) is False and all(m[i] for i in ids[1:]), json.dumps(m))
    page.evaluate(f"() => window.PIP.solo('{ids[0]}')")  # toggle back to all-muted
    page.wait_for_timeout(300)
    st3 = pip_state(page)
    step("unsolo: back to all muted", all(p["muted"] for p in st3["panes"]))

    # --- add a 4th pane via API, then verticals preset ---
    page.evaluate("() => window.PIP.add('kK42WEwQszc')")  # ~9:16-ish short-form stand-in
    page.wait_for_timeout(3500)
    st4 = pip_state(page)
    step("add: 4th pane live", st4.get("count") == 4, f"count={st4.get('count')}")
    page.evaluate("() => window.PIP.presets.verticals()")
    page.wait_for_timeout(400)
    rects = page.evaluate("""() => [...document.querySelectorAll('.pane')].map(el => {
        const r = el.getBoundingClientRect();
        return {w: +(r.width/innerWidth).toFixed(3), h: +(r.height/innerHeight).toFixed(3),
                x: +(r.left/innerWidth).toFixed(3)};
    })""")
    cols = sorted(set(r["x"] for r in rects))
    step("verticals preset: 4 columns laid out", len(rects) == 4 and len(cols) == 4,
         f"xs={[r['x'] for r in rects]} h={[r['h'] for r in rects]}")
    page.screenshot(path=f"{OUT}/shot-verticals.png")

    # --- focus + grid presets run without error ---
    page.evaluate("() => window.PIP.presets.focus()")
    page.evaluate("() => window.PIP.presets.grid()")
    page.wait_for_timeout(300)
    page.evaluate("() => window.PIP.presets.verticals()")
    step("focus/grid presets execute", True)

    # --- persistence: reload, expect 4 panes restored ---
    page.reload(wait_until="domcontentloaded")
    page.wait_for_timeout(9000)
    st5 = pip_state(page)
    step("reload: 4 panes restored from localStorage", st5.get("count") == 4, f"count={st5.get('count')}")
    playing5 = [p for p in st5.get("panes", []) if p["state"] in (1, 3)]
    step("restored panes autoplay muted", len(playing5) >= 2, f"active={len(playing5)}")
    page.screenshot(path=f"{OUT}/shot-restored.png")

    step("no page JS errors", not errors, "; ".join(errors[:3]))
    browser.close()

print("RESULT_JSON:" + json.dumps(res))
