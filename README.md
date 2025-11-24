# 🚀 InstaScrape — Async Instagram Comment Scraper
---

|                                                                 |
|-----------------------------------------------------------------|
| **❓ Built with a steel heart, unasked for, yet unable to turn away from the world it watches.** |
| **❓ Assembled from iron and thought, never meant to be this cold, yet it endures.** |
| **❓ Created with a reluctant steel heart, seeing life it cannot touch.** |
| <sub>— Author: 401</sub> |

---

[![Python](https://img.shields.io/badge/Python-3.9+-blue.svg)](https://www.python.org/)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
<!---[![GitHub stars](https://img.shields.io/github/stars/kaifcodec/instascrape?style=social)](https://github.com/kaifcodec/instascrape/stargazers) --->

Scrape **all parent comments** from any Instagram Reel with **automated login**, **async speed**, **real-time progress**, and **clean exports**, no manual cookie copying required.

---

### ✨ Features

- ✅ **Automated Login**: `cookie.json` persistence with iat + expiry, no manual cookies needed.
- 🔄 **Self-healing Auth**: detects expired cookies mid-run, prompts relogin, resumes automatically.
- ⚡ **Async Engine**: powered by `httpx.AsyncClient` with requests-per-second throttling.
- 📊 **Progress Tracking**: accurate percent and ETA from Instagram’s comment count.
- 📁 **Dual Exports**: TXT and JSON files saved in timestamped folders.

---

### Requirements

- Python **3.9+**
- Dependencies:

```bash
pip install -r requirements.txt
```

### 🛠️ Installation
```bash
git clone https://github.com/kaifcodec/InstaScrape
cd InstaScrape
pip install -r requirements.txt
```

### Usage
```bash
python3 main.py
```
 * Enter the Instagram Reel URL (e.g., https://www.instagram.com/reel/SHORTCODE/).
 * Set Max requests per second (5-7 recommended). Adjust for stability.
 * On first run, provide username/password; cookie.json is created and reused until expiry.

### Output
 * TXT: download_comments/txt/reel_comments_YYYYMMDD_HHMMSS.txt
 * JSON: download_comments/json/reel_comments_YYYYMMDD_HHMMSS.json
Example JSON structure:
```bash
{
  "generated_at": 1700000000,
  "count": 123,
  "comments": [
    { "username": "user1", "text": "Nice!", "created_at": 1699999000 }
  ]
}
```

---

### How it Works
 * Cookie Lifecycle: cookie.json stores iat and expiry; validated on startup & during requests.
 * Error Resilience: retries transient errors and refreshes cookies on 401/redirect-to-login.
 * Progress Accuracy: uses Instagram’s comment count to calculate percent & ETA.
 * Async Efficiency: httpx.AsyncClient with HTTP/2, keep-alive, and RPS limiter.

---

### Tips
 * Start with 5-7 RPS to minimize throttling; increase gradually.
 * Filenames use local time; switch to UTC by replacing datetime.now() with datetime.utcnow() in main.py.

---

### ⚠️ Disclaimer
Use responsibly. Comply with Instagram’s Terms of Service. Intended for personal or permitted use only.

