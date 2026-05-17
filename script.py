#!/usr/bin/env python3

import json, logging, os, secrets, webbrowser, requests, time
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlencode, urlparse, parse_qs

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)


def load_env(path=".env"):
    env = {}
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            key, _, value = line.partition("=")
            env[key.strip()] = value.strip().strip('"').strip("'")
    return env


cfg = load_env()
BASE = "https://api.intra.42.fr"
REDIRECT = "http://localhost:8080/callback"
SCOPE = "public projects"
TOKEN_FILE = ".token.json"
CHECK_EVERY_MIN = 2
BUFFER_MINUTES = 60
REQUEST_TIMEOUT = 30
MAX_RETRIES = 5


def request_with_retry(method, url, **kw):
    kw.setdefault("timeout", REQUEST_TIMEOUT)
    for attempt in range(MAX_RETRIES):
        r = requests.request(method, url, **kw)
        if r.status_code != 429:
            return r
        wait = float(r.headers.get("Retry-After", 1))
        log.warning("429 rate-limited, sleeping %.1fs (attempt %d)", wait, attempt + 1)
        time.sleep(wait)
    return r


def iso(dt):
    return dt.strftime("%Y-%m-%dT%H:%M:%S.000Z")


def login_in_browser():
    state = secrets.token_urlsafe(16)
    auth_url = f"{BASE}/oauth/authorize?" + urlencode(
        {
            "client_id": cfg["UID"],
            "redirect_uri": REDIRECT,
            "response_type": "code",
            "scope": SCOPE,
            "state": state,
        }
    )

    received = {}

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            q = parse_qs(urlparse(self.path).query)
            received["code"] = q.get("code", [None])[0]
            received["state"] = q.get("state", [None])[0]
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"OK, you can close this tab.")

        def log_message(self, format: str, *args) -> None:
            pass

    server = HTTPServer(("localhost", 8080), Handler)
    log.info("Opening browser for login...")
    webbrowser.open(auth_url)
    server.handle_request()

    if received.get("state") != state:
        raise RuntimeError("OAuth state mismatch")
    if not received.get("code"):
        raise RuntimeError("OAuth callback missing code")
    r = request_with_retry(
        "POST",
        f"{BASE}/oauth/token",
        data={
            "grant_type": "authorization_code",
            "client_id": cfg["UID"],
            "client_secret": cfg["SECRET"],
            "code": received["code"],
            "redirect_uri": REDIRECT,
        },
    )
    r.raise_for_status()
    return r.json()


def refresh(tok):
    r = request_with_retry(
        "POST",
        f"{BASE}/oauth/token",
        data={
            "grant_type": "refresh_token",
            "refresh_token": tok["refresh_token"],
            "client_id": cfg["UID"],
            "client_secret": cfg["SECRET"],
        },
    )
    r.raise_for_status()
    return r.json()


def get_token():
    tok = None
    if os.path.exists(TOKEN_FILE):
        with open(TOKEN_FILE) as f:
            tok = json.load(f)
    if tok and tok["created_at"] + tok["expires_in"] - 60 > datetime.now().timestamp():
        log.info("Using access token from .token.json")
        return tok["access_token"]

    if tok and "refresh_token" in tok:
        try:
            tok = refresh(tok)
            log.info("Using refresh token from .token.json to get new access token")
        except requests.HTTPError:
            tok = None

    if not tok:
        log.info("No valid access or refresh token in .token.json, need to login")
        tok = login_in_browser()

    tmp = TOKEN_FILE + ".tmp"
    with open(tmp, "w") as f:
        json.dump(tok, f)
    os.chmod(tmp, 0o600)
    os.replace(tmp, TOKEN_FILE)
    return tok["access_token"]


def _run_cycle(headers):
    now = datetime.now(timezone.utc)
    window_end = now + timedelta(hours=24)
    cutoff = now + timedelta(minutes=BUFFER_MINUTES)

    r = request_with_retry(
        "GET",
        f"{BASE}/v2/me/slots",
        headers=headers,
        params={
            "range[begin_at]": f"{iso(now)},{iso(window_end)}",
            "page[size]": 100,
        },
    )
    r.raise_for_status()
    slots = sorted(r.json(), key=lambda x: x["begin_at"])

    print(f"\n[{now.astimezone():%H:%M:%S %Z}] {len(slots)} slot(s) in next 24h:")
    to_delete = []
    for s in slots:
        begin = datetime.fromisoformat(s["begin_at"])
        end   = datetime.fromisoformat(s["end_at"])
        tag = "DELETE" if begin < cutoff else "keep"
        if tag == "DELETE":
            to_delete.append(s)
        print(f"  {s['id']:>8}  {begin.astimezone():%H:%M} → {end.astimezone():%H:%M}  [{tag}]")

    for s in to_delete:
        r = request_with_retry("DELETE", f"{BASE}/v2/slots/{s['id']}", headers=headers)
        print(f"    deleted {s['id']} → {r.status_code}")


def cycle():
    for attempt in (1, 2):
        token = get_token()
        headers = {"Authorization": f"Bearer {token}"}
        try:
            _run_cycle(headers)
            return
        except requests.HTTPError as e:
            if e.response is not None and e.response.status_code == 401 and attempt == 1:
                log.warning("401 from API, invalidating cached token and retrying")
                try:
                    os.remove(TOKEN_FILE)
                except FileNotFoundError:
                    pass
                continue
            raise


def main():
    token = get_token()

    me = request_with_retry(
        "GET",
        f"{BASE}/v2/me",
        headers={"Authorization": f"Bearer {token}"},
    ).json()
    log.info("Logged in as %s (id %s)", me["login"], me["id"])

    log.info("Watching slots, checking every %d minute(s). Ctrl+C to stop.", CHECK_EVERY_MIN)
    try:
        while True:
            try:
                cycle()
            except Exception:
                log.exception("cycle error")
            time.sleep(CHECK_EVERY_MIN * 60)
    except KeyboardInterrupt:
        log.info("stopped")


if __name__ == "__main__":
    main()
