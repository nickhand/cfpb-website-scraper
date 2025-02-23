import argparse
from pathlib import Path

import pandas as pd
from loguru import logger


def modify(link):
    if link.endswith(".html"):
        return link
    if not link.endswith("/") and not link.endswith("index.html"):
        link = link + "/"
    if link.endswith("/"):
        link = link + "index.html"
    return link


def get_all_files(directory):
    return [file for file in Path(directory).rglob("*") if file.is_file()]


if __name__ == "__main__":

    parser = argparse.ArgumentParser(
        description="Find links that failed to download to S3"
    )
    parser.add_argument("input_folder", type=str, help="The input folder")
    parser.add_argument(
        "existing_data", type=str, help="The filename of existing links"
    )
    parser.add_argument(
        "output_filename", type=str, help="The output file to save missing links to"
    )

    args = parser.parse_args()

    # Get all files from the input folder
    files = get_all_files(args.input_folder)
    files = ["/" + str(p.relative_to(args.input_folder)) for p in files]

    # Get the existing data
    data = pd.read_csv(args.existing_data)["url"].fillna("")
    data_modified = data.copy().apply(modify)

    sel = data_modified.isin(files)
    missing_links = data.loc[~sel]
    logger.info(f"Found {sel.sum()} matched links")
    logger.info(f"Found {len(missing_links)} missing links")

    # Save the missing links
    missing_links.to_frame().to_csv(args.output_filename, index=False)
    logger.info(f"Saved missing links to {args.output_filename}")
