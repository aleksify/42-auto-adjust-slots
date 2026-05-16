#!/usr/bin/env python3

import requests


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

# Auth
token = requests.post(f"{BASE}/oauth/token", data={
    "grant_type": "client_credentials",
    "client_id": cfg["UID"],
    "client_secret": cfg["SECRET"],
}).json()["access_token"]

if cfg.get("ID") is None:
    r = requests.get(
        f"{BASE}/v2/users",
        headers={"Authorization": f"Bearer {token}"},
        params={"filter[login]": cfg["USERNAME"]},
    )
    cfg["ID"] = r.json()[0]["id"]
    print(f"\nYour ID: {cfg["ID"]}. You can hardcode it in .env to not make this request each time.\n")

print(cfg["ID"])
