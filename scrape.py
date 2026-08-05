import re
import time
import urllib.request
from urllib.error import HTTPError, URLError

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
    "Accept-Encoding": "identity",
    "Connection": "keep-alive",
}

MAX_RETRIES = 3
RETRY_DELAY = 2

class ParseError(Exception):
    pass

class RequestError(Exception):
    pass

def _extract_price(html: str) -> tuple:
    # Core price, usually in a span with arial price classes
    m = re.search(r'a-offscreen">\$([0-9,]+\.\d{2})<', html)
    if m:
        raw = m.group(1).replace(",", "")
        return float(raw), "USD"

    # Kindle / books use different markup sometimes
    m = re.search(r'kindle-price[^>]*>\$([0-9,]+\.\d{2})', html)
    if m:
        raw = m.group(1).replace(",", "")
        return float(raw), "USD"

    # Newer layout splits dollars and cents into separate spans
    m = re.search(r'a-price-whole[^>]*>([0-9,]+)', html)
    if m:
        dollars = m.group(1).replace(",", "")
        cents_m = re.search(r'a-price-fraction[^>]*>(\d{2})', html)
        if cents_m:
            return float(f"{dollars}.{cents_m.group(1)}"), "USD"
        return float(dollars), "USD"

    return None, None

def _extract_title(html: str) -> str:
    m = re.search(r'<span[^>]*id="productTitle"[^>]*>([^<]+)</span>', html)
    if m:
        return m.group(1).strip()
    return ""

def _extract_availability(html: str) -> str:
    m = re.search(r'deliveryMessageMirroring[^>]*>([^<]+)<', html)
    if m:
        return m.group(1).strip()
    # fallback for in-stock / out-of-stock text
    if "In Stock" in html:
        return "In Stock"
    if "Currently unavailable" in html:
        return "Currently unavailable"
    return ""

def fetch_price(url: str, retries: int = MAX_RETRIES) -> dict:
    last_err = None
    for attempt in range(retries):
        req = urllib.request.Request(url, headers=HEADERS)
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                html = resp.read().decode("utf-8", errors="replace")
        except HTTPError as e:
            last_err = f"HTTP {e.code}"
            if e.code == 503:
                time.sleep(RETRY_DELAY * (attempt + 1))
                continue
            raise RequestError(last_err)
        except URLError as e:
            raise RequestError(f"URL error: {e.reason}")

        # Amazon sometimes returns a CAPTCHA or login wall
        if "captcha" in html.lower() or "sign-in" in html.lower():
            raise RequestError("blocked by Amazon (captcha/login)")

        title = _extract_title(html)
        price, currency = _extract_price(html)
        availability = _extract_availability(html)

        if price is None and title == "":
            # probably got a partial page or redirect, retry
            last_err = "partial page"
            time.sleep(RETRY_DELAY)
            continue

        return {
            "price": price,
            "currency": currency,
            "title": title,
            "availability": availability,
        }

    raise RequestError(f"failed after {retries} tries: {last_err}")
