
import sys
import os
from pathlib import Path

# Add project root to Python path
project_root = Path(__file__).resolve().parent.parent.parent
sys.path.append(str(project_root))

from gonzo_pit_strategy.log.logger import get_logger
# Test with a name that inherits from gonzo_pit_strategy
logger_cli = get_logger("gonzo_pit_strategy.cli.reproduce")
print(f"Logger name: {logger_cli.name}")
logger_cli.info("CLI INFO message")
logger_cli.debug("CLI DEBUG message (Should appear if config handles inheritance)")


# Also test with explicit name 'training'
logger2 = get_logger("training")
logger2.info("Training INFO message")
