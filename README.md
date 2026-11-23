# secnews-digest

A small, read-only, open-source tool that builds a daily digest of new posts from a few
public security subreddits, with every entry linking back to the original Reddit post.

It is a personal, non-commercial project.

## What it does

- Reads new public posts from configured subreddits through Reddit's Data API, using
  application-only OAuth (client credentials) and a descriptive User-Agent.
- Stores only the post id, subreddit, title, permalink, creation time and self text.
- Writes one Markdown digest per day, grouped by subreddit, each line linking to the post.

## What it never does

- Post, comment, vote, send messages or moderate.
- Collect user profiles, author names, scores or comments in bulk.
- Use Reddit data to train any AI model, or sell or redistribute it.

## Respecting Reddit and its users

- Posts older than the retention window (30 days by default) are deleted.
- `prune` asks Reddit about every stored post and deletes any that was removed or deleted.
- Requests are paced (one every 2 seconds) and total well under 500 a day with the
  default schedule.

## Setup

Requires Python 3.11 or newer; no third-party packages.

1. Create a "script" app at https://www.reddit.com/prefs/apps after your Data API access is approved.
2. `cp config.example.toml config.toml` and set `client_id`.
3. `export SECNEWS_CLIENT_SECRET=...` (the secret is never written to a file).

## Usage

```
python3 secnews_digest.py collect   # every 30 to 60 minutes
python3 secnews_digest.py prune     # once a day
python3 secnews_digest.py digest    # once a day
```

Example cron:

```
*/45 * * * *  cd ~/secnews-digest && python3 secnews_digest.py collect
5 0 * * *     cd ~/secnews-digest && python3 secnews_digest.py prune && python3 secnews_digest.py digest
```

## License

MIT. See [LICENSE](LICENSE).

This project is not affiliated with Reddit. Use of the Reddit API is subject to Reddit's
Developer Terms, Data API Terms and Responsible Builder Policy.
