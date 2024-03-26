"""This is the bridge, It connects the horde with the ML processing"""

# We need to import the argparser first, as it sets the necessary Switches
from worker.argparser import args  # noqa: I001
from worker.bridge_data import BridgeData
from worker.logger import logger, quiesce_logger, set_logger_verbosity
from worker.scribe_worker import ScribeWorker


def main() -> None:
    set_logger_verbosity(args.verbosity)
    quiesce_logger(args.quiet)
    bridge_data = BridgeData()
    bridge_data.reload_data()

    try:
        worker = ScribeWorker(bridge_data)
        worker.start()
    except KeyboardInterrupt:
        logger.info("Keyboard Interrupt Received. Ending Process")
    logger.info(f"{bridge_data.worker_name} Instance stopped")


if __name__ == "__main__":
    main()
