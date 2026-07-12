#!/usr/bin/env python3
"""
Build podcasts.json for the glasses audio app.

For each show in feeds.json this resolves an RSS feed (an explicit URL, an
iTunes podcast id, or an iTunes search), downloads it, and writes the latest
episodes (title, audio URL, date, duration) to podcasts.json.

It runs server-side — locally, or in GitHub Actions — so there is no browser
CORS problem: the app only ever reads the same-origin podcasts.json and streams
the audio URLs directly (media elements don't enforce CORS).

stdlib only, no pip installs. Run from the repo root:  python3 feed2json.py
"""

import json
import sys
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime

FEEDS_FILE = 'feeds.json'
OUT_FILE = 'podcasts.json'
EPISODES_PER_SHOW = 25
UA = 'glasses-podcasts/1.0 (+https://github.com/smklein83/playlist-backup)'
ITUNES_NS = '{http://www.itunes.com/dtds/podcast-1.0.dtd}'


def http_get(url, accept=None):
    req = urllib.request.Request(url, headers={'User-Agent': UA})
    if accept:
        req.add_header('Accept', accept)
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read()


def itunes(path):
    data = json.loads(http_get('https://itunes.apple.com/' + path,
                               accept='application/json').decode('utf-8', 'replace'))
    return data.get('results') or []


def resolve_feed(show):
    """Return (feed_url, resolved_name). Explicit feed > iTunes id > search."""
    if show.get('feed'):
        return show['feed'], show.get('name')
    if show.get('itunesId'):
        res = itunes('lookup?id=%s&entity=podcast' % show['itunesId'])
        if res:
            return res[0].get('feedUrl'), res[0].get('collectionName')
    term = show.get('search') or show.get('name') or ''
    res = itunes('search?' + urllib.parse.urlencode(
        {'term': term, 'entity': 'podcast', 'limit': 1}))
    if res:
        return res[0].get('feedUrl'), res[0].get('collectionName')
    return None, None


def text(el, tag, ns=''):
    child = el.find(ns + tag)
    return (child.text or '').strip() if child is not None else ''


def parse_feed(xml_bytes, limit):
    root = ET.fromstring(xml_bytes)
    rows = []
    for it in root.findall('.//item'):
        enc = it.find('enclosure')
        if enc is None or not enc.get('url'):
            continue                       # no downloadable media on this item
        raw_date = text(it, 'pubDate')
        ts, iso = -1.0, raw_date
        try:
            if raw_date:
                dt = parsedate_to_datetime(raw_date)
                ts, iso = dt.timestamp(), dt.isoformat()
        except Exception:
            pass
        rows.append((ts, {
            'title': text(it, 'title') or 'Untitled',
            'src': enc.get('url'),
            'type': enc.get('type', ''),
            'date': iso,
            'duration': text(it, 'duration', ITUNES_NS),
        }))
    rows.sort(key=lambda r: r[0], reverse=True)   # newest first, whatever the feed order
    return [d for _, d in rows[:limit]]


def main():
    try:
        with open(FEEDS_FILE, encoding='utf-8') as f:
            feeds = json.load(f)
    except FileNotFoundError:
        print('No %s — nothing to do.' % FEEDS_FILE, file=sys.stderr)
        feeds = []

    shows = []
    for show in feeds:
        name = show.get('name') or show.get('search') or 'Show'
        try:
            feed_url, resolved = resolve_feed(show)
        except Exception as e:
            print('  ! %-22s resolve failed: %s' % (name, e), file=sys.stderr)
            feed_url, resolved = show.get('feed'), None
        if not feed_url:
            print('  ! %-22s no feed found — skipping' % name, file=sys.stderr)
            continue
        try:
            episodes = parse_feed(
                http_get(feed_url, accept='application/rss+xml, application/xml, text/xml'),
                EPISODES_PER_SHOW)
        except Exception as e:
            print('  ! %-22s fetch/parse failed: %s' % (name, e), file=sys.stderr)
            continue
        if not episodes:
            print('  ! %-22s feed had no playable episodes' % name, file=sys.stderr)
            continue
        shows.append({'name': name, 'feed': feed_url, 'episodes': episodes})
        print('  ok %-22s %d episodes  [%s]' % (name, len(episodes), resolved or feed_url))

    with open(OUT_FILE, 'w', encoding='utf-8') as f:
        json.dump({'updated': int(time.time()), 'shows': shows},
                  f, ensure_ascii=False, indent=2)
    print('Wrote %s: %d show(s).' % (OUT_FILE, len(shows)))


if __name__ == '__main__':
    main()
