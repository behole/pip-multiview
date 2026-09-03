# PIP — masonry multiview for YouTube

A wall of viewports instead of one centered video. Watch 3 verticals at once,
solo one audio, ignore the algorithm entirely.

![boot](shot-boot.png)

## What it is

- **Panes, not a page.** Each video is a free-floating viewport on a canvas.
  Drag the header to move, grab the corner to resize, double-click header to
  maximize. The layout is yours; nothing recenters itself.
- **Click-to-solo audio.** Everything loads muted (the mute-wall). Click a
  pane → it's the only one you hear. Click again → back to silence.
- **Presets:** `3-verticals` (9:16 columns — the phone-native default),
  `grid`, `focus` (one big + rail), `cascade`.
- **Persistence.** Panes + geometry live in localStorage; reload and the wall
  is still yours.
- **Per-pane chrome:** play/pause, seek bar, live title, close. Videos that
  refuse embedding get flagged with a badge instead of pretending to work.

## Run it

```sh
cd ~/workspace/PIP
python3 -m http.server 8321 --bind 0.0.0.0
```

- On the box: http://127.0.0.1:8321
- Over Tailscale: http://100.70.136.106:8321 (or
  pop-os.warthog-clownfish.ts.net:8321)

`file://` won't work — the YouTube IFrame API needs a real origin. Cap is 6
panes; each iframe is a full YouTube player and they add up.

## The companion theme

`youtube.user.css` — Stylus theme for youtube.com itself: `--yt-spec-*`
palette overrides (accent `#f05a28`) + toggles for hide-Shorts,
hide-home-recs, hide-comments, calm-grid. Install via Stylus (live-reload on
a `file://` install; bump `@version` + push for auto-update from a raw
GitHub URL).

## Test

```sh
python3 test_pip.py   # headless Chrome, boots the page and drives every feature
```

## v1 boundary, on purpose

No search (paste URLs only), no account sync, no backend, no telemetry.
The player is YouTube's embed; the layout, the audio model, and the
reasons-to-visit are yours.

## Ideas on deck

- Chat pane — YouTube Live Chat as just another viewport
- Search pane (Data API, 100 free queries/day)
- Document PiP pop-out of the whole wall
