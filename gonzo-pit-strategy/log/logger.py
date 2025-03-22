# TODO:  log for project
import logging
from logging import NullHandler

# Create a logger
logger = logging.getLogger(__name__)
logger.addHandler(NullHandler())
logger.setLevel(logging.DEBUG)

def log_message(message, level=logging.INFO):
    logger.log(level, message)
