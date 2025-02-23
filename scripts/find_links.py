import re
from pathlib import Path
from typing import Optional, Union
from urllib.parse import urljoin, urlparse

import pandas as pd
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.service import Service

THIS_DIR = Path(__file__).resolve().parent
DATA_DIR = THIS_DIR / ".." / "data"

URL = "https://www.consumerfinance.gov"


def normalize_url(url):
    """Remove double slashes from a URL."""
    return re.sub(r"(?<!:)//+", "/", url)


def get_webdriver(
    browser: str, download_dir: Optional[str] = None, debug: bool = False
) -> Union[webdriver.Chrome, webdriver.Firefox]:
    """
    Initialize a selenium web driver with the specified options.

    Parameters
    ----------
    browser: str
        The browser to use; either 'chrome' or 'firefox'
    download_dir: str
        If specified, the name of the local download directory
    debug: bool
        Whether to use the headless version of Chrome

    Returns
    -------
    webdriver.Chrome, webdriver.Firefox
        The selenium web driver

    Raises
    ------
    ValueError
        If the browser is not 'chrome' or 'firefox'
    """
    # Google chrome
    if browser == "chrome":
        # Create the options
        options = webdriver.ChromeOptions()
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-extensions")
        options.add_argument("--disable-gpu")
        if not debug:
            options.add_argument("--headless")

        # Set up the download directory for PDFs
        if download_dir is not None:
            profile = {
                "plugins.plugins_list": [
                    {"enabled": False, "name": "Chrome PDF Viewer"}
                ],  # Disable Chrome's PDF Viewer
                "download.default_directory": download_dir,
                "download.extensions_to_open": "applications/pdf",
            }
            options.add_experimental_option("prefs", profile)

        service = Service()
        driver = webdriver.Chrome(service=service, options=options)

    # Firefox
    elif browser == "firefox":
        # Create the options
        options = webdriver.FirefoxOptions()
        if not debug:
            options.add_argument("--headless")

        service = Service()
        driver = webdriver.Firefox(service=service, options=options)
    else:
        raise ValueError("Unknown browser type, should be 'chrome' or 'firefox'")

    return driver


def format_url(link):
    """Format the URLs to be consistent."""

    # Remove any query parameters
    link = urljoin(link, urlparse(link).path)

    # Remove the base URL if it is there
    if link.startswith(URL):
        link = link.replace(URL, "")

    # Add a leading slash if it is missing
    if (
        link.endswith(".html")
        and not link.startswith("http")
        and not link.startswith("www")
        and not link.startswith("/")
    ):
        link = "/" + link

    return normalize_url(link)


def get_internal_links(link):
    """Return True/False depending on whether the link is internal."""
    link = link.strip()
    return link.startswith("/") and not link.startswith("/#")


def get_files(link):
    """Return True/False depending on whether the link is an external file."""

    link = link.strip()

    allowed_domains = [
        "files.consumerfinance.gov",
        "s3.amazonaws.com",
        "files.consumerfinance.gov.s3.amazonaws.com",
    ]

    domain = urlparse(link).netloc

    if domain in allowed_domains:
        return True

    if domain == "" and link.startswith("/documents/"):
        return True
    if domain == "" and link.startswith("/f/"):
        return True

    return False


def find_static_assets(soup):
    """Return any static assets on the page, starting with /static"""

    static_assets = []

    # Find all relevant tags
    for tag in soup.find_all(["script", "link", "img"]):
        src = tag.get("src") or tag.get("href")  # Get the asset link
        if src and "/static" in src:
            full_url = urljoin(URL, src)  # Convert to absolute URL
            static_assets.append(full_url)

    return static_assets


