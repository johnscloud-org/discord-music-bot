#!/usr/bin/env python3
"""Setup the discord-music-bot repo: upload all workspace files via GitHub API, then create issues."""

import json
import os
import sys
from urllib import request, error

# Load token
token = ""
token = os.environ.get("GITHUB_TOKEN", "")
if not token:
    # Source .env to load the token
    for line in open("/opt/data/.env"):
        if line.startswith("GITHUB_TOKEN="):
            token = line.strip().split("=", 1)[1]
            break
if not token:
    print("ERROR: GITHUB_TOKEN not found")
    sys.exit(1)

BASE = "https://api.github.com"
AUTH = {"Authorization": f"token {token}"}
ORG_REPO = "johnscloud-org/discord-music-bot"

def api(method, path, data=None):
    url = BASE + path
    body = json.dumps(data).encode() if data else None
    req = request.Request(url, data=body, headers={**AUTH, "Content-Type": "application/json"} if body else AUTH, method=method)
    try:
        resp = request.urlopen(req)
        return json.loads(resp.read())
    except error.HTTPError as e:
        print(f"API error {e.code}: {e.read().decode()}")
        raise

def upload_file(filepath):
    """Upload a file to the repo via GitHub API (create or update)."""
    rel_path = os.path.relpath(filepath, "/opt/data/kanban/workspaces/t_d7d3d895")
    content = open(filepath, "rb").read()
    
    # Skip if it's a .pyc file
    if filepath.endswith(".pyc"):
        return
    
    # Get file SHA if it exists
    sha = None
    try:
        info = api("GET", f"/repos/{ORG_REPO}/contents/{rel_path}")
        sha = info.get("sha")
    except error.HTTPError as e:
        if e.code != 404:
            raise
    
    import base64
    encoded = base64.b64encode(content).decode()
    
    payload = {
        "message": f"Add {rel_path}",
        "content": encoded,
    }
    if sha:
        payload["sha"] = sha
    
    try:
        api("PUT", f"/repos/{ORG_REPO}/contents/{rel_path}", payload)
        print(f"  Uploaded: {rel_path}")
    except error.HTTPError as e:
        print(f"  ERROR uploading {rel_path}: {e.read().decode()}")

def create_issue(title, body, labels=None):
    data = {"title": title, "body": body}
    if labels:
        data["labels"] = labels
    result = api("POST", f"/repos/{ORG_REPO}/issues", data)
    print(f"  Created issue #{result['number']}: {result['html_url']}")

# Step 1: Upload all source files
print("Uploading workspace files...")
workspace = "/opt/data/kanban/workspaces/t_d7d3d895"
skip_dirs = {".venv", "__pycache__"}
for root, dirs, files in os.walk(workspace):
    # Skip hidden dirs and .venv
    dirs[:] = [d for d in dirs if d not in skip_dirs and not d.startswith('.')]
    for fname in sorted(files):
        fpath = os.path.join(root, fname)
        upload_file(fpath)

# Step 2: Add repo description
print("\nUpdating repo description...")
api("PATCH", f"/repos/{ORG_REPO}", {"description": "Discord music bot with YouTube and local file streaming support"})

# Step 3: Create issues
print("\nCreating issues...")

issues = [
    {
        "title": "Add SoundCloud source adapter",
        "body": "Implement a `SoundCloudSource` class inheriting from `AudioSource` similar to `YouTubeSource`, using yt-dlp's SoundCloud support to stream audio.\n\nAcceptance criteria:\n- Resolves SoundCloud track URLs to direct audio streams\n- Extracts metadata (title, author, duration)\n- Handles unavailable tracks gracefully\n- Follows the same error handling pattern as `YouTubeSource`",
        "labels": ["enhancement", "sources"]
    },
    {
        "title": "Add Twitch stream source adapter",
        "body": "Implement a `TwitchSource` class for streaming audio from Twitch channels/videos.\n\nAcceptance criteria:\n- Resolves Twitch VOD/channel URLs to audio streams\n- Handles live vs. VOD streams appropriately\n- Extracts stream metadata\n- Graceful handling of offline streams",
        "labels": ["enhancement", "sources"]
    },
    {
        "title": "Add playlist support for TrackQueue",
        "body": "Extend `TrackQueue` to handle multi-track playlists from YouTube and SoundCloud sources.\n\nAcceptance criteria:\n- Detects when a source URL is a playlist\n- Queues all tracks from the playlist in order\n- Tracks current position within playlist\n- Allows requeue of next track",
        "labels": ["enhancement"]
    },
    {
        "title": "Add voice channel persistence across bot restarts",
        "body": "Implement a simple persistence layer (SQLite or JSON file) to save/restore voice channel state.\n\nAcceptance criteria:\n- Saves current voice channel connection and queue on shutdown\n- Restores state on bot restart\n- Graceful handling of stale references (e.g., bot was removed from channel)",
        "labels": ["enhancement"]
    },
    {
        "title": "Add skip/queue command parameters",
        "body": "Enhance `/play` and `/skip` slash commands with optional parameters.\n\nAcceptance criteria:\n- `/play [url] --position N` to insert track at specific queue position\n- `/skip [N]` to skip N tracks at once\n- `/queue list [N]` to show next N tracks in the queue",
        "labels": ["enhancement", "commands"]
    },
    {
        "title": "Implement volume control slash command",
        "body": "Add a `/volume` command to adjust playback volume.\n\nAcceptance criteria:\n- `/volume [0-100]` sets absolute volume level\n- `/volume +10` / `/volume -10` adjusts relative volume\n- Volume persists across track changes in the queue",
        "labels": ["enhancement", "commands"]
    },
]

for issue in issues:
    try:
        create_issue(issue["title"], issue["body"], issue.get("labels"))
    except Exception as e:
        print(f"  Failed to create issue: {e}")

print("\nDone!")
