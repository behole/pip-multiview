"""PIP test drive: swap-drag, focus, container reuse, multi-kind, clear/demo fix,
real-pointer header buttons + drag (v1.3.1 regression: synthetic .click() can't
catch hit-testing bugs)."""
import json
import functools
import http.server
import os
import threading
from playwright.sync_api import sync_playwright

OUT = os.path.dirname(os.path.abspath(__file__))
PORT = 8321
URL = f"http://127.0.0.1:{PORT}/"
MP4 = f"http://127.0.0.1:{PORT}/sample.mp4"   # local ffmpeg-generated test clip
res = {"steps": []}

def serve_here():
    """Background static server so the test is self-contained (was: manual
    `python3 -m http.server 8321` — the test would hang on goto without it)."""
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=OUT)
    try:
        httpd = http.server.ThreadingHTTPServer(("127.0.0.1", PORT), handler)
    except OSError:
        return None                      # dev server already running on PORT
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd

def step(name, ok, detail=""):
    res["steps"].append({"step": name, "ok": bool(ok), "detail": str(detail)[:180]})
    print(("PASS" if ok else "FAIL"), "-", name, ("| " + str(detail) if detail else ""))

def state(page):
    return page.evaluate("""() => {
      const P = window.PIP; if (!P) return {err:'no PIP'};
      const panes = [];
      P.panes.forEach(p => {
        let muted=null, playing=null;
        try { if (p.player) muted = p.player.isMuted(); } catch(e){}
        try { if (p.media) { muted = p.media.muted; playing = !p.media.paused; } } catch(e){}
        const r = p.el.getBoundingClientRect();
        const cr = document.getElementById('canvas').getBoundingClientRect();
        panes.push({id:p.id, kind:p.kind, vid:p.vid, src:(p.src||'').slice(0,60),
          rect:{x:+((r.left-cr.left)/cr.width).toFixed(3), y:+((r.top-cr.top)/cr.height).toFixed(3),
                w:+(r.width/cr.width).toFixed(3), h:+(r.height/cr.height).toFixed(3)},
          muted, playing,
          hasMedia: !!p.media, hasIframe: !!p.el.querySelector('.stage iframe')});
      });
      return {count: P.panes.size, panes, note: document.querySelector('#note')?.textContent||''};
    }""")

def rects(page):
    return {p["id"]: p["rect"] for p in state(page)["panes"]}

