#!/usr/bin/env python3

import json, os, secrets, webbrowser, requests
from datetime import datetime
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlencode, urlparse, parse_qs


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
    print("Opening browser for login...")
    webbrowser.open(auth_url)
    server.handle_request()

    assert received["state"] == state, "state mismatch"
    r = requests.post(
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
    r = requests.post(
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
        print("Using access token from .token.json")
        return tok["access_token"]

    if tok and "refresh_token" in tok:
        try:
            tok = refresh(tok)
            print("Using refresh token from .token.json to get new access token")
        except requests.HTTPError:
            tok = None

    if not tok:
        print("No valid access or refresh token in .token.json, need to login")
        tok = login_in_browser()

    with open(TOKEN_FILE, "w") as f:
        json.dump(tok, f)
    return tok["access_token"]


token = get_token()

info = requests.get(
    f"{BASE}/oauth/token/info", headers={"Authorization": f"Bearer {token}"}
).json()
print(info)

me = requests.get(f"{BASE}/v2/me", headers={"Authorization": f"Bearer {token}"}).json()
print(f"Logged in as {me['login']} (id {me['id']})")
