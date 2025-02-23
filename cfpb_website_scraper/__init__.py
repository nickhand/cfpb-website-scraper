from importlib.metadata import version

__version__ = version(__package__)


# The app name on AWS
APP_NAME = __package__.replace("_", "-")

# BUCKET NAME
BUCKET_NAME = APP_NAME
