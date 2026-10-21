#!/usr/bin/env python3
"""Graphical interface for the Automated File Backup and Restore Utility.

    python3 gui.py               # opens the interface in your web browser
    python3 gui.py --port 9000   # use a different port
    python3 gui.py --no-browser  # only print the address

The interface is a web page, but nothing goes on the internet: this script runs a
small web server on 127.0.0.1 (this computer only) with Python's built-in
http.server, and the page in web/ talks to it. Every button calls the same `core`
functions as the command line, so there is still nothing to install.

How a button press flows
    web/app.js  --POST /api/backup {source, dest, keep, ...}-->  Handler.do_POST
    api_backup() --> core.create_backup() --> result formatted like the CLI --> JSON
    web/app.js shows the text in the Output box and reloads the version table

OS concepts
- ThreadingHTTPServer answers each request in its own thread, so the page stays
  responsive while a long backup runs.
- WORK_LOCK (mutual exclusion) lets only one backup/restore/verify/status touch the
  backup folder at a time; a second request is told to wait instead of racing it.
- The server only listens on 127.0.0.1, and every API call must carry a random token
  that is handed only to the page this server served, so another website open in
  the same browser cannot trigger a restore.
"""

import argparse
import io
import json
import os
import secrets
import shutil
import subprocess
import sys
import threading
import webbrowser
from contextlib import redirect_stdout
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import demo_tools
import make_sample_data
from backup_tool import (
    DEFAULT_KEEP,
    print_backup_result,
    print_restore_result,
    print_status,
    print_verify_result,
)
from core import (
    BackupError,
    changes_since_backup,
    create_backup,
    list_backups,
    restore_backup,
    verify_backup,
)
from core.backup import DEFAULT_EXCLUDES
from core.utils import IN_PROGRESS_PREFIX, LOG_NAME, MANIFEST_NAME, human_size
from core.versioning import load_manifest, resolve_name

HERE = os.path.dirname(os.path.abspath(__file__))
WEB_DIR = os.path.join(HERE, "web")
STATIC_FILES = {                       # the only files the server will hand out
    "/": ("index.html", "text/html; charset=utf-8"),
    "/style.css": ("style.css", "text/css; charset=utf-8"),
    "/app.js": ("app.js", "text/javascript; charset=utf-8"),
}
DEFAULT_PORT = 8765
TOKEN = secrets.token_urlsafe(16)      # new every time the server starts
WORK_LOCK = threading.Lock()


# ---------------------------------------------------------------- helpers

def captured(print_func, result):
    """Run one of backup_tool's print_* helpers and return its text instead of printing it."""
    buf = io.StringIO()
    with redirect_stdout(buf):
        print_func(result)
    return buf.getvalue().strip("\n")


def path_from(req, key, what=None):
    """Read a folder path from the request; if `what` is given, the path is required."""
    path = os.path.expanduser(str(req.get(key) or "").strip())
    if what and not path:
        raise BackupError(f"Choose the {what} first.")
    return path


# ---------------------------------------------------------------- API: reading

def api_config(req):
    demo = os.path.join(HERE, "sample_data")
    has_demo = os.path.isdir(demo)     # handy for the demo: pre-fill the sample folders
    return {
        "source": demo if has_demo else "",
        "dest": os.path.join(HERE, "my_backups") if has_demo else "",
        "keep": DEFAULT_KEEP,
        "default_excludes": DEFAULT_EXCLUDES,
        "can_pick": sys.platform == "darwin",
    }


def api_versions(req):
    dest = path_from(req, "dest")
    backups = list_backups(dest) if dest else []
    return {"versions": [{
        "name": b["name"],
        "mode": b["mode"],
        "files": b["files"],
        "size": human_size(b["total_size"]),
        "copied": b["stats"].get("copied", "-"),
        "linked": b["stats"].get("linked", "-"),
    } for b in backups]}


def api_log(req):
    path = os.path.join(path_from(req, "dest"), LOG_NAME)
    if not os.path.isfile(path):
        return {"lines": []}
    with open(path, encoding="utf-8") as fh:
        return {"lines": fh.read().splitlines()}


def api_version_files(req):
    """Everything stored in one version, for the 'Files in this version' table."""
    dest = path_from(req, "dest", "backup location")
    name = resolve_name(dest, req.get("version") or None)
    files = load_manifest(dest, name)["files"]
    return {"version": name, "path": os.path.join(dest, name), "files": [{
        "path": rel,
        "size": human_size(info["size"]),
        "stored": info.get("stored", "copied"),
        "modified": datetime.fromtimestamp(info["mtime"]).strftime("%Y-%m-%d %H:%M"),
    } for rel, info in sorted(files.items())]}


def api_files(req):
    """Every file and folder stored in a version, for the 'only this file' suggestions."""
    dest = path_from(req, "dest", "backup location")
    name = resolve_name(dest, req.get("version") or None)
    files = sorted(load_manifest(dest, name)["files"])
    folders = sorted({"/".join(f.split("/")[:i]) for f in files for i in range(1, f.count("/") + 1)})
    return {"version": name, "paths": [f + "/" for f in folders] + files}


