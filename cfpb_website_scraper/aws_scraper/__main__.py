from __future__ import annotations

from typing import Literal, Optional

import click
import numpy as np
import pandas as pd
from loguru import logger

from . import aws, io
from .scrape import WebScraper

SHARED_OPTIONS = [
    click.option(
        "--sample",
        type=int,
        default=None,
        help="Only scrape a random sample of input data rows.",
    ),
    click.option(
        "--seed",
        type=int,
        default=42,
        help="Random seed for sampling.",
    ),
    click.option(
        "--errors",
        type=click.Choice(["ignore", "raise"]),
        default="ignore",
        help="Whether to ignore or raise exceptions.",
    ),
    click.option(
        "--max-retries",
        default=3,
        type=int,
        help="Max number of retries when error occurs.",
    ),
    click.option(
        "--min-sleep", default=10, type=int, help="Min sleep time between retries."
    ),
    click.option(
        "--max-sleep", default=120, type=int, help="Max sleep time between retries."
    ),
    click.option(
        "--log-freq", default=25, type=int, help="How often to log while scraping."
    ),
]


def add_run_options(f: click.Command) -> click.Command:
    """Add CLI options for running AWS scraper."""

    options = [
        click.option(
            "--total-processes",
            type=int,
            default=1,
            help="If running in parallel, the total number of processes that will run.",
        ),
        click.option(
            "--process-id",
            type=int,
            default=0,
            help=(
                "If running in parallel, the local process id."
                "This should be between 0 and number of processes."
            ),
        ),
    ] + SHARED_OPTIONS

    # Add the options to the input function
    for option in options:
        option(f)

    # Return the original function
    return f


def add_submit_options(f: click.Command) -> click.Command:
    """Add AWS options to the input function."""

    options = [
        click.option(
            "--debug",
            is_flag=True,
            help="Turn on additional logging for debugging purposes.",
        ),
        click.option(
            "--no-wait", is_flag=True, help="Whether to wait for AWS jobs to finish"
        ),
    ] + SHARED_OPTIONS

    # Add the options to the input function
    for option in options:
        option(f)

    # Return the original function
    return f


def run(
    data_path: aws.S3Path | str,
    scraper: WebScraper,
    total_processes: int = 1,
    process_id: int = 0,
    sample: Optional[int] = None,
    seed: int = 42,
    errors: Literal["ignore", "raise"] = "ignore",
    max_retries: int = 3,
    min_sleep: int = 10,
    max_sleep: int = 120,
    log_freq: int = 25,
) -> Optional[pd.DataFrame]:
    """
    Run the scraper pipeline.

    Note: This will fail if we are not on AWS.
    """
    # Fail if we are not on AWS
    # if not aws.running_on_aws():
    #    raise RuntimeError("Scraping code is not running on AWS")

    # Process ID cannot be greater than total
    assert process_id < total_processes

    # Check paths
    if isinstance(data_path, str):
        data_path = aws.S3Path(data_path)

    # Load the input data from the specified file
    data = io.load_data_from_s3(data_path)  # This is a CSV file

    # Sample data if requested
    if sample is not None:
        data = data.sample(sample, random_state=seed)

    # Split data by process
    if total_processes > 1:
        data_chunk = np.array_split(data, total_processes)[process_id]
    else:
        data_chunk = data

    # No data, just return
    if not len(data_chunk):
        return

    # Run the scraper
    logger.info(f"Process #{process_id+1}: Scraping data for {len(data_chunk)} rows")
    scraper.scrape_data(
        data_chunk,
        errors=errors,
        max_retries=max_retries,
        min_sleep=min_sleep,
        max_sleep=max_sleep,
        log_freq=log_freq,
    )


def submit(
    base_command: str,
    num_workers: int,
    bucket_name: str,
    cluster_name: str,
    task_family: str,
    debug: bool = False,
    sample: Optional[int] = None,
    seed: int = 42,
    errors: Literal["ignore", "raise"] = "ignore",
    max_retries: int = 5,
    min_sleep: int = 30,
    max_sleep: int = 120,
    log_freq: int = 10,
    no_wait: bool = False,
) -> pd.DataFrame:
    """
    Submit scraping jobs to AWS.
    """
    # Initialize the AWS connection
    aws_interface = aws.AWSConnection(
        bucket_name, cluster_name, task_family, debug=debug
    )

    # Initialize the cluster connection
    aws_interface.initialize_ecs_cluster()

    # Build the command
    command = base_command.split()

    # Make sure first entry is "run"
    if command[0] != "run":
        command.insert(0, "run")

    # Add the options
    command += [
        f"--total-processes={num_workers}",
        f"--errors={errors}",
        f"--seed={seed}",
        f"--max-retries={max_retries}",
        f"--min-sleep={min_sleep}",
        f"--max-sleep={max_sleep}",
        f"--log-freq={log_freq}",
    ]

    # Add the optional arguments
    if sample is not None:
        command += [f"--sample={sample}"]
    if debug:
        command += ["--debug"]

    tasks = []
    for pid in range(0, num_workers):

        # Log
        logger.info(f"Submitting job #{pid+1}")

        # Build the final command
        task = aws_interface.submit_job(command + [f"--process-id={pid}"])
        tasks.append(task)

    # Do not wait for tasks to finish
    if no_wait:
        return

    # Wait for the tasks to finish!
    aws_interface.wait_for_tasks(tasks)
