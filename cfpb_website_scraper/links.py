import os.path
import random
from datetime import datetime
from pathlib import Path
from typing import Literal
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup
from loguru import logger
from tryagain import retries

from . import HOME_FOLDER
from .aws_scraper.scrape import get_webdriver, normalize_url

WEBSITE_URL = "https://www.consumerfinance.gov/"


def _is_same_url(url1, url2):
    """Test if two URLs are the same by comparing domain and path."""

    p1 = urlparse(url1)
    p2 = urlparse(url2)

    # Check if the domains are the same
    if p1.netloc != p2.netloc:
        return False

    # Check if the paths are the same
    if p1.path != p2.path:
        return False

    return True


def _remove_query_params(url):
    """
    Remove query parameters from a URL.
    """
    return urljoin(url, urlparse(url).path)


def _format_url(url, current_page):
    """
    Format the URLs to be consistent.

    This:
        - Converts relative URLs to absolute URLs
        - Removes double slashes
        - Removes query parameters
    """
    # Check for relative paths or headers
    if url.startswith("./") or url.startswith("../"):

        # Parse it
        p = urlparse(f"{current_page}/{url}")

        # Normalize it to handle "../" and "./"
        path = os.path.normpath(p.path)

        # Recombine the URL
        url = f"{p.scheme}://{p.netloc}{path}"

    # hash or query params first
    elif url.startswith("#") or url.startswith("?"):
        # Parse it
        p = urlparse(f"{current_page}{url}")

        # Normalize the path
        path = os.path.normpath(p.path)

        # Recombine the URL
        url = f"{p.scheme}://{p.netloc}{path}"

    # Handle absolute paths and add domain
    elif url.startswith("/"):
        url = urljoin(WEBSITE_URL, url)

    # Now normalize by removing double slashes
    url = normalize_url(url)

    # Last thing: remove any query parameters
    url = _remove_query_params(url)

    return url


def is_internal_link(url):
    """
    Return True/False depending on whether the link is internal.
    """
    url = url.strip()

    # Parse it
    p = urlparse(url)

    # Check if the domain is consumerfinance.gov
    if p.netloc != "www.consumerfinance.gov":
        return False

    # Skip RSS feeds
    if url.endswith("/feed/") or url.endswith("/feed"):
        return False

    # Internal link will either have no suffix or end in .html
    suffix = Path(p.path).suffix
    if suffix == ".html" or suffix == "":
        return True

    # Otherwise it is not an internal link
    return False


def is_file_link(url):
    """Return True/False depending on whether the link is an external file."""

    # Parse it
    url = url.strip()
    p = urlparse(url)

    # Check if the domain is in the allowed domains for files
    allowed_domains = [
        "files.consumerfinance.gov",
        "s3.amazonaws.com",
        "files.consumerfinance.gov.s3.amazonaws.com",
    ]
    if p.netloc in allowed_domains:
        return True

    # Check allowed paths if domain is on consumerfinance.gov
    if p.netloc == "www.consumerfinance.gov":
        allowed_paths = [
            "/documents/",
            "/f/",
        ]
        if any(p.path.startswith(path) for path in allowed_paths):
            return True

    # Check suffixes we know are files
    allowed_suffixes = [
        ".csv",
        ".do",
        ".doc",
        ".docx",
        ".epub",
        ".jpg",
        ".jpeg",
        ".mp3",
        ".mp4",
        ".pdf",
        ".png",
        ".pptx",
        ".py",
        ".r",
        ".sas",
        ".sps",
        ".txt",
        ".wav",
        ".xls",
        ".xlsx",
        ".xltm",
        ".xml",
        ".zip",
    ]
    suffix = Path(url).suffix.strip().lower()
    if suffix in allowed_suffixes:
        return True

    return False