# ---------------------------------------------------------------- API: actions

def api_backup(req):
    source = path_from(req, "source", "folder to back up")
    dest = path_from(req, "dest", "backup location")
    try:
        keep = int(req.get("keep", DEFAULT_KEEP))
    except (TypeError, ValueError):
        raise BackupError("Versions to keep must be a whole number.")
    extra = [p.strip() for p in str(req.get("exclude") or "").split(",") if p.strip()]
    res = create_backup(source, dest, keep=keep, excludes=DEFAULT_EXCLUDES + extra,
                        mode="full" if req.get("full") else "incremental")
    return {"text": captured(print_backup_result, res), "problem": bool(res["errors"])}


def api_status(req):
    res = changes_since_backup(path_from(req, "source", "folder to back up"),
                               path_from(req, "dest", "backup location"))
    return {"text": captured(print_status, res)}


def api_restore(req):
    res = restore_backup(path_from(req, "dest", "backup location"),
                         name=req.get("version") or None,
                         target=path_from(req, "target") or None,
                         only=str(req.get("only") or "").strip() or None,
                         overwrite=bool(req.get("overwrite")))
    return {"text": captured(print_restore_result, res), "problem": bool(res["failed"])}


def api_verify(req):
    rep = verify_backup(path_from(req, "dest", "backup location"), req.get("version") or None)
    problem = bool(rep["missing"] or rep["corrupted"])
    text = captured(print_verify_result, rep)
    if problem:
        text += "\n  Tip: run a Full backup to start a clean chain of versions."
    return {"text": text, "problem": problem}


PICK_SCRIPT = """
on run argv
    set startFolder to item 1 of argv
    activate
    if startFolder is "" then
        set chosen to choose folder with prompt "Choose a folder"
    else
        set chosen to choose folder with prompt "Choose a folder" default location (POSIX file startFolder)
    end if
    return POSIX path of chosen
end run
"""


def api_pick(req):
    """Show the native macOS folder chooser (via AppleScript) and return the chosen path."""
    if sys.platform != "darwin":
        raise BackupError("The Choose… dialog only works on macOS. Type the path instead.")
    start = path_from(req, "start")
    while start and not os.path.isdir(start):        # open at the nearest existing folder
        start = os.path.dirname(start) if start != os.path.dirname(start) else ""
    proc = subprocess.run(["osascript", "-e", PICK_SCRIPT, start],
                          capture_output=True, text=True)
    if proc.returncode != 0:
        if "-128" in proc.stderr:                    # the user pressed Cancel
            return {"path": None}
        raise BackupError(f"Could not open the chooser: {proc.stderr.strip()}")
    path = proc.stdout.strip().rstrip("/") or "/"
    return {"path": path, "has_other_files": holds_other_files(path)}


def holds_other_files(folder):
    """True if `folder` contains anything besides backup versions, backup.log and crash leftovers."""
    for name in os.listdir(folder):
        full = os.path.join(folder, name)
        if name in (LOG_NAME, ".DS_Store") or name.startswith(IN_PROGRESS_PREFIX):
            continue
        if os.path.isdir(full) and os.path.isfile(os.path.join(full, MANIFEST_NAME)):
            continue
        return True
    return False


def api_reveal(req):
    """Open a folder in Finder (macOS) so you can look at the real files."""
    if sys.platform != "darwin":
        raise BackupError("Opening folders only works on macOS.")
    path = path_from(req, "path", "folder")
    if not os.path.isdir(path):
        raise BackupError(f"Folder not found: {path}")
    subprocess.run(["open", path])
    return {}


# ---------------------------------------------------------------- API: Test Lab (demo_tools.py)

def api_source_files(req):
    return {"files": demo_tools.source_files(path_from(req, "source"))}


def api_lab_edit(req):
    return {"text": demo_tools.edit_source_file(path_from(req, "source", "folder to back up"),
                                                path_from(req, "dest", "backup location"),
                                                req.get("file") or "")}


def api_lab_delete_source(req):
    return {"text": demo_tools.delete_source_file(path_from(req, "source", "folder to back up"),
                                                  path_from(req, "dest", "backup location"),
                                                  req.get("file") or "")}


def api_lab_add(req):
    return {"text": demo_tools.add_source_file(path_from(req, "source", "folder to back up"))}


def api_lab_corrupt(req):
    return {"text": demo_tools.corrupt_backup_file(path_from(req, "dest", "backup location"),
                                                   req.get("version") or None, req.get("file") or "")}


def api_lab_delete_backup(req):
    return {"text": demo_tools.delete_backup_file(path_from(req, "dest", "backup location"),
                                                  req.get("version") or None, req.get("file") or "")}


