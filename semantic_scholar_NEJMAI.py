from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
import time

# Set up ChromeOptions to run the browser in headless mode (no UI)
chrome_options = Options()
chrome_options.add_argument("--headless")  # Run in background without opening browser window

# Initialize the WebDriver
driver = webdriver.Chrome()

def search_and_extract_dois():
    # Open the Semantic Scholar search page for "NEJM AI" sorted by publication date
    search_query = "NEJM AI"
    search_url = f"https://www.semanticscholar.org/search?q={search_query}&sort=pub-date"
    driver.get(search_url)
    time.sleep(20)  # Allow time for the page to load

    # Ensure that the page has loaded and display the results
    print(f"Successfully navigated to search results for: {search_query}")

    try:
        # Find all the anchor tags with 'href' containing 'doi.org'
        publisher_links = driver.find_elements(By.XPATH, "//a[contains(@href, 'doi.org')]")
        print(f"Found {len(publisher_links)} publisher links.")

        # Iterate through each publisher link and extract the href
        for link in publisher_links:
            href = link.get_attribute("href")
            print(f"Found DOI URL: {href}")
            if "doi.org" in href:
                doi = href.split("doi.org/")[-1]  # Extract the DOI from the link
                print(f"Extracted DOI: {doi}")
            else:
                print("No DOI found in link:", href)
    except Exception as e:
        print(f"Error extracting DOIs: {e}")
    finally:
        driver.quit()

# Run the function to search and extract DOIs
search_and_extract_dois()