def _get_static_asset_links(soup, current_page):
    """
    Return any static assets on the page, starting with /static, extracted
    from either "href" or "src" attributes on <script>, <link>, or <img> tags.
    """
    links = set()

    # Find all relevant tags
    for tag in soup.find_all(["script", "link", "img"]):

        # Get the asset link
        src = tag.get("src") or tag.get("href")

        # If the link is not None and starts with /static, add it
        if src and "/static" in src:
            links.add(_format_url(src, current_page))

        # Add any links from srcset too!
        srcset = tag.get("srcset")
        if srcset:
            extra = [aa.strip().split()[0] for aa in tag["srcset"].split(",")]
            links |= set([_format_url(aa, current_page) for aa in extra])

    return links


def is_static_asset(url):
    """Return True/False depending on whether the link is a static asset."""

    # Parse it
    url = url.strip()
    p = urlparse(url)

    # Get static assets from consumerfinance.gov
    if p.netloc == "www.consumerfinance.gov" and p.path.startswith("/static"):
        return True

    return False


def _get_href_links(soup, current_page):
    """
    Utility function to extract href links from <a> tags on the current page.

    Output is a set of absolute href links from the current page
    """
    # Set of the found links
    links = set()

    # Loop over all the <a> tags
    for a in soup.select("a"):

        # Get the href attribute and parse if it exists
        href = a.get("href", None)
        if href:
            links.add(_format_url(href, current_page))

    return links


def get_links_from_page(driver, page):
    """
    Find all the links on a given page.

    This also handles pagination if the page has a table with multiple pages.
    """
    # Set of the found links
    all_links = set()

    # Do the parsing in BeautifulSoup
    soup = BeautifulSoup(driver.page_source, "html.parser")

    # First check for pagination to see if there is a table
    table_nav = soup.select_one("input#m-pagination__current-page-0")

    # We have an interactive table, so page through the results
    if table_nav is not None:

        # This is the number of pages in the table
        max_pages = int(table_nav["max"])

        # Log the number of pages found
        print(f"Found {max_pages} pages for {page}")

        # Need to loop over every page and get all links
        for pg_num in range(1, max_pages + 1):

            # Navigate to the new page
            driver.get(f"{page}?page={pg_num}")
            soup = BeautifulSoup(driver.page_source, "html.parser")

            # Find all static assets
            all_links |= _get_static_asset_links(soup, page)

            # Get all the href links
            all_links |= _get_href_links(soup, page)

    # No tables, so just grab the links from the original soup
    else:

        # Find all static assets
        all_links |= _get_static_asset_links(soup, page)

        # Get all the href links
        all_links |= _get_href_links(soup, page)

    return all_links


