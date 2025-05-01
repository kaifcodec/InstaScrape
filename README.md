# InstaScrape: Instagram Comment Scraper

Welcome to **InstaScrape** – a powerful Python script that allows you to scrape and download comments from Instagram Reels effortlessly! 📥💬

Ever wanted to grab all the comments on your favorite Instagram Reels, but found it tedious? Look no further! InstaScrape makes it quick, simple, and fun.

---

### 🚀 Features

- **Fetch Instagram Reels comments**: Grab all the parent comments on any Instagram Reel.
- **Save to file**: The comments are saved in a neat `.txt` file for your convenience.
- **Handle large comment sections**: Supports pagination, ensuring you capture all comments, even when there are hundreds!
- **Customizable pagination**: Fetch a custom number of comments per page (50 by default).
- **Interactive progress bar**: Watch as the comments are scraped, one by one!

---

### 🛠️ Requirements

To run InstaScrape, you’ll need:

- **Python 3.x**
- **Requests module**: `requests`
- **tqdm module** : `tqdm`
- **A set of cookies** from your Instagram session.

---

### 📝 How to Use

1. **Clone the repo**:

```bash
git clone https://github.com/kaifcodec/instascrape.git
cd instascrape
pip install -r requirements.txt
```
2. After getting your respective cookies, add them in the `cookie_example.py` accordingly and rename it to `cookie.py`

3. **Run the script**
 ```bash
python insta_scrape.py
```

