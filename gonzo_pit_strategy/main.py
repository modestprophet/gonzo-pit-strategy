import traceback
from log import get_console_logger, get_db_logger

def main():
    logger = get_console_logger("example_component")

    logger.info("This is an informational message")
    logger.warning("This is a warning message")
    logger.error("This is an error message")

    db_logger = get_db_logger("db_component")
    db_logger.info("This only goes to the database")

    try:
        # Simulate an error
        x = 1 / 0
    except Exception as e:
        stack_trace = traceback.format_exc()
        db_logger.error(f"An error occurred: {str(e)}", stack_trace=stack_trace)


if __name__ == "__main__":
    main()
