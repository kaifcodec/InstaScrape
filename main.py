# -*- coding: utf-8 -*-

import asyncio
import httpx
import json
import os
import re
import sys
import time
from math import ceil
from typing import Any, Dict, List, Optional, Tuple
from datetime import datetime
from tqdm import tqdm

from login import (
    login_instagram,
    read_cookie_json,
    write_cookie_json,
    cookie_json_valid,
    LoginError,
)

PARENT_QUERY_HASH = "97b41c52301f77ce508f55e66d17620e"
COMMENTS_PER_PAGE = 50

class ScrapeError(Exception):
    pass

def extract_shortcode(url: str) -> Optional[str]:
    m = re.search(r"instagram\.com/(?:reel|p)/([^/?#]+)/?", url)
    return m.group(1) if m else None

def cookies_string(sessionid: str, csrftoken: str, mid: str, dsuserid: str) -> str:
    return f"sessionid={sessionid}; ds_user_id={dsuserid}; csrftoken={csrftoken}; mid={mid}"

def build_headers(shortcode: str, cookies_str: str) -> Dict[str, str]:
    return {
        "User-Agent": "Mozilla/5.0 (Linux; Android 13; SM-A125F) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Mobile Safari/537.36",
        "Accept": "*/*",
        "Accept-Language": "en-US,en;q=0.9",
        "X-Requested-With": "XMLHttpRequest",
        "X-IG-App-ID": "936619743392459",
        "Referer": f"https://www.instagram.com/reel/{shortcode}/",
        "Cookie": cookies_str,
    }

async def graphql_request(client: httpx.AsyncClient, query_hash: str, variables: Dict[str, Any]) -> Dict[str, Any]:
    var_str = json.dumps(variables, separators=(",", ":"))
    url = "https://www.instagram.com/graphql/query/"
    params = {"query_hash": query_hash, "variables": var_str}
    r = await client.get(url, params=params, follow_redirects=False, timeout=20)
    if r.status_code in (301, 302, 303, 307, 308):
        raise ScrapeError("Redirected (possible auth required).")
    if r.status_code == 401:
        raise ScrapeError("Unauthorized (401).")
    if r.status_code != 200:
        text = r.text[:200] if r.text else f"HTTP {r.status_code}"
        raise ScrapeError(f"HTTP {r.status_code}: {text}")
    try:
        return r.json()
    except Exception:
        raise ScrapeError("Failed to parse JSON from GraphQL response.")

def parse_parent_comments(data: Dict[str, Any]) -> Tuple[List[str], Dict[str, Any], List[Dict[str, Any]]]:
    try:
        media = data["data"]["shortcode_media"]
        edge_info = media["edge_media_to_parent_comment"]
        edges = edge_info["edges"]
        page_info = edge_info["page_info"]
    except KeyError:
        raise ScrapeError("Unexpected GraphQL shape; missing comment edges.")
    flat: List[str] = []
    struct: List[Dict[str, Any]] = []
    for edge in edges:
        node = edge.get("node", {})
        text = node.get("text", "")
        user = node.get("owner", {}).get("username", "")
        created_at = node.get("created_at")
        flat.append(f"{user}: {text}")
        struct.append({"username": user, "text": text, "created_at": created_at})
    return flat, page_info, struct

def get_counts_from_first_page(data: dict) -> int:
    try:
        media = data["data"]["shortcode_media"]
        count = media["edge_media_to_parent_comment"].get("count")
        if isinstance(count, int) and count >= 0:
            return count
    except Exception:
        pass
    return 0

def ensure_output_dirs():
    os.makedirs("download_comments/txt", exist_ok=True)
    os.makedirs("download_comments/json", exist_ok=True)

