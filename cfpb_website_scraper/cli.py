from datetime import datetime

import click
import pandas as pd
from dotenv import find_dotenv, load_dotenv
from loguru import logger
from s3fs import S3FileSystem

from . import APP_NAME, BUCKET_NAME
from .aws_scraper import __main__ as aws_scraper_cli
from .aws_scraper.scrape import WebScraper
from .links import LinkScraper, is_file_link, is_internal_link, is_static_asset


@click.group()
def cli():
    """CLI for scraping CFPB website"""
    pass


@cli.command()
@aws_scraper_cli.add_submit_options
@click.argument(
    "input_filename",
    type=str,
)
@click.argument(
    "kind",
    type=click.Choice(["pages", "files", "static"]),
)
@click.option("--num-workers", type=int, default=20, help="The number of workers")
def submit(input_filename, kind, num_workers=20, **kwargs):
    """Submit scraping jobs to AWS."""

    # Load config
    load_dotenv(find_dotenv())

    # Load the data
    data = pd.DataFrame(
        {"url": [x.strip() for x in open(input_filename, "r").readlines()]}
    )

    # Filter
    if kind == "pages":
        data = data.loc[data["url"].apply(is_internal_link)].drop_duplicates()
    elif kind == "files":
        data = data.loc[data["url"].apply(is_file_link)].drop_duplicates()
    elif kind == "static":
        data = data.loc[data["url"].apply(is_static_asset)].drop_duplicates()
    else:
        raise ValueError(f"Invalid kind: {kind}")

    # Log
    logger.info(f"Scraping data for {len(data)} {kind}")

    # Figure out the s3 folder
    date_string = datetime.today().strftime("%y-%m-%d_%H_%M_%S")
    s3_subfolder = f"input-data/{date_string}"
    input_filename = f"s3://{BUCKET_NAME}/{s3_subfolder}/{kind}.csv"

    # Initialize the s3 file system
    s3 = S3FileSystem()

    # Save the incident numbers to s3
    with s3.open(input_filename, "w") as f:
        data.to_csv(f, index=False)

    # Loag
    logger.info(f"Uploaded data to {input_filename}")

    # Create the command
    command = f"{APP_NAME} run {input_filename} {kind}"

    # Submit the jobs
    data = aws_scraper_cli.submit(
        command,
        num_workers=num_workers,
        bucket_name=BUCKET_NAME,
        cluster_name="aws-scraper",
        task_family=APP_NAME,
        **kwargs,
    )


@cli.command()
@click.argument("data_path", type=str)
@click.argument("kind", type=click.Choice(["pages", "files", "static"]))
@aws_scraper_cli.add_run_options
def run(data_path, kind, **kwargs):
    """Run scraper jobs."""

    # Load config
    load_dotenv(find_dotenv())

    # Initialize the scraper
    scraper = WebScraper(kind)

    # Run the scraper
    aws_scraper_cli.run(
        data_path=data_path,
        scraper=scraper,
        **kwargs,
    )


@cli.command(name="find-links")
@click.option(
    "--browser",
    type=click.Choice(["firefox", "chrome"]),
    default="firefox",
    help="The browser to use.",
)
@click.option(
    "--debug",
    is_flag=True,
    help="Turn on additional logging for debugging purposes.",
)
def find_links(browser="firefox", debug=False):
    """Find all links on the CFPB website."""

    scraper = LinkScraper(browser=browser, debug=debug)
    scraper.scrape_data()
