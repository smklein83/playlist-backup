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
import os
import re
import sys
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser

FEEDS_FILE = 'feeds.json'
OUT_FILE = 'podcasts.json'
EPISODES_PER_SHOW = 25
# A browser-like UA: some hosts (e.g. Substack behind Cloudflare) 403 non-browser agents.
UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36')
ITUNES_NS = '{http://www.itunes.com/dtds/podcast-1.0.dtd}'
CONTENT_NS = '{http://purl.org/rss/1.0/modules/content/}'


def http_get(url, accept=None):
    req = urllib.request.Request(url, headers={
        'User-Agent': UA,
        'Accept-Language': 'en-US,en;q=0.9',
    })
    if accept:
        req.add_header('Accept', accept)
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read()


def itunes(path):
    data = json.loads(http_get('https://itunes.apple.com/' + path,
                               accept='application/json').decode('utf-8', 'replace'))
    return data.get('results') or []


def resolve_feed(show):
    """Return (feed_url, resolved_name). feedEnv > explicit feed > iTunes id > search."""
    if show.get('feedEnv'):
        # Private/paid feed URL kept in an env var (a GitHub Actions Secret), so
        # the token never lives in the repo. Empty/unset -> skip quietly.
        return (os.environ.get(show['feedEnv'], '').strip() or None), show.get('name')
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


class _Text(HTMLParser):
    """Collapse post HTML to readable plain text for text-to-speech."""
    def __init__(self):
        HTMLParser.__init__(self, convert_charrefs=True)
        self.parts, self.skip = [], 0

    def handle_starttag(self, tag, attrs):
        if tag in ('script', 'style'):
            self.skip += 1
        elif tag in ('p', 'br', 'div', 'li', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'tr'):
            self.parts.append('\n')

    def handle_endtag(self, tag):
        if tag in ('script', 'style') and self.skip:
            self.skip -= 1

    def handle_data(self, data):
        if not self.skip:
            self.parts.append(data)


def html_to_text(s):
    if not s:
        return ''
    p = _Text()
    try:
        p.feed(s)
        out = ''.join(p.parts)
    except Exception:
        out = re.sub(r'<[^>]+>', ' ', s)
    out = re.sub(r'[ \t]+', ' ', out)
    out = re.sub(r'\n\s*\n+', '\n\n', out)
    return out.strip()


def parse_feed(xml_bytes, limit, include_articles=False):
    root = ET.fromstring(xml_bytes)
    rows = []
    for it in root.findall('.//item'):
        raw_date = text(it, 'pubDate')
        ts, iso = -1.0, raw_date
        try:
            if raw_date:
                dt = parsedate_to_datetime(raw_date)
                ts, iso = dt.timestamp(), dt.isoformat()
        except Exception:
            pass
        title = text(it, 'title') or 'Untitled'
        enc = it.find('enclosure')
        if enc is not None and enc.get('url'):
            etype = enc.get('type', '')
            rows.append((ts, {
                'kind': 'video' if etype.startswith('video') else 'audio',
                'title': title,
                'src': enc.get('url'),
                'type': etype,
                'date': iso,
                'duration': text(it, 'duration', ITUNES_NS),
            }))
        elif include_articles:                 # text post — keep it for read-aloud
            body = html_to_text(text(it, 'encoded', CONTENT_NS) or text(it, 'description'))
            if body:
                rows.append((ts, {
                    'kind': 'article',
                    'title': title,
                    'date': iso,
                    'text': body[:20000],
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
        if show.get('feedEnv') and not os.environ.get(show['feedEnv'], '').strip():
            print('  - %-22s private feed: secret %s not set — skipping' % (name, show['feedEnv']),
                  file=sys.stderr)
            continue
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
                EPISODES_PER_SHOW, include_articles=bool(show.get('articles')))
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
