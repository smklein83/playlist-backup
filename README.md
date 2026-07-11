# Glasses Playlist Player

A 600×600 web player for the Meta Ray-Ban Display browser: big focusable
buttons (swipe to choose, pinch to select), status and errors rendered on
the lens. Serve it over HTTPS (e.g. GitHub Pages) and open it in the
glasses browser.

## Two screens

1. **Choose a playlist** — the screen you land on. It lists every playlist
   in the `PLAYLISTS` array (swipe to move, pinch to select).
2. **Player** — the selected playlist's videos, with the usual controls:
   Prev, Play/Pause, Next, 15 seconds back, 30 seconds forward, and a 2x
   speed toggle.

**Press Prev twice within 2 seconds to jump back to the playlist screen.**
A single Prev still just goes to the previous video.

Each playlist is either a YouTube playlist or a set of self-hosted files —
both use the same player UI:

| Kind | Entry shape | Plays |
|------|-------------|-------|
| YouTube | `{ name, list }` | the playlist `list` via the IFrame API |
| Self-hosted | `{ name, videos: [...] }` | your own video files |

## Auto-remove finished videos (`consume`)

Add `consume: true` to a playlist entry and any video you play **to the
end** drops out of that playlist's rotation. Skipping (Prev/Next) or leaving
a video unfinished keeps it. Without the flag a playlist is retained and
loops forever.

**This never touches YouTube.** It does not sign in and it cannot edit the
real playlist — finished video ids are just written to the glasses browser's
`localStorage` and skipped locally. So it works whether or not you are signed
in, and whether or not you own the playlist (nothing on YouTube is modified).
The flip side: "removed" means removed from this player on this device;
clearing the browser's storage brings everything back, and it does not sync
across devices. If `localStorage` is unavailable the feature quietly degrades
to session-only (no error, still nothing modified on YouTube).

To bring a `consume` playlist's finished videos back, run
`glassesForget('<playlist id>')` in the browser console (the id is the
`list`/`name` from `PLAYLISTS`).

## YouTube mode — currently walled off on the glasses

YouTube's anti-bot system ("Sign in to confirm you're not a bot") has been
blocking the glasses browser's fingerprint outright: every video errors
with code 150 in the embed, the plain youtube.com pages are walled too, it
follows the device across Wi-Fi/LTE, and Google sign-in does not complete
on the glasses, so the one documented cure is unavailable. Nothing a web
page can change (host, referrer, cookies, tokens, headers) gets around
that — it has to be fixed between Meta and YouTube, or the flag has to
lift on its own. The player detects the pattern (3 refused videos in a
row), stops skip-looping, and says so on the lens.

Config knobs at the top of the script in `index.html`:

- `PLAYLISTS` — the list of playlists shown on the selection screen. Add a
  `{ name: 'My Mix', list: 'PLxxxxxxxx' }` entry for each YouTube playlist;
  add `consume: true` to auto-remove finished videos (see above).
- `SHUFFLE` — `true` for random order (both kinds)

## Self-hosted mode — cannot be blocked

Put a `videos.json` at the repo root listing the files to play, in order:

```json
[
  { "title": "First clip",  "src": "videos/first.mp4" },
  { "title": "Second clip", "src": "videos/second.mp4" }
]
```

Then commit the files under `videos/`. On the next load a **Self-hosted**
entry appears on the selection screen alongside the YouTube playlists, with
the same controls. Press 2x again to return to normal speed. The playlist
loops at the end and unplayable entries are skipped. Delete `videos.json`
to drop the Self-hosted entry.

To hard-code self-hosted playlists instead of using `videos.json`, add
`{ name: '...', videos: [ { title, src }, ... ] }` entries directly to
`PLAYLISTS`.

Practical notes:

- GitHub Pages serves files up to 100 MB each; encode for the glasses
  (H.264 MP4, ~600px wide, AAC audio) and most clips stay well under it.
- `src` can also be a full URL on another host, but that host must allow
  cross-origin media; same-repo files avoid the issue entirely.
- Only add content you have the right to copy. Your own YouTube uploads
  can be downloaded legitimately from YouTube Studio; ripping other
  people's videos is against YouTube's terms.
