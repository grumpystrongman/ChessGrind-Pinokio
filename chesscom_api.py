"""Chess.com public read-only API client and SQLite-backed Rapid game importer.

No password or API key is required. Requests are made serially. The client's
user-agent identifies the application and includes a public profile as contact.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import re
import sqlite3
import time
from urllib.parse import urlparse

import requests

BASE = 'https://api.chess.com/pub'
USERNAME_PATTERN = re.compile(r'^[A-Za-z0-9_-]{3,25}$')


class ChessComError(RuntimeError):
    pass


class ChessComClient:
    def __init__(self, username=None, *, session=None, pause=0.2, retries=3):
        if not isinstance(username,str) or not USERNAME_PATTERN.fullmatch(username):
            raise ValueError('Invalid Chess.com username.')
        self.username = username.lower()
        self.session = session or requests.Session()
        self.pause = pause
        self.retries = retries
        contact = os.getenv('CHESS_GRIND_CONTACT', f'https://www.chess.com/member/{self.username}')
        self.session.headers.update({
            'User-Agent': f'ChessGrindAgent/0.2 (personal study; user: {self.username}; contact: {contact})',
            'Accept': 'application/json',
        })

    def get(self, path):
        if not path.startswith('/player/') or '?' in path or '#' in path:
            raise ValueError('Only Chess.com player API paths are supported.')
        url = BASE + path
        for attempt in range(self.retries + 1):
            try:
                response = self.session.get(url, timeout=(10, 30))
            except requests.RequestException as exc:
                if attempt < self.retries:
                    time.sleep(min(2 ** attempt, 8))
                    continue
                raise ChessComError(f'Network error reaching Chess.com: {exc}') from exc
            if response.status_code in (429, 500, 502, 503, 504) and attempt < self.retries:
                retry_after = response.headers.get('Retry-After', '')
                try:
                    delay = min(20.0, max(0.0, float(retry_after)))
                except ValueError:
                    delay = min(2 ** attempt, 8)
                time.sleep(delay)
                continue
            if response.status_code == 403:
                raise ChessComError('Chess.com returned HTTP 403 (access denied). Set CHESS_GRIND_CONTACT to your email or contact URL and retry. The service may also block your network/IP; this cannot be fixed by changing code alone.')
            if response.status_code == 404:
                raise ChessComError(f'Chess.com returned HTTP 404 for {path}. Confirm the username exists.')
            if not response.ok:
                raise ChessComError(f'Chess.com returned HTTP {response.status_code} for {path}: {response.text[:180]}')
            try:
                result = response.json()
            except ValueError as exc:
                raise ChessComError(f'Chess.com returned non-JSON data for {path}') from exc
            if not isinstance(result, dict):
                raise ChessComError(f'Unexpected response format for {path}')
            if self.pause:
                time.sleep(self.pause)
            return result
        raise ChessComError(f'Unable to fetch {path} after retries.')

    def profile(self):
        return self.get(f'/player/{self.username}')

    def stats(self):
        return self.get(f'/player/{self.username}/stats')

    def archives(self):
        payload = self.get(f'/player/{self.username}/games/archives')
        urls = payload.get('archives', [])
        safe = []
        for url in urls:
            parsed = urlparse(url)
            if parsed.scheme != 'https' or parsed.netloc != 'api.chess.com':
                continue
            match = re.fullmatch(r'/pub/player/([A-Za-z0-9_-]+)/games/(\d{4})/(\d{2})', parsed.path)
            if match and match.group(1).lower() == self.username and 1 <= int(match.group(3)) <= 12:
                safe.append((int(match.group(2)), int(match.group(3))))
        return sorted(set(safe), reverse=True)

    def monthly_games(self, year, month):
        if not (2000 <= year <= 2100 and 1 <= month <= 12):
            raise ValueError('Invalid archive month')
        payload = self.get(f'/player/{self.username}/games/{year}/{month:02d}')
        games = payload.get('games', [])
        if not isinstance(games, list):
            raise ChessComError('Unexpected games response: expected a list')
        return games


def ensure_schema(con):
    con.executescript('''
      CREATE TABLE IF NOT EXISTS chesscom_players (
        username TEXT PRIMARY KEY, synced_at TEXT NOT NULL,
        profile_json TEXT NOT NULL, stats_json TEXT NOT NULL
      );
      CREATE TABLE IF NOT EXISTS chesscom_games (
        game_id TEXT PRIMARY KEY, username TEXT NOT NULL,
        year INTEGER NOT NULL, month INTEGER NOT NULL,
        end_time INTEGER, time_class TEXT, time_control TEXT,
        white_username TEXT, black_username TEXT, white_rating INTEGER,
        black_rating INTEGER, result TEXT, pgn TEXT NOT NULL,
        url TEXT, imported_at TEXT NOT NULL
      );
      CREATE INDEX IF NOT EXISTS chesscom_games_user_date
        ON chesscom_games(username, end_time DESC);
    ''')
    con.commit()


def rapid_rating(stats):
    return (stats.get('chess_rapid') or {}).get('last', {}).get('rating')


def sync(con, username=None, *, max_rapid=200, client=None, all_types=False):
    if max_rapid < 1:
        raise ValueError('--max-games must be greater than zero')
    ensure_schema(con)
    client = client or ChessComClient(username)
    profile = client.profile()
    stats = client.stats()
    archives = client.archives()
    now = dt.datetime.now(dt.timezone.utc).isoformat()
    con.execute('''INSERT INTO chesscom_players(username,synced_at,profile_json,stats_json)
      VALUES(?,?,?,?) ON CONFLICT(username) DO UPDATE SET
      synced_at=excluded.synced_at, profile_json=excluded.profile_json,
      stats_json=excluded.stats_json''',
      (client.username, now, json.dumps(profile), json.dumps(stats)))
    con.commit()

    scanned = 0
    added = 0
    found = 0
    counts = {}
    for year, month in archives:
        games = client.monthly_games(year, month)
        # Newest first; API data is not guaranteed to be returned in date order.
        for game in sorted(games, key=lambda g: g.get('end_time') or 0, reverse=True):
            kind = str(game.get('time_class', '')).lower()
            if kind != 'rapid' and not all_types:
                continue
            if kind not in ('rapid', 'blitz', 'bullet', 'daily'):
                continue
            white, black = game.get('white') or {}, game.get('black') or {}
            if client.username not in (str(white.get('username', '')).lower(), str(black.get('username', '')).lower()):
                continue
            game_pgn = game.get('pgn')
            if not game_pgn:
                continue
            found += 1
            counts[kind] = counts.get(kind, 0) + 1
            game_id = game.get('uuid') or game.get('url')
            if not game_id:
                continue
            own = white if str(white.get('username', '')).lower() == client.username else black
            cur = con.execute('''INSERT OR IGNORE INTO chesscom_games
              (game_id,username,year,month,end_time,time_class,time_control,
               white_username,black_username,white_rating,black_rating,result,pgn,url,imported_at)
              VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
              (game_id, client.username, year, month, game.get('end_time'), kind,
               str(game.get('time_control', '')), white.get('username'), black.get('username'),
               white.get('rating'), black.get('rating'), own.get('result'), game_pgn,
               game.get('url'), now))
            added += max(0, cur.rowcount)
            if found >= max_rapid:
                break
        scanned += 1
        con.commit()
        if found >= max_rapid:
            break
    return {'username':client.username, 'rating':rapid_rating(stats),
            'months_scanned':scanned, 'rapid_games_seen':counts.get('rapid', 0),
            'games_seen':found, 'by_type':counts, 'new_games':added,
            'archive_months_available':len(archives)}


def status(con, username=None):
    ensure_schema(con)
    if not username:
        # Backward-compatible read-only status on databases with exactly one imported player.
        # Never use this fallback for syncing or first-run account selection.
        known=con.execute("SELECT username FROM chesscom_players LIMIT 2").fetchall()
        if len(known)!=1:
            return {"username":"","synced":False,"stored_rapid_games":0}
        username=known[0]["username"]
    username = username.lower()
    row = con.execute('SELECT * FROM chesscom_players WHERE username=?', (username,)).fetchone()
    n = con.execute('SELECT COUNT(*) FROM chesscom_games WHERE username=? AND time_class=\'rapid\'', (username,)).fetchone()[0]
    by_type={r['time_class']:r['n'] for r in con.execute('''SELECT time_class,COUNT(*) AS n
      FROM chesscom_games WHERE username=? GROUP BY time_class''',(username,))}
    if row is None:
        return {'username':username, 'synced':False, 'stored_rapid_games':n}
    stats = json.loads(row['stats_json'])
    return {'username':username,'synced':True, 'synced_at':row['synced_at'],
            'rapid_rating':rapid_rating(stats), 'stored_rapid_games':n,
            'rapid_last_played':(stats.get('chess_rapid') or {}).get('last',{}).get('date'),
            'rapid_best':(stats.get('chess_rapid') or {}).get('best',{}).get('rating'),
            'all_games_imported':sum(by_type.values()),'games_by_type':by_type}


def export_pgn(con, username, destination):
    ensure_schema(con)
    rows = con.execute('SELECT pgn FROM chesscom_games WHERE username=? ORDER BY end_time DESC',
                       (username.lower(),)).fetchall()
    from pathlib import Path
    target=Path(destination)
    target.parent.mkdir(parents=True,exist_ok=True)
    target.write_text('\n\n'.join(r['pgn'].strip() for r in rows)+'\n', encoding='utf-8')
    return len(rows)
