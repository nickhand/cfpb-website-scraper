from importlib.metadata import version
from pathlib import Path

__version__ = version(__package__)


# The app name on AWS
APP_NAME = __package__.replace("_", "-")

# BUCKET NAME
BUCKET_NAME = APP_NAME

# The directory of this file
HOME_FOLDER = Path(__file__).resolve().parent
