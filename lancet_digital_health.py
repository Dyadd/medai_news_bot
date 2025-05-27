# To connect the lancet articles to news_worker as automatically medically relevant

#!/usr/bin/env python3
"""
lancet_digital_health_scraper.py
——————————————————————————————————
• Visit the The Lancet Digital Health venue page on Semantic Scholar (sorted by date)
• Collect every PubMed primary link on that first batch of results
• For each PubMed record:
      – wait for the “Full text links” widget to appear
      – look for an Elsevier Science link-out (href contains linkinghub.elsevier.com)
      – skip the record if no Elsevier link is present
      – fetch the Elsevier page, grab <section id="bodymatter">, strip HTML
• Save each article body as plain-text files in ./lancet_dh_bodies/
"""

import re, time, sys
from pathlib import Path
from bs4 import BeautifulSoup

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException


###############################################################################
# ---------- configuration ----------
HEADLESS          = True
WAIT_SEC          = 20                               # explicit-wait timeout
OUT_DIR           = Path("lancet_dh_bodies")
VENUE_URL = (
    "https://www.semanticscholar.org/venue"
    "?name=The%20Lancet%20Digital%20Health&sort=pub-date"
)
###############################################################################


def make_driver() -> webdriver.Chrome:
    opts = Options()
    if HEADLESS:
        opts.add_argument("--headless=new")           # Chrome ≥ 120
    opts.add_argument("--window-size=1920,1080")
    return webdriver.Chrome(options=opts)


def wait_for(driver, css, wait) -> None:
    """Block until *any* element matching CSS selector is in the DOM."""
    wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, css)))


def extract_body_text(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    sec  = soup.select_one("section#bodymatter")
    return sec.get_text(" ", strip=True) if sec else ""


def fetch_elsevier_link(driver, wait) -> str | None:
    """Return Elsevier link-out on current PubMed page, or None."""
    try:
        wait_for(driver, "div.full-text-links-list", wait)
        # give JS a moment to inject <a> children
        time.sleep(1.0)
        links = driver.find_elements(
            By.CSS_SELECTOR,
            "div.full-text-links-list a[href*='linkinghub.elsevier.com']",
        )
        return links[0].get_attribute("href") if links else None
    except TimeoutException:
        return None


def safe_filename(title: str, max_len: int = 100) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9]+", "_", title).strip("_")
    return (cleaned or "article")[:max_len] + ".txt"


def main() -> None:
    driver = make_driver()
    wait   = WebDriverWait(driver, WAIT_SEC)

    ###########################################################################
    # 1. Semantic Scholar venue page
    ###########################################################################
    driver.get(VENUE_URL)
    wait_for(
        driver,
        "a[data-test-id='paper-link'][data-heap-link-type='medline'][data-heap-primary-link='true']",
        wait,
    )
    pubmed_links = [
        e.get_attribute("href")
        for e in driver.find_elements(
            By.CSS_SELECTOR,
            "a[data-test-id='paper-link'][data-heap-link-type='medline'][data-heap-primary-link='true']",
        )
    ]
    print(f"▶  Found {len(pubmed_links)} PubMed links")

    OUT_DIR.mkdir(exist_ok=True)

    ###########################################################################
    # 2. Iterate through PubMed → Elsevier → scrape body
    ###########################################################################
    for idx, pm_link in enumerate(pubmed_links, 1):
        print(f"\n[{idx}/{len(pubmed_links)}] PubMed ⇒ {pm_link}")
        driver.get(pm_link)

        elsevier_href = fetch_elsevier_link(driver, wait)
        if not elsevier_href:
            print("    ⚠  No Elsevier link – skipped")
            continue

        print(f"    ↳ Elsevier link: {elsevier_href}")
        driver.get(elsevier_href)

        try:
            wait_for(driver, "section#bodymatter", wait)
            body_text = extract_body_text(driver.page_source)
            if not body_text:
                raise ValueError("bodymatter empty")
            title = driver.title.split(" | ")[0]
            fp = OUT_DIR / safe_filename(title)
            fp.write_text(body_text, encoding="utf-8")
            print(f"    ✔ saved body ({len(body_text):,} chars) → {fp.name}")
        except Exception as e:
            print(f"    ✘ could not extract body: {e}")

    driver.quit()
    print("\nDone.")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit("Interrupted by user")