with sync_playwright() as pw:
    serve_here()
    browser = pw.chromium.launch(channel="chrome", headless=True,
                                 args=["--autoplay-policy=no-user-gesture-required", "--mute-audio"])
    page = browser.new_page(viewport={"width": 1600, "height": 900})
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.goto(URL, wait_until="domcontentloaded")
    page.evaluate("() => { localStorage.clear(); }")
    page.reload(wait_until="domcontentloaded")
    page.wait_for_timeout(9000)

    # --- boot: fresh visitor gets demo; clear now truly clears ---
    st = state(page)
    step("fresh boot: demo wall (3 panes)", st.get("count") == 3, f"count={st.get('count')}")
    page.click("#clear")
    page.wait_for_timeout(300)
    st = state(page)
    step("clear: truly empty now (no demo respawn)",
         st.get("count") == 0 and "cleared" in st.get("note", ""), f"count={st.get('count')} note={st.get('note')}")
    page.click("#demo")
    page.wait_for_timeout(6000)
    step("demo button: reloads demo on demand", state(page).get("count") == 3)

    # --- parser: one box, many kinds ---
    cases = [
        ("https://www.youtube.com/watch?v=dQw4w9WgXcQ", "video"),
        ("https://youtu.be/jNQXAC9IVRw", "video"),
        ("https://www.twitch.tv/shroud", "twitch"),
        ("https://clips.twitch.tv/FunnyClipName", "twitch"),
        ("https://www.tiktok.com/@scout2015/video/6718335390845095173", "tiktok"),
        ("https://www.tiktok.com/@someuser", "web"),
        ("https://vimeo.com/76979871", "web"),
        (MP4, "file"),
        ("https://example.com/page", "web"),
    ]
    got = page.evaluate("""(cases) => cases.map(c => {
        const p = window.PIP.parse(c); return p ? p.kind : null;
    })""", [c for c, _ in cases])
    step("parser: 9 url shapes → correct kinds", got == [k for _, k in cases], json.dumps(dict(zip([c[:28] for c,_ in cases], got))))

    # --- file pane: mounts, and playback advances (headless self-pauses
    #     remote media, so drive play() explicitly and check time moves) ---
    page.evaluate(f"() => window.PIP.add({{kind:'file', src:'{MP4}'}})")
    page.wait_for_timeout(2500)
    t0 = page.evaluate("() => { const p=[...window.PIP.panes.values()].find(x=>x.kind=='file'); p.media.muted=true; p.media.play(); return p.media.currentTime; }")
    page.wait_for_timeout(1500)
    st = state(page)
    fp = [p for p in st["panes"] if p["kind"] == "file"]
    t1 = page.evaluate("() => [...window.PIP.panes.values()].find(x=>x.kind=='file').media.currentTime")
    advanced = (t1 - t0) > 0.3
    step("file pane: mp4 mounts + playback advances", len(fp) == 1 and fp[0]["hasMedia"] and advanced,
         f"t {t0:.2f}→{t1:.2f}")

    # --- solo covers file panes ---
    vid_ids = [p["id"] for p in st["panes"] if p["kind"] == "video"]
    file_id = fp[0]["id"]
    page.evaluate(f"() => window.PIP.solo('{file_id}')")
    page.wait_for_timeout(400)
    st = state(page)
    fm = [p for p in st["panes"] if p["id"] == file_id][0]["muted"]
    vm = [p for p in st["panes"] if p["id"] == vid_ids[0]][0]["muted"]
    step("solo: file pane audible, yt panes muted", fm is False and vm is True, f"file={fm} yt={vm}")
    page.evaluate(f"() => window.PIP.solo('{file_id}')")

    # --- real-pointer clicks: header buttons must respond to genuine mouse
    #     events (v1.3.1 regression: startDrag swallowed pointerdown on
    #     buttons, synthetic .click() couldn't catch it) ---
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
    step("real click solo btn: unmutes pane 0", m0 is False, f"muted={m0}")
    click_btn(0, ".audio")
    m0b = page.evaluate("() => [...window.PIP.panes.values()][0].player.isMuted()")
    step("real click solo btn: second click re-mutes", m0b is True, f"muted={m0b}")

    # drag via real pointer: header drag must still move the pane after the
    # button opt-out fix (drag arms only after 4px dead-zone)
    xy = page.evaluate("""() => { const p=[...document.querySelectorAll('.pane')][0];
      const r = p.querySelector('.title').getBoundingClientRect();
      return {x: r.x + 10, y: r.y + r.height/2}; }""")
    x_before = page.evaluate("() => [...window.PIP.panes.values()][0].el.getBoundingClientRect().x")
    page.mouse.move(xy["x"], xy["y"]); page.mouse.down()
    page.mouse.move(xy["x"] + 150, xy["y"] + 60, steps=8); page.mouse.up()
    page.wait_for_timeout(300)
    x_after = page.evaluate("() => [...window.PIP.panes.values()][0].el.getBoundingClientRect().x")
    step("real pointer drag: header drag moves the pane", x_after - x_before > 100, f"dx={x_after-x_before:.0f}px")


    # --- swap-drag: apply a non-overlapping layout first (the demo wall
    #     overlaps by design, so "pane under cursor" is ambiguous there),
    #     then drag A's header onto B → geometry swaps ---
    page.evaluate("() => window.PIP.presets.grid()")
    page.wait_for_timeout(300)
    st = state(page)
    a, b = st["panes"][0], st["panes"][1]
    ra, rb = a["rect"].copy(), b["rect"].copy()
    ha = page.evaluate(f"""() => {{
      const el = document.querySelector('.pane[data-id="{a['id']}"] .head');
      const r = el.getBoundingClientRect(); return {{x: r.x + r.width*0.3, y: r.y + r.height/2}};
    }}""")
    tb = page.evaluate(f"""() => {{
      const el = document.querySelector('.pane[data-id="{b['id']}"]');
      const r = el.getBoundingClientRect(); return {{x: r.x + r.width/2, y: r.y + r.height/2}};
    }}""")
    page.mouse.move(ha["x"], ha["y"]); page.mouse.down()
    page.wait_for_timeout(80)
    dragging_cls = page.evaluate("() => document.body.classList.contains('dragging')")
    pe = page.evaluate("() => getComputedStyle(document.querySelector('.stage iframe')).pointerEvents")
    page.mouse.move(tb["x"], tb["y"], steps=12); page.wait_for_timeout(80)
    page.mouse.up()
    page.wait_for_timeout(300)
    st2 = state(page)
    a2 = [p for p in st2["panes"] if p["id"] == a["id"]][0]["rect"]
    b2 = [p for p in st2["panes"] if p["id"] == b["id"]][0]["rect"]
    swapped = a2 == rb and b2 == ra
    step("drag: body.dragging set + iframes inert (no jump)", dragging_cls and pe == "none",
         f"cls={dragging_cls} iframe.pointerEvents={pe}")
    step("swap: drop on another pane swaps geometry", swapped, f"a:{a2} b:{b2}")

    # --- rotate: contents permute over the SAME shape; players keep playing ---
    page.evaluate("() => window.PIP.presets.grid()")
    page.wait_for_timeout(300)
    before_rot = state(page)
    vids_before = {p["vid"] or p["src"]: p["rect"] for p in before_rot["panes"]}
    shape_before = sorted([(r["x"], r["y"], r["w"], r["h"]) for r in [p["rect"] for p in before_rot["panes"]]])
    playing_before = {p["id"]: p["playing"] for p in before_rot["panes"]}
    page.evaluate("() => window.PIP.rotate(1)")
    page.wait_for_timeout(400)
    after_rot = state(page)
    shape_after = sorted([(r["x"], r["y"], r["w"], r["h"]) for r in [p["rect"] for p in after_rot["panes"]]])
    vids_after = {p["vid"] or p["src"]: p["rect"] for p in after_rot["panes"]}
    # every content moved to a rect that some pane previously occupied
    old_rects = set((r["x"], r["y"], r["w"], r["h"]) for r in [p["rect"] for p in before_rot["panes"]])
    all_moved_to_old = all((r["x"], r["y"], r["w"], r["h"]) in old_rects
                           for r in [p["rect"] for p in after_rot["panes"]])
    no_one_home = all(vids_after[k] != v for k, v in vids_before.items())
    step("rotate: shape identical, contents permuted", shape_after == shape_before and all_moved_to_old,
         f"shape_equal={shape_after == shape_before}")
    step("rotate: every content actually moved slot", no_one_home)
    # players still alive after rotation
    still_playing = page.evaluate("""() => {
      let n = 0;
      window.PIP.panes.forEach(p => {
        try { if (p.player && p.player.getPlayerState() === 1) n++; } catch(e){}
        try { if (p.media && !p.media.paused) n++; } catch(e){}
      });
      return n;
    }""")
    step("rotate: players keep playing through rotation", still_playing >= 3, f"playing={still_playing}")

    # --- focus: ◎ makes one big + rail; persists across reload ---
    target = [p for p in st2["panes"] if p["kind"] == "file"][0]["id"]
    page.evaluate(f"() => window.PIP.focusById('{target}')")
    page.wait_for_timeout(300)
    st3 = state(page)
    big = [p for p in st3["panes"] if p["id"] == target][0]["rect"]
    others = [p["rect"]["w"] for p in st3["panes"] if p["id"] != target]
    step("focus: ◎ pane takes big cell, others rail",
         big["w"] > 0.65 and all(w < 0.35 for w in others), f"big={big['w']} rail={others}")
    page.reload(wait_until="domcontentloaded")
    page.wait_for_timeout(9000)
    st4 = state(page)
    file4 = [p for p in st4["panes"] if p["kind"] == "file"]
    step("reload: layout + file pane + focus restored",
         st4.get("count") == 4 and len(file4) == 1 and file4[0]["rect"]["w"] > 0.65,
         f"count={st4.get('count')} file={len(file4)}")

    # --- container reuse via ✎ arm + url box ---
    arm_id = [p for p in st4["panes"] if p["kind"] == "video"][0]["id"]
    rect_before = [p for p in st4["panes"] if p["id"] == arm_id][0]["rect"]
    page.evaluate(f"() => {{ const p=[...window.PIP.panes.values()].find(x=>x.id==='{arm_id}'); p && p.el.querySelector('.swapr').click(); }}")
    page.wait_for_timeout(200)
    armed_note = page.evaluate("() => document.querySelector('#note').textContent")
    page.fill("#url", MP4)
    page.press("#url", "Enter")
    page.wait_for_timeout(5000)
    st5 = state(page)
    same_spot = [p for p in st5["panes"] if p["kind"] == "file" and p["rect"] == rect_before]
    step("reuse: ✎ arms pane, new url replaces in-place (same rect, new kind)",
         "paste a url" in armed_note and st5.get("count") == 4 and len(same_spot) == 1,
         f"note={armed_note} count={st5.get('count')}")

    # --- regression: armed + chat mode must refuse non-YT urls (the v1.4 fix) ---
    vid_pane = [p for p in st5["panes"] if p["kind"] == "video"][0]["id"] if any(
        p["kind"] == "video" for p in st5["panes"]) else None
    if vid_pane:
        page.click("button[data-mode='chat']")
        page.evaluate(f"() => {{ const p=[...window.PIP.panes.values()].find(x=>x.id==='{vid_pane}'); p.el.querySelector('.swapr').click(); }}")
        page.fill("#url", "https://vimeo.com/76979871")
        page.press("#url", "Enter")
        page.wait_for_timeout(400)
        still_web = page.evaluate(f"() => {{ const p=[...window.PIP.panes.values()].find(x=>x.id==='{vid_pane}'); return p.kind; }}")
        step("armed+chat: vimeo paste refused (pane kind unchanged, no broken chat embed)",
             still_web == "video", f"kind={still_web}")
        page.click("button[data-mode='']") if page.query_selector("button[data-mode='']") else page.keyboard.press("Escape")
        page.evaluate("() => { document.querySelector('#note').textContent=''; }")

    # --- drop a url onto a pane = reuse; onto canvas = new pane ---
    drop_res = page.evaluate("""() => {
      const target = [...document.querySelectorAll('.pane')][1];
      const r = target.getBoundingClientRect();
      const dt = new DataTransfer();
      dt.setData('text/uri-list', 'https://www.twitch.tv/shroud');
      const ev = new DragEvent('drop', {bubbles:true, cancelable:true, dataTransfer:dt,
        clientX: r.x + r.width/2, clientY: r.y + r.height/2});
      target.dispatchEvent(ev);
      return {kinds: [...window.PIP.panes.values()].map(p=>p.kind), count: window.PIP.panes.size};
    }""")
    step("drop-on-pane: reuses that container (→ twitch)",
         "twitch" in drop_res["kinds"], json.dumps(drop_res["kinds"]))
    before = state(page).get("count")
    page.evaluate("""() => {
      const c = document.querySelector('#canvas');
      const dt = new DataTransfer();
      dt.setData('text/uri-list', 'https://vimeo.com/76979871');
      c.dispatchEvent(new DragEvent('drop', {bubbles:true, cancelable:true, dataTransfer:dt,
        clientX: 300, clientY: 300}));
    }""")
    page.wait_for_timeout(400)
    after = state(page).get("count")
    step("drop-on-canvas: creates new pane", after == before + 1, f"{before}→{after}")

    # --- regression: refusal-hint badge must persist after iframe load (was auto-hidden at 4s).
    #     buildIframePane (twitch/web panes) sets it on mount; YT panes only badge onError. ---
    badge = page.evaluate("""() => {
      const p = [...window.PIP.panes.values()].find(x =>
        (x.kind === 'twitch' || x.kind === 'web') && x.el.querySelector('.stage iframe'));
      if (!p) return null;
      const b = p.el.querySelector('.badge');
      return {kind: p.kind, shown: getComputedStyle(b).display !== 'none', text: b.textContent};
    }""")
    step("refusal badge stays visible after load (no auto-hide)",
         badge and badge["shown"] and "refus" in badge["text"], f"badge={badge}")

    # close-button check runs last: it mutates pane count, nothing downstream may depend on it
    n_before = page.evaluate("() => window.PIP.panes.size")
    click_btn(2, ".close")
    n_after = page.evaluate("() => window.PIP.panes.size")
    step("real click close btn: removes the pane", n_after == n_before - 1, f"{n_before}->{n_after}")

    step("no page JS errors", not errors, "; ".join(errors[:3]))
    browser.close()

print("RESULT_JSON:" + json.dumps(res))
