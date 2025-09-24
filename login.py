#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
import json
import time
import hmac
import hashlib
import uuid
import random
import sys
from typing import Optional, Dict, Any, Tuple

import requests

API_URL = "https://i.instagram.com/api/{version}/"
V = "v1"
USER_AGENT = "Instagram 123.0.0.0 Android (30/11; 420dpi; 1080x1920; Google; Pixel; sailfish; qcom; en_US)"
IG_SIG_KEY = "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
SIG_KEY_VERSION = "4"
IG_CAPABILITIES = "3brTvw"
APPLICATION_ID = "567067343352427"
FB_HTTP_ENGINE = "Liger"

COOKIE_JSON_PATH = "cookie.json"

# ---------- Utilities ----------

def generate_uuid(return_hex: bool = False, seed: Optional[str] = None) -> str:
    if seed:
        m = hashlib.md5()
        m.update(seed.encode("utf-8"))
        new_uuid = uuid.UUID(m.hexdigest())
    else:
        new_uuid = uuid.uuid1()
    return new_uuid.hex if return_hex else str(new_uuid)

def generate_device_id(seed: Optional[str] = None) -> str:
    return "android-%s" % generate_uuid(True, (seed or "")[:16])

def generate_adid(seed: Optional[str] = None, username: Optional[str] = None, dsuser: Optional[str] = None) -> str:
    modified_seed = seed or dsuser or username or generate_uuid()
    sha2 = hashlib.sha256()
    sha2.update(modified_seed.encode("utf-8"))
    modified_seed = sha2.hexdigest()
    return generate_uuid(False, modified_seed)

def default_headers(useragent: str, igcap: str, appid: str) -> Dict[str, str]:
    return {
        "User-Agent": useragent,
        "Connection": "close",
        "Accept": "*/*",
        "Accept-Language": "en-US",
        "Accept-Encoding": "gzip, deflate",
        "X-IG-Capabilities": igcap,
        "X-IG-Connection-Type": "WIFI",
        "X-IG-Connection-Speed": f"{random.randint(1000,5000)}kbps",
        "X-IG-App-ID": appid,
        "X-IG-Bandwidth-Speed-KBPS": "-1.000",
        "X-IG-Bandwidth-TotalBytes-B": "0",
        "X-IG-Bandwidth-TotalTime-MS": "0",
        "X-FB-HTTP-Engine": FB_HTTP_ENGINE,
    }

def sign_params(signature_key: str, key_version: str, params: dict) -> Dict[str, str]:
    json_params = json.dumps(params, separators=(",", ":"))
    mac = hmac.new(signature_key.encode("ascii"), json_params.encode("ascii"), digestmod=hashlib.sha256).hexdigest()
    return {
        "ig_sig_key_version": key_version,
        "signed_body": f"{mac}.{json_params}",
    }

def get_cookie_value(jar: requests.cookies.RequestsCookieJar, key: str, domain: str = "instagram.com") -> Optional[str]:
    now = int(time.time())
    eternity = now + 100 * 365 * 24 * 60 * 60
    # Prefer latest-expiring cookie for the domain
    for c in sorted(jar, key=lambda c: c.expires or eternity, reverse=True):
        if c.expires and c.expires < now:
            continue
        cookiedomain = c.domain[1:] if c.domain.startswith(".") else c.domain
        if not domain.endswith(cookiedomain):
            continue
        if c.name.lower() == key.lower():
            return c.value
    return None

# ---------- Cookie JSON Helpers ----------

