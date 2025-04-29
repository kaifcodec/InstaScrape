import requests
import json
import re
import cookie
import sys
from tqdm import tqdm  # Import tqdm for progress bar

# === Configuration ===
PARENT_QUERY_HASH   = "97b41c52301f77ce508f55e66d17620e"
COMMENTS_PER_PAGE   = 50

def extract_shortcode(url):
    m = re.search(r"instagram\.com/reel/([^/?]+)", url)
    return m.group(1) if m else None

def build_headers(shortcode, cookies_str):
    return {
        "User-Agent": "Mozilla/5.0 (Linux; Android 13; SM-A125F) AppleWebKit/537.36 "
                      "(KHTML, like Gecko) Chrome/122.0.0.0 Mobile Safari/537.36",
        "Accept": "*/*",
        "Accept-Language": "en-US,en;q=0.9",
        "X-Requested-With": "XMLHttpRequest",
        "X-IG-App-ID": "936619743392459",
        "Referer": f"https://www.instagram.com/reel/{shortcode}/",
        "Cookie": cookies_str
    }

def graphql_request(query_hash, variables, headers):
    var_str = json.dumps(variables, separators=(",", ":"))
    url = (
        f"https://www.instagram.com/graphql/query/"
        f"?query_hash={query_hash}"
        f"&variables={requests.utils.quote(var_str)}"
    )
    r = requests.get(url, headers=headers)
    if r.status_code != 200:
        print(f"[!] HTTP {r.status_code} error for {query_hash}: {r.text}")
        sys.exit(1)
    return r.json()

def fetch_parent_comments(shortcode, headers):
    all_comments = []
    has_next = True
    cursor = ""
    page_count = 0  # To track the number of pages fetched

    # Create a progress bar based on the unknown number of comments
    progress_bar = tqdm(total=100, desc="Fetching Comments", unit="page")

    while has_next:
        vars = {"shortcode": shortcode, "first": COMMENTS_PER_PAGE}
        if cursor:
            vars["after"] = cursor

        data = graphql_request(PARENT_QUERY_HASH, vars, headers)

        try:
            edge_info = data["data"]["shortcode_media"]["edge_media_to_parent_comment"]
            edges = edge_info["edges"]
            for edge in edges:
                text = edge["node"]["text"]
                user = edge["node"]["owner"]["username"]
                all_comments.append(f"{user}: {text}")
        except KeyError as e:
            print(f"[!] Error parsing comment data: {e}")
            break

        page_info = edge_info["page_info"]
        has_next = page_info["has_next_page"]
        cursor = page_info["end_cursor"]

        page_count += 1
        progress_bar.n = page_count * COMMENTS_PER_PAGE  # Update the progress bar
        progress_bar.last_print_n = progress_bar.n
        progress_bar.update(0)  # Update without adding new value

    progress_bar.close()
    return all_comments

def main():
    reel_url = input("Enter Instagram Reel URL: ").strip()
    sessionid = cookie.sessionid
    ds_user_id = cookie.ds_user_id
    csrftoken = cookie.csrftoken
    mid = cookie.mid

    shortcode = extract_shortcode(reel_url)
    if not shortcode:
        print("[!] Invalid URL format.")
        exit()

    cookies_str = f"sessionid={sessionid}; ds_user_id={ds_user_id}; csrftoken={csrftoken}; mid={mid};"
    headers = build_headers(shortcode, cookies_str)

    comments = fetch_parent_comments(shortcode, headers)

    if comments:
        with open("reel_comments.txt", "w", encoding="utf-8") as f:
            f.write("\n".join(comments))
        print(f"[+] Saved {len(comments)} comments to reel_comments.txt")
    else:
        print("[!] No comments found or failed.")

if __name__ == "__main__":
    main()