def get_links_from_page(driver, page):
    """
    Find all the links on a given page.

    This also handles pagination if the page has a table with multiple pages.
    """

    # List of the found links
    links = []
    static = []

    # Navigate to the page first
    base = "https://www.consumerfinance.gov"
    driver.get(f"{base}/{page}")

    # Do the parsing in BeautifulSoup
    soup = BeautifulSoup(driver.page_source, "html.parser")

    # First check for pagination to see if there is a table
    table_nav = soup.select_one("input#m-pagination__current-page-0")

    def get_links_from_soup(soup):
        """Utility function to extract href links from a BeautifulSoup object."""

        links = []
        for a in soup.select("a"):
            href = a.get("href", None)
            if href:
                links.append(format_url(href))
        return links

    # We have an interactive table, so page through the results
    if table_nav is not None:

        # This is the number of pages in the table
        max_pages = int(table_nav["max"])

        # Log the number of pages found
        print(f"Found {max_pages} pages for {page}")

        # Need to loop over every page and get all links
        for pg_num in range(1, max_pages + 1):

            # Navigate to the new page
            driver.get(f"{base}/{page}?page={pg_num}")
            soup = BeautifulSoup(driver.page_source, "html.parser")

            # Find all static assets
            static += find_static_assets(soup)

            # Get all the links
            links += get_links_from_soup(soup)

    # No tables, so just grab the links from the original soup
    else:

        # Find all static assets
        static += find_static_assets(soup)

        # Get the href links from the page
        links += get_links_from_soup(soup)

    if len(links):
        links = pd.Series(links).drop_duplicates()
    if len(static):
        static = pd.Series(static).drop_duplicates()
    return links, static


if __name__ == "__main__":

    # Initialize the web driver
    driver = get_webdriver("chrome", debug=False)

    # This will track the pages we still need to parse
    pages_to_parse = [""]

    # Keep track of output
    file_links = []
    all_links = []
    static_links = []

    # Continue parsing until we have no more pages to parse
    while len(pages_to_parse) > 0:

        print(static_links)

        # The page we are about to parse
        page = pages_to_parse.pop(0)

        if len(all_links) % 100 == 0:
            print(len(all_links))
            print(f"Parsing {page}...")

        # Save the link
        all_links.append(page)

        # Extract all new links from the page
        L, S = get_links_from_page(driver, page)

        # Store static assets
        if len(S):
            static_links += S.tolist()

        # If we found links, add them to the list of pages to parse
        if len(L):

            # These are file links on files.consumerfinance.gov
            sel = L.apply(get_files)
            file_links += L.loc[sel].tolist()

            # These are internal links, e.g. start with "/"
            L_no_files = L.loc[~sel]
            internal_links = L_no_files.loc[
                L_no_files.apply(get_internal_links)
            ].tolist()

            # These are pages we know about
            known_pages = list(set(pages_to_parse) | set(all_links))

            # Add a link to the parsing list if it is not already there
            pages_to_parse += [
                link for link in internal_links if link not in known_pages
            ]

    # Drop duplicates and convert to Series
    all_links = pd.Series(all_links, name="url").apply(normalize_url).drop_duplicates()
    file_links = (
        pd.Series(file_links, name="url").apply(normalize_url).drop_duplicates()
    )
    static_links = (
        pd.Series(static_links, name="url").apply(normalize_url).drop_duplicates()
    )

    # Find file links mistakenly classified as internal links
    sel = all_links.apply(lambda x: Path(x).suffix).isin([".pdf", ".csv", ".jpg"])
    missed_file_links = all_links.loc[sel].copy()
    missed_file_links = "https://www.consumerfinance.gov" + missed_file_links

    # Remove from internal links
    all_links = all_links.loc[~sel]

    # Remove RSS feeds
    sel = all_links.str.endswith("/feed/")
    all_links = all_links.loc[~sel]

    # Make sure the links end in "/"
    def add_trailing_slash(url):
        if url.endswith(".html"):
            return url
        if not url.endswith("/"):
            return url + "/"
        return url

    all_links = all_links.apply(add_trailing_slash).drop_duplicates()

    # Add to file links
    file_links = pd.concat([file_links, missed_file_links])

    # Fix /documents too if we need to
    sel = file_links.str.startswith("/documents/") | file_links.str.startswith("/f/")
    file_links.loc[sel] = file_links.loc[sel].apply(
        lambda x: f"https://www.consumerfinance.gov{x}"
    )

    # Save
    all_links.to_csv("page_links.csv", index=False)
    file_links.to_csv("file_links.csv", index=False)
    static_links.to_csv("static_links.csv", index=False)

    # Close the web driver
    driver.close()
