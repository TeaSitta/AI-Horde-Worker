"""This is the bridge, It connects the horde with the ML processing"""

# We need to import the argparser first, as it sets the necessary Switches
from worker.argparser import args
from worker.utils.set_envs import set_worker_env_vars_from_config
from worker.bridge_data import BridgeData
from worker.logger import logger, quiesce_logger, set_logger_verbosity
from worker.scribe_worker import ScribeWorker
from worker.ui import TerminalUI

set_worker_env_vars_from_config()  # Get `cache_home` from `bridgeconfig.yaml` into the environment variable


def main():
    set_logger_verbosity(args.verbosity)
    quiesce_logger(args.quiet)
    bridge_data = BridgeData()
    bridge_data.reload_data()

    try:
        worker = ScribeWorker(bridge_data)
        worker.start()
    except KeyboardInterrupt:
        logger.info("Keyboard Interrupt Received. Ending Process")
    logger.init(f"{bridge_data.worker_name} Instance", status="Stopped")
    TerminalUI.stop()


if __name__ == "__main__":
    main()