def write_cookie_json(sessionid: str, csrftoken: str, mid: str, ds_user_id: str,
                      per_cookie_expiry: Optional[Dict[str, Optional[int]]] = None) -> None:
    now = int(time.time())
    per_cookie_expiry = per_cookie_expiry or {}

    expiries = []
    for k in ("sessionid", "csrftoken", "mid", "ds_user_id"):
        v = per_cookie_expiry.get(k)
        if isinstance(v, int) and v > now:
            expiries.append(v)
    # Fallback: 25 days, typically less than some official cookie lifetimes but safe
    overall_expiry = min(expiries) if expiries else now + 25 * 24 * 60 * 60

    data = {
        "iat": now,
        "overall_expiry": overall_expiry,
        "cookies": {
            "sessionid": sessionid or "",
            "csrftoken": csrftoken or "",
            "mid": mid or "",
            "ds_user_id": ds_user_id or ""
        },
        "per_cookie_expiry": {
            "sessionid": per_cookie_expiry.get("sessionid"),
            "csrftoken": per_cookie_expiry.get("csrftoken"),
            "mid": per_cookie_expiry.get("mid"),
            "ds_user_id": per_cookie_expiry.get("ds_user_id")
        }
    }
    with open(COOKIE_JSON_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def read_cookie_json() -> Optional[Dict[str, Any]]:
    try:
        with open(COOKIE_JSON_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None

def cookie_json_valid(d: Optional[Dict[str, Any]]) -> bool:
    if not isinstance(d, dict):
        return False
    now = int(time.time())
    overall = d.get("overall_expiry")
    c = (d.get("cookies") or {})
    required_ok = all(k in c and isinstance(c.get(k), str) and c.get(k) for k in ("sessionid", "csrftoken", "mid", "ds_user_id"))
    return bool(required_ok and isinstance(overall, int) and overall > now)

# ---------- Login Core ----------

class LoginError(Exception):
    pass

def login_instagram(username: str, password: str, timeout_prelogin: int = 10, timeout_login: int = 20) -> Tuple[str, str, str, str]:
    """
    Perform the mobile-app-like login and return tuple:
    (sessionid, csrftoken, mid, ds_user_id)
    Raises LoginError on failure with meaningful message.
    """
    s = requests.Session()
    s.headers.update(default_headers(USER_AGENT, IG_CAPABILITIES, APPLICATION_ID))

    # Pre-login to fetch CSRF
    guid = generate_uuid(True)
    prelogin_url = API_URL.format(version=V) + "si/fetch_headers/"
    prelogin_query = {"challenge_type": "signup", "guid": generate_uuid(True)}
    try:
        r = s.post(prelogin_url, params=prelogin_query, headers={"Content-type": "application/x-www-form-urlencoded; charset=UTF-8"}, timeout=timeout_prelogin)
    except requests.RequestException as e:
        raise LoginError(f"Network error during prelogin: {e}")

    csrftoken = get_cookie_value(s.cookies, "csrftoken")
    if not csrftoken:
        raise LoginError("Unable to get CSRF from prelogin.")

    device_id = generate_device_id()
    login_params = {
        "device_id": device_id,
        "guid": generate_uuid(False),
        "adid": generate_adid(username=username),
        "phone_id": generate_uuid(False, seed=device_id),
        "csrftoken": csrftoken,
        "username": username,
        "password": password,
        "login_attempt_count": 0,
    }
    signed = sign_params(IG_SIG_KEY, SIG_KEY_VERSION, login_params)
    login_url = API_URL.format(version=V) + "accounts/login/"

    try:
        r = s.post(login_url, data=signed, headers={"Content-type": "application/x-www-form-urlencoded; charset=UTF-8"}, timeout=timeout_login)
    except requests.RequestException as e:
        raise LoginError(f"Network error during login: {e}")

    # Attempt JSON parse, but tolerate non-JSON
    try:
        j = r.json()
    except Exception:
        j = {"status": "unknown", "text": r.text}

    # Detect common error states
    if r.status_code != 200:
        raise LoginError(f"HTTP {r.status_code} during login: {j}")

    if not isinstance(j, dict):
        raise LoginError(f"Unexpected login response: {j}")

    if j.get("two_factor_required"):
        raise LoginError("Two-factor authentication required on this account; interactive flow not implemented.")

    if j.get("challenge_required"):
        raise LoginError("Challenge required by Instagram; solve in-app and retry.")

    if not j.get("logged_in_user", {}).get("pk"):
        raise LoginError(f"Unable to login: {j}")

    # Extract cookies
    sessionid = get_cookie_value(s.cookies, "sessionid", domain="instagram.com")
    csrftoken = get_cookie_value(s.cookies, "csrftoken", domain="instagram.com")
    mid = get_cookie_value(s.cookies, "mid", domain="instagram.com")
    dsuserid = get_cookie_value(s.cookies, "ds_user_id", domain="instagram.com")

    if not all([sessionid, csrftoken, mid, dsuserid]):
        raise LoginError("Login succeeded but required cookies are missing.")

    return (sessionid, csrftoken, mid, dsuserid)

# ---------- CLI ----------

def main():
    ap = argparse.ArgumentParser(description="Instagram app login and dump cookies (standalone)")
    ap.add_argument("-u", "--username", required=True)
    ap.add_argument("-p", "--password", required=True)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    try:
        sessionid, csrftoken, mid, dsuserid = login_instagram(args.username, args.password)
        if args.json:
            print(json.dumps(
                {"sessionid": sessionid, "csrftoken": csrftoken, "mid": mid, "ds_user_id": dsuserid},
                ensure_ascii=False
            ))
        else:
            print(sessionid)
            print(csrftoken)
            print(mid)
            print(dsuserid)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
