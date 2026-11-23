#!/usr/bin/env python3
"""secnews-digest: a read-only daily digest of public security subreddits.

It only reads public posts through Reddit's Data API (application-only OAuth),
stores a minimal record of each post (id, subreddit, title, permalink, created
time, self text), drops anything older than the retention window or deleted on
Reddit, and writes one Markdown digest per day linking back to every post.

It never posts, comments, votes, messages, moderates or profiles users.

Usage:
    python3 secnews_digest.py collect    # fetch new posts (run every 30 to 60 min)
    python3 secnews_digest.py digest     # write today's digest
    python3 secnews_digest.py prune      # apply retention and remove deleted posts
"""
import base64
import datetime as dt
import json
import os
import sqlite3
import sys
import time
import tomllib
import urllib.parse
import urllib.request

VERSION = "0.1.0"
TOKEN_URL = "https://www.reddit.com/api/v1/access_token"
API = "https://oauth.reddit.com"
PAUSE_SECONDS = 2  # well under Reddit's rate limit


def load_config(path="config.toml"):
    with open(path, "rb") as f:
        cfg = tomllib.load(f)
    cfg["client_secret"] = os.environ.get("SECNEWS_CLIENT_SECRET", "")
    if not cfg.get("client_id") or not cfg["client_secret"]:
        sys.exit("client_id in config.toml and SECNEWS_CLIENT_SECRET in the environment are required")
    cfg["user_agent"] = f"script:secnews-digest:{VERSION} (by /u/{cfg.get('reddit_username', 'unknown')})"
    return cfg


def http_json(req):
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def token(cfg):
    """Application-only OAuth (client credentials): read-only, no user login."""
    basic = base64.b64encode(f"{cfg['client_id']}:{cfg['client_secret']}".encode()).decode()
    req = urllib.request.Request(
        TOKEN_URL,
        data=urllib.parse.urlencode({"grant_type": "client_credentials"}).encode(),
        headers={"Authorization": "Basic " + basic, "User-Agent": cfg["user_agent"]},
    )
    return http_json(req)["access_token"]


def api_get(cfg, bearer, path, params):
    url = f"{API}{path}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={"Authorization": "Bearer " + bearer, "User-Agent": cfg["user_agent"]})
    return http_json(req)


def db(cfg):
    con = sqlite3.connect(cfg.get("database", "secnews.db"))
    con.execute(
        """CREATE TABLE IF NOT EXISTS posts (
             id TEXT PRIMARY KEY, subreddit TEXT NOT NULL, title TEXT NOT NULL,
             permalink TEXT NOT NULL, created_utc REAL NOT NULL, selftext TEXT NOT NULL DEFAULT '')"""
    )
    return con


def collect(cfg):
    bearer = token(cfg)
    con = db(cfg)
    added = 0
    for sub in cfg["subreddits"]:
        listing = api_get(cfg, bearer, f"/r/{sub}/new", {"limit": cfg.get("posts_per_request", 25), "raw_json": 1})
        for child in listing.get("data", {}).get("children", []):
            p = child.get("data", {})
            # Only the minimal public fields; no author, no scores, no comments.
            row = (p.get("name"), p.get("subreddit"), p.get("title", ""), "https://www.reddit.com" + p.get("permalink", ""),
                   float(p.get("created_utc", 0)), (p.get("selftext") or "")[:2000])
            if row[0]:
                added += con.execute("INSERT OR IGNORE INTO posts VALUES (?,?,?,?,?,?)", row).rowcount
        time.sleep(PAUSE_SECONDS)
    con.commit()
    print(f"collected {added} new post(s) from {len(cfg['subreddits'])} subreddit(s)")


def prune(cfg):
    con = db(cfg)
    cutoff = time.time() - cfg.get("retention_days", 30) * 86400
    old = con.execute("DELETE FROM posts WHERE created_utc < ?", (cutoff,)).rowcount
    # Respect deletions: ask Reddit about stored posts and drop removed or deleted ones.
    ids = [r[0] for r in con.execute("SELECT id FROM posts")]
    removed = 0
    if ids:
        bearer = token(cfg)
        for i in range(0, len(ids), 100):
            batch = ids[i:i + 100]
            info = api_get(cfg, bearer, "/api/info", {"id": ",".join(batch), "raw_json": 1})
            alive = set()
            for child in info.get("data", {}).get("children", []):
                p = child.get("data", {})
                if not p.get("removed_by_category") and p.get("selftext") not in ("[deleted]", "[removed]"):
                    alive.add(p.get("name"))
            for pid in batch:
                if pid not in alive:
                    removed += con.execute("DELETE FROM posts WHERE id = ?", (pid,)).rowcount
            time.sleep(PAUSE_SECONDS)
    con.commit()
    print(f"pruned {old} expired and {removed} deleted or removed post(s)")


def digest(cfg, day=None):
    day = day or dt.datetime.now(dt.timezone.utc).date()
    start = dt.datetime.combine(day, dt.time(), dt.timezone.utc).timestamp()
    con = db(cfg)
    rows = con.execute(
        "SELECT subreddit, title, permalink FROM posts WHERE created_utc >= ? AND created_utc < ? ORDER BY subreddit, created_utc",
        (start, start + 86400),
    ).fetchall()
    out_dir = cfg.get("digest_dir", "digests")
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, f"{day.isoformat()}.md")
    lines = [f"# Security subreddits digest, {day.isoformat()}", ""]
    current = None
    for sub, title, link in rows:
        if sub != current:
            lines += ["", f"## r/{sub}", ""]
            current = sub
        lines.append(f"- [{title.replace(']', ')')}]({link})")
    if not rows:
        lines.append("No new posts.")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print(f"wrote {path} with {len(rows)} post(s)")


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd not in ("collect", "digest", "prune"):
        sys.exit(__doc__)
    cfg = load_config()
    {"collect": collect, "digest": digest, "prune": prune}[cmd](cfg)


if __name__ == "__main__":
    main()
