"""PIP headless test drive: load, players, solo audio, presets, CHAT PANE, persistence."""
import json, time
from playwright.sync_api import sync_playwright

OUT = "/home/behole/workspace/PIP"
URL = "http://127.0.0.1:8321/"
LIVE_URL = "https://www.youtube.com/watch?v=jfKfPfyJRdk"   # lofi girl — live most of the time
res = {"steps": []}

def step(name, ok, detail=""):
    res["steps"].append({"step": name, "ok": bool(ok), "detail": detail})
    print(("PASS" if ok else "FAIL"), "-", name, ("| " + str(detail) if detail else ""))

def pip_state(page):
    return page.evaluate("""() => {
      const P = window.PIP; if (!P) return {err:'no PIP'};
      const panes = [];
      P.panes.forEach(p => {
        let state=null, muted=null, dur=null;
        try {
          if (p.player) {
            state = p.player.getPlayerState();
            muted = p.player.isMuted();
            dur = Math.round(p.player.getDuration());
          }
        } catch(e) { state = 'ERR '+e.message; }
        panes.push({id:p.id, kind:p.kind, vid:p.vid, title:(p.title||'').slice(0,40),
                    state, muted, dur,
                    hasIframe: !!p.el.querySelector('.stage iframe')});
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
    page.wait_for_timeout(9000)

    st = pip_state(page)
    step("boot: 3 demo panes", st.get("count") == 3, f"count={st.get('count')}")
    playing = [p for p in st.get("panes", []) if p["state"] in (1, 3)]
    step("players started muted (mute-wall)",
         len(playing) >= 2 and all(p["muted"] for p in st.get("panes", []) if p["kind"] == "video"),
         f"active={len(playing)}")
    page.screenshot(path=f"{OUT}/shot-boot.png")

    ids = [p["id"] for p in st["panes"]]
    page.evaluate(f"() => window.PIP.solo('{ids[0]}')")
    page.wait_for_timeout(400)
    st2 = pip_state(page)
    m = {p["id"]: p["muted"] for p in st2["panes"]}
    step("solo: pane0 unmuted, others muted", m.get(ids[0]) is False and all(m[i] for i in ids[1:]), json.dumps(m))
    page.evaluate(f"() => window.PIP.solo('{ids[0]}')")
    page.wait_for_timeout(400)
    step("unsolo: back to all muted", all(p["muted"] for p in pip_state(page)["panes"]))

    # --- chat pane via the real UI path: mode toggle + url box ---
    page.click('[data-mode="chat"]')
    add_label = page.evaluate("() => document.querySelector('#add').textContent")
    step("chat mode toggle (+ chat label)", add_label == "+ chat", add_label)
    page.fill("#url", LIVE_URL)
    page.press("#url", "Enter")
    page.wait_for_timeout(3500)
    st3 = pip_state(page)
    chat = [p for p in st3["panes"] if p["kind"] == "chat"]
    step("chat pane added via url box", st3.get("count") == 4 and len(chat) == 1,
         f"count={st3.get('count')}")
    src = page.evaluate("""() => {
      const el = document.querySelector('.pane.chat .stage iframe');
      return el ? el.src : null;
    }""")
    step("chat iframe = live_chat embed w/ domain + dark theme",
         bool(src) and "live_chat" in src and "embed_domain=127.0.0.1" in src and "dark_theme=1" in src, src)
    page.screenshot(path=f"{OUT}/shot-chat.png")

    # honest chat-liveness probe: inspect YT's frame from inside the app page
    page.wait_for_timeout(6000)
    chat_frames = [f for f in page.frames if "live_chat" in (f.url or "")]
    if chat_frames:
        try:
            has_renderer = chat_frames[0].evaluate(
                "() => !!document.querySelector('yt-live-chat-renderer, #items')")
            msg_count = chat_frames[0].evaluate(
                "() => document.querySelectorAll('yt-live-chat-text-message-renderer').length")
            print(f"INFO - chat frame live: renderer={has_renderer} messages={msg_count}")
        except Exception as e:
            print("INFO - chat frame probe blocked:", str(e)[:100])
    else:
        print("INFO - no live_chat frame found in page")

    # chat pane coexists with audio model: solo a video while chat present
    page.evaluate(f"() => window.PIP.solo('{ids[1]}')")
    page.wait_for_timeout(300)
    st4 = pip_state(page)
    m4 = {p["id"]: p["muted"] for p in st4["panes"] if p["kind"] == "video"}
    step("solo works with chat pane present (no crash)",
         m4.get(ids[1]) is False and all(v for k, v in m4.items() if k != ids[1]), json.dumps(m4))
    page.evaluate("() => { window.PIP.panes.forEach(p => p.player && p.player.mute()); }")

    # add a 5th video pane, then verticals across the mixed wall
    page.evaluate("() => window.PIP.add('kK42WEwQszc')")
    page.wait_for_timeout(3500)
    page.evaluate("() => window.PIP.presets.focus()")
    page.evaluate("() => window.PIP.presets.grid()")
    page.wait_for_timeout(300)
    page.evaluate("() => window.PIP.presets.verticals()")
    step("mixed-wall presets execute (5 panes: 4 video + 1 chat)",
         pip_state(page).get("count") == 5)

    # --- persistence: reload, expect 5 panes incl. the chat pane ---
    page.reload(wait_until="domcontentloaded")
    page.wait_for_timeout(9000)
    st5 = pip_state(page)
    chat5 = [p for p in st5.get("panes", []) if p["kind"] == "chat"]
    step("reload: 5 panes restored", st5.get("count") == 5, f"count={st5.get('count')}")
    step("chat pane survives reload as chat (iframe re-mounted)",
         len(chat5) == 1 and chat5[0]["hasIframe"] and not chat5[0].get("state"),
         json.dumps(chat5))
    playing5 = [p for p in st5.get("panes", []) if p["state"] in (1, 3)]
    step("restored videos autoplay muted", len(playing5) >= 2, f"active={len(playing5)}")
    page.screenshot(path=f"{OUT}/shot-restored.png")

    # --- direct probe: is YT serving chat for the live id right now? (informational) ---
    probe = browser.new_page()
    try:
        probe.goto("https://www.youtube.com/live_chat?v=jfKfPfyJRdk&embed_domain=127.0.0.1&dark_theme=1",
                   wait_until="domcontentloaded", timeout=20000)
        probe.wait_for_timeout(4000)
        live = probe.evaluate("() => !!document.querySelector('yt-live-chat-renderer, #items')")
        print("INFO - live_chat endpoint serving messages for jfKfPfyJRdk:", live)
        probe.screenshot(path=f"{OUT}/shot-chat-direct.png")
    except Exception as e:
        print("INFO - live_chat probe failed:", str(e)[:120])
    probe.close()

    step("no page JS errors", not errors, "; ".join(errors[:3]))
    browser.close()

print("RESULT_JSON:" + json.dumps(res))