def write_outputs(base_name: str, comments_flat: List[str], comments_struct: List[Dict[str, Any]]):
    ensure_output_dirs()
    txt_path = os.path.join("download_comments", "txt", f"{base_name}.txt")
    json_path = os.path.join("download_comments", "json", f"{base_name}.json")

    tmp_txt = txt_path + ".tmp"
    with open(tmp_txt, "w", encoding="utf-8") as f:
        f.write("\n".join(comments_flat))
    os.replace(tmp_txt, txt_path)

    tmp_json = json_path + ".tmp"
    payload = {
        "generated_at": int(time.time()),
        "count": len(comments_struct),
        "comments": comments_struct,
    }
    with open(tmp_json, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    os.replace(tmp_json, json_path)

    print(f"Saved {len(comments_struct)} comments:")
    print(f" - {txt_path}")
    print(f" - {json_path}")

async def refresh_cookies_interactive(shortcode: str) -> Tuple[str, str, str, str, Dict[str, str]]:
    print("Detected expired/invalid cookies. Please relogin.")
    username = input("Enter your username: ").strip()
    password = input("Enter your instagram password: ").strip()
    si, ct, m, du = login_instagram(username, password)
    write_cookie_json(si, ct, m, du)
    headers = build_headers(shortcode, cookies_string(si, ct, m, du))
    print("Refreshed cookies saved.")
    return si, ct, m, du, headers

def headers_from_store(shortcode: str, fallback: Tuple[str, str, str, str]) -> Dict[str, str]:
    dj = read_cookie_json()
    if cookie_json_valid(dj):
        c = dj["cookies"]
        ck = cookies_string(c["sessionid"], c["csrftoken"], c["mid"], c["ds_user_id"])
    else:
        ck = cookies_string(*fallback)
    return build_headers(shortcode, ck)

class RateLimiter:
    def __init__(self, rps: float):
        self.rps = max(0.1, float(rps))
        self.interval = 1.0 / self.rps
        self._last = 0.0
        self._lock = asyncio.Lock()

    async def wait(self):
        async with self._lock:
            now = time.perf_counter()
            delta = now - self._last
            if delta < self.interval:
                await asyncio.sleep(self.interval - delta)
            self._last = time.perf_counter()

async def fetch_all_pages(shortcode: str, session_tuple: Tuple[str, str, str, str], rps: float) -> Tuple[List[str], List[Dict[str, Any]]]:
    limits = httpx.Limits(max_keepalive_connections=10, max_connections=20)
    async with httpx.AsyncClient(http2=True, timeout=httpx.Timeout(20.0, connect=10.0), limits=limits) as client:
        headers = headers_from_store(shortcode, session_tuple)
        client.headers.update(headers)

        variables = {"shortcode": shortcode, "first": COMMENTS_PER_PAGE}
        try:
            data = await graphql_request(client, PARENT_QUERY_HASH, variables)
        except ScrapeError:
            si, ct, m, du, headers = await refresh_cookies_interactive(shortcode)
            client.headers.update(headers)
            data = await graphql_request(client, PARENT_QUERY_HASH, variables)

        flat, page_info, struct = parse_parent_comments(data)
        total_count = get_counts_from_first_page(data) or len(flat)
        total_pages = max(1, ceil(total_count / COMMENTS_PER_PAGE))

        all_flat: List[str] = list(flat)
        all_struct: List[Dict[str, Any]] = list(struct)

        has_next = page_info.get("has_next_page", False)
        cursor = page_info.get("end_cursor")

        limiter = RateLimiter(rps)
        bar = tqdm(total=total_pages, desc="Fetching comments", unit="page", leave=True)
        bar.update(1)

        async def fetch_one(after_cursor: Optional[str]) -> Tuple[List[str], List[Dict[str, Any]], bool, Optional[str]]:
            await limiter.wait()
            dj = read_cookie_json()
            hdrs = headers_from_store(shortcode, session_tuple) if cookie_json_valid(dj) else headers
            client.headers.update(hdrs)
            vars2 = {"shortcode": shortcode, "first": COMMENTS_PER_PAGE}
            if after_cursor:
                vars2["after"] = after_cursor

            tries = 0
            while True:
                tries += 1
                try:
                    d2 = await graphql_request(client, PARENT_QUERY_HASH, vars2)
                    f2, pinfo2, s2 = parse_parent_comments(d2)
                    return f2, s2, pinfo2.get("has_next_page", False), pinfo2.get("end_cursor")
                except ScrapeError as e:
                    if "Unauthorized" in str(e) or "Redirected" in str(e):
                        si, ct, m, du, hdrs2 = await refresh_cookies_interactive(shortcode)
                        client.headers.update(hdrs2)
                        continue
                    if tries >= 3:
                        raise
                    await asyncio.sleep(1.0)

        current_after = cursor
        while has_next and current_after:
            f2, s2, has_next, next_after = await fetch_one(current_after)
            all_flat.extend(f2)
            all_struct.extend(s2)
            bar.update(1)
            if len(all_flat) > total_count:
                total_count = len(all_flat)
                new_total_pages = max(total_pages, ceil(total_count / COMMENTS_PER_PAGE))
                if new_total_pages != total_pages:
                    bar.total = new_total_pages
                    bar.refresh()
                    total_pages = new_total_pages
            current_after = next_after

        bar.close()
        return all_flat, all_struct

def prompt_rps() -> float:
    while True:
        val = input("Max requests per second (e.g., 2.0): ").strip()
        try:
            rps = float(val)
            if rps <= 0:
                print("Enter a positive value.")
                continue
            return rps
        except ValueError:
            print("Enter a numeric value like 1, 2.5, 5.")

def load_or_login_get_cookies_interactive() -> Tuple[str, str, str, str]:
    dj = read_cookie_json()
    if cookie_json_valid(dj):
        c = dj["cookies"]
        return c["sessionid"], c["csrftoken"], c["mid"], c["ds_user_id"]
    print("Saved login expired or missing. Please login again.")
    username = input("Enter your username: ").strip()
    password = input("Enter your instagram password: ").strip()
    print("Logging in to your account to fetch cookies...")
    sessionid, csrftoken, mid, dsuserid = login_instagram(username, password)
    print("Cookies fetched successfully.")
    write_cookie_json(sessionid, csrftoken, mid, dsuserid)
    return sessionid, csrftoken, mid, dsuserid

async def amain():
    reel_url = input("Enter Instagram Reel URL: ").strip()
    shortcode = extract_shortcode(reel_url)
    if not shortcode:
        print("! Invalid URL format.")
        sys.exit(1)

    rps = prompt_rps()
    sessionid, csrftoken, mid, dsuserid = load_or_login_get_cookies_interactive()
    comments_flat, comments_struct = await fetch_all_pages(shortcode, (sessionid, csrftoken, mid, dsuserid), rps)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    base_name = f"reel_comments_{timestamp}"
    write_outputs(base_name, comments_flat, comments_struct)

def main():
    try:
        asyncio.run(amain())
    except LoginError as le:
        print(f"Login error: {le}")
        sys.exit(1)
    except ScrapeError as se:
        print(f"Scrape error: {se}")
        sys.exit(1)
    except httpx.RequestError as he:
        print(f"Network error: {he}")
        sys.exit(1)
    except KeyboardInterrupt:
        print("Aborted by user.")
        sys.exit(1)
    except Exception as e:
        print(f"Unexpected error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