def api_lab_crash(req):
    return {"text": demo_tools.simulate_crash(path_from(req, "dest", "backup location"))}


def api_lab_attack(req):
    return {"text": demo_tools.path_traversal_attack(path_from(req, "dest", "backup location"),
                                                     req.get("version") or None)}


def api_lab_links(req):
    return {"text": demo_tools.hard_link_report(path_from(req, "dest", "backup location"),
                                                req.get("file") or "")}


def api_lab_sample(req, reset=False):
    """(Re)create the demo folder next to gui.py; with reset, delete it and its backups first."""
    source, dest = os.path.join(HERE, "sample_data"), os.path.join(HERE, "my_backups")
    if reset:
        shutil.rmtree(source, ignore_errors=True)
        shutil.rmtree(dest, ignore_errors=True)
    buf = io.StringIO()
    with redirect_stdout(buf):
        make_sample_data.main(source)
    os.makedirs(dest, exist_ok=True)                 # so "Choose…" opens right in it
    text = "✔ " + buf.getvalue().strip()
    if reset:
        text = "✔ Deleted the demo folders sample_data/ and my_backups/.\n" + text
    return {"text": text + "\n  Next: Create Backup.", "source": source, "dest": dest}


# (function, needs WORK_LOCK) for every POST /api/<name>
API = {
    "config": (api_config, False),
    "versions": (api_versions, False),
    "log": (api_log, False),
    "files": (api_files, False),
    "pick": (api_pick, False),
    "backup": (api_backup, True),
    "status": (api_status, True),
    "restore": (api_restore, True),
    "verify": (api_verify, True),
    "source_files": (api_source_files, False),
    "lab_links": (api_lab_links, False),
    "version_files": (api_version_files, False),
    "reveal": (api_reveal, False),
    "lab_edit": (api_lab_edit, True),
    "lab_delete_source": (api_lab_delete_source, True),
    "lab_add": (api_lab_add, True),
    "lab_corrupt": (api_lab_corrupt, True),
    "lab_delete_backup": (api_lab_delete_backup, True),
    "lab_crash": (api_lab_crash, True),
    "lab_attack": (api_lab_attack, True),
    "lab_sample": (api_lab_sample, True),
    "lab_reset": (lambda req: api_lab_sample(req, reset=True), True),
}


# ---------------------------------------------------------------- HTTP server

class Handler(BaseHTTPRequestHandler):
    server_version = "BackupGUI"

    def _host_ok(self):
        port = self.server.server_address[1]
        return self.headers.get("Host") in (f"127.0.0.1:{port}", f"localhost:{port}")

    def _send(self, status, body, content_type):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, status, payload):
        self._send(status, json.dumps(payload).encode("utf-8"), "application/json")

    def do_GET(self):
        entry = STATIC_FILES.get(self.path.split("?")[0])
        if not self._host_ok():
            return self._send(403, b"Forbidden", "text/plain")
        if not entry:
            return self._send(404, b"Not found", "text/plain")
        name, content_type = entry
        with open(os.path.join(WEB_DIR, name), "rb") as fh:
            body = fh.read()
        if name == "index.html":
            body = body.replace(b"{{TOKEN}}", TOKEN.encode())
        self._send(200, body, content_type)

    def do_POST(self):
        if not self._host_ok() or self.headers.get("X-Token") != TOKEN:
            return self._json(403, {"ok": False, "error": "Forbidden"})
        entry = API.get(self.path[len("/api/"):]) if self.path.startswith("/api/") else None
        if not entry:
            return self._json(404, {"ok": False, "error": "Unknown request"})
        func, needs_lock = entry
        try:
            length = int(self.headers.get("Content-Length") or 0)
            req = json.loads(self.rfile.read(length) or b"{}")
            if not needs_lock:
                data = func(req)
            elif WORK_LOCK.acquire(blocking=False):
                try:
                    data = func(req)
                finally:
                    WORK_LOCK.release()
            else:
                raise BackupError("Another operation is still running. Wait for it to finish.")
            self._json(200, {"ok": True, **data})
        except BackupError as exc:
            self._json(400, {"ok": False, "error": str(exc)})
        except Exception as exc:          # unexpected: report it instead of dropping the request
            self._json(500, {"ok": False, "error": f"{type(exc).__name__}: {exc}"})

    def log_message(self, fmt, *args):   # keep the terminal quiet (actions go to backup.log)
        pass


def main(argv=None):
    parser = argparse.ArgumentParser(description="Open the backup utility's graphical interface")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT,
                        help=f"port to use (default {DEFAULT_PORT})")
    parser.add_argument("--no-browser", action="store_true", help="don't open a browser window")
    args = parser.parse_args(argv)

    try:
        server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    except OSError:                       # port already in use: let the OS pick a free one
        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    url = f"http://127.0.0.1:{server.server_address[1]}/"
    print(f"Backup utility GUI running at {url}")
    print("Keep this window open while you use it. Press Ctrl+C here to stop.")
    if not args.no_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
