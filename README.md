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

# Podcast player (audio) — `podcasts.html`

A sibling app at **`/podcasts.html`** that plays podcasts instead of YouTube.
Podcasts are distributed as open RSS feeds with direct audio URLs, so this
path **never touches YouTube and can't be bot-walled** — no sign-in, no embed,
nothing to flag. It reuses the same lens UI and input model (swipe = move,
pinch = select), with a **shows → episodes → player** flow, per-episode
**resume**, and a ✓ on finished episodes.

## How the data gets there (no browser CORS problem)

A browser on `github.io` can't reliably `fetch()` a cross-origin RSS feed
(most hosts don't send CORS headers). So the feeds are fetched **server-side**
and baked into a static `podcasts.json` that the app reads same-origin; the
audio itself streams live from the publisher (media elements don't enforce
CORS). Only the *episode list* is as fresh as the last refresh — the audio is
never stale, and these shows publish at most daily.

```
feeds.json  ──►  feed2json.py  ──►  podcasts.json  ──►  podcasts.html
 (shows)         (Action / local)     (committed)         (on Pages)
```

## Choosing shows — `feeds.json`

Each entry resolves to a feed in priority order: explicit `feed` URL, then
`itunesId`, then an iTunes `search` term.

```json
[
  { "name": "The Ezra Klein Show", "search": "The Ezra Klein Show" },
  { "name": "All-In",              "itunesId": 1502871393 },
  { "name": "My Show",             "feed": "https://example.com/rss" }
]
```

`search` is convenient but fuzzy — after the first refresh, check the Action
log (it prints the resolved feed for each show) and pin anything that matched
the wrong podcast with an exact `feed` URL or `itunesId`.

## Private / paid feeds (Substack, Patreon) — via GitHub Secrets

Paid podcasts hand you a **private RSS URL** with a secret token baked in (no
password). To use one without committing the token to this public repo, a feed
entry can read its URL from an environment variable instead:

```json
{ "name": "My Paid Show", "feedEnv": "SUBSTACK_FEED" }
```

Setup:

1. **Get the private feed URL** — e.g. a paid Substack's "Listen in podcast
   app" / RSS link, or Patreon's "Connect to podcast app" URL.
2. Repo **Settings → Secrets and variables → Actions → New repository secret**.
   Name it **`SUBSTACK_FEED`**, paste the URL, save.
3. `feeds.json` already ships the entry above. Rename `"name"` to the show if
   you like. The fetcher reads the URL from the Secret at build time — the
   token never touches the repo (it's skipped with a log line until the Secret
   exists).
4. Run the workflow (or wait for the 6h cron); the show appears.

Add more private feeds by creating another Secret, mapping it under `env:` in
`.github/workflows/refresh-podcasts.yml`, and adding another `feedEnv` entry.

**Security caveat:** the Secret hides the feed *token*, but the generated
`podcasts.json` is public (GitHub Pages) and lists the episode media URLs. If
those URLs are themselves tokenized, they're exposed to anyone reading the repo.
For genuinely private content use a **private repo** (Pages then needs a paid
GitHub plan), or download those episodes and self-host them.

## Articles read aloud (text-to-speech)

Add `"articles": true` to a feed entry (e.g. a Substack) and the fetcher also
keeps its **text posts** — the feed items with no audio file. In the player
those are marked `📄 ~N min read`, and selecting one has the glasses **read it
aloud** via the browser's `speechSynthesis` — no video, no squinting at the
lens. Play/Pause and the `2x` read-speed control work; the body is chunked by
sentence so long posts don't hit the browser's per-utterance limit. If the
glasses browser has no text-to-speech it says so instead of failing silently.
Note: Substack often truncates article bodies in RSS, so some arrive as
previews.

## Refreshing

- **Automatic:** `.github/workflows/refresh-podcasts.yml` runs every 6 hours
  (and on any change to `feeds.json`), regenerates `podcasts.json`, commits it,
  and then **requests a GitHub Pages rebuild** so the *live* site serves the
  fresh file. Scheduled runs only fire from the **default branch**, so this
  starts working once the workflow is on `main`.
  - The explicit rebuild is required because the job commits with the built-in
    `GITHUB_TOKEN`, and GitHub does **not** auto-trigger a "Deploy from a branch"
    Pages build for `GITHUB_TOKEN` pushes. Without it the repo's `podcasts.json`
    keeps advancing while the deployed app stays frozen at the last human push.
    (This needs Pages **Source: "Deploy from a branch"**; if you use
    **Source: "GitHub Actions"** instead, deploy with the `actions/deploy-pages`
    action rather than the REST rebuild step.)
  - If every feed fails in one run (e.g. the runner IP gets rate-limited),
    `feed2json.py` keeps the last good `podcasts.json` and exits non-zero instead
    of publishing an empty playlist.
- **On demand:** the same workflow has a "Run workflow" button
  (`workflow_dispatch`).
- **Locally:** `python3 feed2json.py` (stdlib only) writes `podcasts.json`;
  commit it yourself.

Controls match the video player: Prev, Play/Pause, Next, `<15`, `>30`, `2x`.
**Prev ×2** within 2 seconds jumps back to the episode list.

## Battery: lights-out and background audio

Since it's audio-only, the display is pure waste while listening. Two things
help:

- **Lights out** — a button on the player turns the whole screen black (which
  is transparent / near-zero light on the additive display) while audio keeps
  playing. Any tap/swipe/pinch wakes it.
- **Media Session** — the app registers as OS audio playback (title + play /
  pause / next / prev / seek handlers) so sound can continue when the display
  sleeps and any hardware media keys work. It deliberately takes **no** screen
  Wake Lock, so nothing forces the display to stay on.

Whether the glasses fully power the display down on their own while audio keeps
playing is up to their firmware — worth a quick on-device check.
