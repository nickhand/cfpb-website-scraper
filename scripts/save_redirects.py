import argparse
from pathlib import Path
from urllib.parse import urlparse

import pandas as pd

THIS_FOLDER = Path(__file__).parent

parser = argparse.ArgumentParser()
parser.add_argument("input_filename", type=str)

args = parser.parse_args()

# Load the data
data = pd.DataFrame(
    [line.split(",") for line in open(args.input_filename).readlines()],
    columns=["to", "from"],
).drop_duplicates()

for col in ["to", "from"]:
    data[col] = data[col].apply(lambda x: urlparse(x).path)


# Save
output_filename = THIS_FOLDER / ".." / "results" / "pages" / "_redirects"
data.to_csv(output_filename, index=False, header=None, sep=" ")