class LinkScraper:
    """
    Scraper class for getting links.

    Parameters
    ----------
    url :
        The url of the website to scrape
    headless :
        Whether to run the scraper in headless mode
    """

    def __init__(
        self,
        debug: bool = False,
        browser: str = "firefox",
    ) -> None:
        """Initialize the web driver."""
        # Save attributes
        self.browser = browser
        self.debug = debug

        # Silent
        os.environ["WDM_LOG_LEVEL"] = "0"

        # Initialize the webdriver
        self.init()

        # The folder tag
        tag = datetime.today().strftime("%Y_%m_%d__%H_%M_%S")

        # Output folder
        output_folder = HOME_FOLDER / ".." / "data" / "links" / tag
        output_folder.mkdir(parents=True, exist_ok=True)

        # Open the files
        self.files = {}
        self.files["links"] = open(output_folder / "all_links.csv", "a")
        self.files["redirects"] = open(output_folder / "redirects.csv", "a")
        self.files["errors"] = open(output_folder / "errors.csv", "a")

    def init(self) -> None:
        """
        Initialize the webdriver.

        This will reset the `driver` attribute.
        """
        # Get the driver
        self.driver = get_webdriver(browser=self.browser, debug=self.debug, nojs=False)

    def cleanup(self) -> None:
        """Clean up the web driver."""
        # Close and delete the driver
        self.driver.close()
        del self.driver

        # Log it
        logger.info("Retrying...")

    def scrape_data(
        self,
        errors: Literal["raise", "ignore"] = "ignore",
        max_retries: int = 3,
        min_sleep: int = 10,
        max_sleep: int = 120,
        log_freq: int = 100,
    ) -> None:
        """
        Scrape the data.

        Parameters
        ----------
        data :
            Scrape each row in this data frame
        errors :
            Whether to "raise" or "ignore" exceptions
        max_retries :
            After failing on a row, how many times to retry
        min_sleep :
            Minimum sleep time in seconds between retries
        max_sleep :
            Maximum sleep time in seconds between retries
        log_freq :
            How often to log messages
        """

        # This will track the pages we still need to parse
        pages_to_parse = set([WEBSITE_URL])

        # Keep track of output
        all_links = set()  # All links found

        # Keep track of redirects
        redirects = {}

        @retries(
            max_attempts=max_retries,
            cleanup_hook=self.cleanup,
            pre_retry_hook=self.init,
            wait=lambda n: min(min_sleep + 2**n + random.random(), max_sleep),
        )
        def get_page(page: str) -> None:
            """Wrapper to navigate to a page."""
            self.driver.get(page)

        # Continue parsing until we have no more pages to parse
        parsed_pages = 0
        while len(pages_to_parse) > 0:

            # The page we are about to parse
            page = pages_to_parse.pop()

            # Add a trailing slash if needed
            if not page.endswith("/"):
                page += "/"

            # Navigate to the page first and
            try:
                get_page(page)
                if parsed_pages % log_freq == 0:
                    logger.info(f"Parsed page {parsed_pages + 1}: {page}")
            except Exception as e:

                # Skip
                if errors == "ignore":
                    logger.info(f"Exception raised for page = {page}")
                    logger.info(f"Ignoring exception: {str(e)}")
                    self.files["errors"].write(f"{page}\n")
                    self.files["errors"].flush()
                    continue
                # Raise
                else:
                    logger.exception(f"Exception raised for page = {page}'")
                    raise

            # Increase the number of parsed pages
            parsed_pages += 1

            # Get formatted current URL
            current_url_no_query = _remove_query_params(self.driver.current_url)
            if not current_url_no_query.endswith("/"):
                current_url_no_query += "/"

            # IMPORTANT: Check for current URL redirects
            if not _is_same_url(page, current_url_no_query):

                # Log it
                logger.info(f"Redirected from {page} to {current_url_no_query}")

                # Save the redirect
                redirects[page] = current_url_no_query
                self.files["redirects"].write(f"{page},{current_url_no_query}\n")
                self.files["redirects"].flush()

                # Parse the redirect if we haven't already
                page = current_url_no_query

                # These are pages we know about
                known_pages = pages_to_parse | all_links

                # We don't need to parse this if we know about it
                if page in known_pages:
                    continue

            # Save the url to the set and write it
            if "/?" in page:
                raise ValueError(f"Found a ? in the URL: {page}")

            all_links.add(page)
            self.files["links"].write(f"{page}\n")
            self.files["links"].flush()

            # Extract all links from the page and static links too
            links_on_this_page = get_links_from_page(self.driver, page)

            # We found some links on the page
            if len(links_on_this_page):

                # Extract out the internal links so we can parse them if needed
                internal_links = [
                    url for url in links_on_this_page if is_internal_link(url)
                ]

                # These are pages we know about and will be (or have been) parsed
                known_pages = pages_to_parse | all_links

                # Add a new internal link to the parsing list if it is not already there
                pages_to_parse |= set(internal_links) - known_pages

                # Get the new links: links not already in all links
                new_links_to_save = links_on_this_page - all_links

                # Add them all to the total list
                all_links |= links_on_this_page

                # Save the rest of the links (non-internals, files, etc.)
                for page in new_links_to_save:

                    if "/?" in page:
                        raise ValueError(f"Found a ? in the URL: {page}")

                    self.files["links"].write(f"{page}\n")
                    self.files["links"].flush()

        # Close the files
        self.files["redirects"].close()
        self.files["links"].close()
        self.files["errors"].close()

        # Close the web driver
        self.driver.close()
