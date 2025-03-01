import os
import random
import re
from typing import Any, Literal, Optional, Union
from urllib.parse import urlparse

import pandas as pd
import requests
from bs4 import BeautifulSoup
from dotenv import find_dotenv, load_dotenv
from loguru import logger
from s3fs import S3FileSystem
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from tryagain import retries

from .. import BUCKET_NAME


def normalize_url(url):
    return re.sub(r"(?<!:)//+", "/", url)


def get_webdriver(
    browser: str,
    download_dir: Optional[str] = None,
    debug: bool = False,
    nojs: bool = True,
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
        if nojs:
            options.add_argument("--disable-javascript")  # Disable JavaScript
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
        if nojs:
            options.set_preference("javascript.enabled", False)  # Disable JavaScript
        if not debug:
            options.add_argument("--headless")

        if download_dir is not None:
            options.set_preference("browser.download.folderList", 2)
            options.set_preference("browser.download.dir", download_dir)
            options.set_preference(
                "browser.helperApps.neverAsk.saveToDisk", "application/pdf"
            )
            options.set_preference("pdfjs.disabled", True)

        service = Service()
        driver = webdriver.Firefox(service=service, options=options)
    else:
        raise ValueError("Unknown browser type, should be 'chrome' or 'firefox'")

    return driver


class WebScraper:
    """
    Scraper abstract base class.

    Parameters
    ----------
    url :
        The url of the website to scrape
    headless :
        Whether to run the scraper in headless mode
    """

    def __init__(
        self,
        kind,
        debug: bool = False,
        browser: str = "firefox",
    ) -> None:
        """Initialize the web driver."""
        # Save attributes
        self.kind = kind
        self.browser = browser
        self.debug = debug

        # Silent
        os.environ["WDM_LOG_LEVEL"] = "0"

        # Initialize the webdriver
        self.init()

    def init(self) -> None:
        """
        Initialize the webdriver.

        This will reset the `driver` attribute.
        """
        # Get the driver
        self.driver = get_webdriver(browser=self.browser, debug=self.debug)

    def cleanup(self) -> None:
        """Clean up the web driver."""
        # Close and delete the driver
        self.driver.close()
        del self.driver

        # Log it
        logger.info("Retrying...")

    def post_call_hook(self) -> None:
        """
        Post call hook.

        This function is called after scraping each data row.
        """
        pass

    def scrape_data(
        self,
        data: pd.DataFrame,
        errors: Literal["raise", "ignore"] = "ignore",
        max_retries: int = 3,
        min_sleep: int = 10,
        max_sleep: int = 120,
        log_freq: int = 10,
    ) -> pd.DataFrame:
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

        @retries(
            max_attempts=max_retries,
            cleanup_hook=self.cleanup,
            pre_retry_hook=self.init,
            wait=lambda n: min(min_sleep + 2**n + random.random(), max_sleep),
        )
        def call(i: int) -> dict[str, Any]:
            """Wrapper to __call__ for each data row."""

            # Get this data row
            row = data.iloc[i]

            # Log
            if i % log_freq == 0:
                logger.info(f"Scraping data row #{i+1}")

            # Scrape
            return self(row.to_dict())

        # Try to scrape
        for i in range(len(data)):

            try:
                # Call for this row
                call(i)

                # Call any post hook
                self.post_call_hook()

            except Exception as e:

                # Skip
                if errors == "ignore":
                    logger.info(f"Exception raised for i = {i}")
                    logger.info(f"Ignoring exception: {str(e)}")
                # Raise
                else:
                    logger.exception(f"Exception raised for i = {i}'")
                    raise

        # Log it
        logger.debug(f"Done scraping {i+1} rows")

    def __call__(self, row: dict[str, Any]) -> dict[str, Any]:
        """Run the scraping operation for the specified row of the data frame."""

        # Get the url
        url = row[
            "url"
        ]  # this is the full url, e.g., httpsL//www.consumerfinance.gov/...

        # Load
        load_dotenv(find_dotenv())

        # Initialize the s3 filesystem
        s3 = S3FileSystem()

        # Get the page
        if self.kind == "pages":

            # Format the url
            full_url = normalize_url(url)
            path_url = urlparse(full_url).path  # e.g., /about-us/blog/...

            # Navigate to the page
            self.driver.get(full_url)

            # Get the page source
            page_source = self.driver.page_source

            if "404: Page not found" in page_source:
                logger.info(f"404: Page Not Found for {full_url}")
                return

            # Check for interactive tables
            soup = BeautifulSoup(page_source, "html.parser")

            # First check for pagination to see if there is a table
            table_nav = soup.select_one("input#m-pagination__current-page-0")

            pages = {}
            if table_nav is not None:
                max_pages = int(table_nav["max"])

                # Need to loop over every page and get all links
                for pg_num in range(1, max_pages + 1):

                    # Go to the page
                    self.driver.get(f"{full_url}?page={pg_num}")

                    if pg_num == 1:
                        pg_url = path_url
                    else:
                        pg_url = f"{path_url}/pages/{pg_num}"

                    pages[pg_url] = self.driver.page_source
            else:
                pages[path_url] = page_source

            # Save each page to s3
            for url, page_source in pages.items():

                # Figure out the output path
                output_path = path_url
                if output_path.endswith("/"):
                    output_path = f"{output_path}index.html"
                elif not output_path.endswith("index.html"):
                    output_path = f"{output_path}/index.html"

                # Strip leading "/"
                output_path = output_path.lstrip("/")

                # Save to s3
                output_filename = normalize_url(
                    f"s3://{BUCKET_NAME}/pages/{output_path}"
                )
                with s3.open(output_filename, "w") as f:
                    f.write(page_source)

        elif self.kind == "files":

            # Get the s3 path
            output_path = urlparse(url).path
            output_filename = f"s3://{BUCKET_NAME}/files{output_path}"

            # Download the file
            response = requests.get(url, stream=True)
            try:
                response.raise_for_status()  # Raise an error for bad responses (4xx, 5xx)
            except:
                logger.info(f"Failed to download {url}")
                return

            with s3.open(output_filename, "wb") as f:
                for chunk in response.iter_content(1024):
                    f.write(chunk)

        elif self.kind == "static":

            if "consumerfinance.gov/static/" not in url:
                return

            # Get the s3 path
            output_filename = (
                f"s3://{BUCKET_NAME}/pages/static{url.split('/static')[-1]}"
            )

            # Download the file
            response = requests.get(url, stream=True)
            try:
                response.raise_for_status()  # Raise an error for bad responses (4xx, 5xx)
            except:
                logger.info(f"Failed to download {url}")
                return

            with s3.open(output_filename, "wb") as f:
                for chunk in response.iter_content(1024):
                    f.write(chunk)
        else:
            raise ValueError(f"Unknown kind: {self.kind}")
