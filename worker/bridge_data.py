"""The configuration of the bridge"""

import os
import random
import threading

import requests
import yaml
from loguru import logger

from worker.argparser import args
from worker.consts import BRIDGE_CONFIG_FILE


class BridgeData:
    """Configuration object"""

    mutex = threading.Lock()

    def __init__(self) -> None:
        random.seed()
        # I have to pass the args from the extended class
        self.args = args

        # If there is a YAML config file, load it
        if not self.load_config():
            logger.warning("bridgeData.yaml not found, loading defaults or arguments.")

        self.horde_url = os.environ.get("HORDE_URL", "https://aihorde.net")
        # Give a cool name to your instance
        self.worker_name = os.environ.get("HORDE_WORKER_NAME", "An Awesome AI Horde Worker")
        # The api_key identifies a unique user in the horde
        self.api_key = os.environ.get("HORDE_API_KEY", "0000000000")
        self.max_threads = int(os.environ.get("HORDE_MAX_THREADS", 1))
        self.queue_size = int(os.environ.get("HORDE_QUEUE_SIZE", 0))

        self.stats_output_frequency = int(os.environ.get("STATS_OUTPUT_FREQUENCY", 30))
        self.disable_terminal_ui = os.environ.get("DISABLE_TERMINAL_UI", "false") == "true"
        self.initialized = False
        self.suppress_speed_warnings = False
        self.kai_available = False
        self.model = None
        self.kai_url = "http://localhost:5000"
        self.max_length = int(os.environ.get("HORDE_MAX_LENGTH", "80"))
        self.max_context_length = int(os.environ.get("HORDE_MAX_CONTEXT_LENGTH", "1024"))

        self.softprompts = {}
        self.current_softprompt = None

    def load_config(self) -> bool:
        # YAML config
        if os.path.exists(BRIDGE_CONFIG_FILE):
            with open(BRIDGE_CONFIG_FILE, encoding="utf-8", errors="ignore") as configfile:
                config = yaml.safe_load(configfile)
                # Map the config's values directly into this instance's properties
                for key, value in config.items():
                    setattr(self, key, value)
            return True  # loaded
        return False

    @logger.catch(reraise=True)
    def reload_data(self) -> None:
        """Reloads configuration data"""
        previous_api_key = self.api_key
        previous_url = self.horde_url
        self.load_config()
        if self.args.api_key:
            self.api_key = self.args.api_key
        if self.args.worker_name:
            self.worker_name = self.args.worker_name
        if self.args.horde_url:
            self.horde_url = self.args.horde_url
        if self.args.max_threads:
            self.max_threads = self.args.max_threads
        if self.args.queue_size:
            self.queue_size = self.args.queue_size
        if not self.initialized or previous_api_key != self.api_key:
            try:
                user_req = requests.get(
                    f"{self.horde_url}/api/v2/find_user",
                    headers={"apikey": self.api_key},
                    timeout=10,
                )
                user_req = user_req.json()
                self.username = user_req["username"]

            except Exception:
                logger.warning(f"Server {self.horde_url} error during find_user. Setting username 'N/A'")
                self.username = "N/A"

        if args.kai_url:
            self.kai_url = args.kai_url
        self.validate_kai()
        if self.kai_available and not self.initialized and previous_url != self.horde_url:
            logger.init(
                (
                    f"Username '{self.username}'. Server Name '{self.worker_name}'. "
                    f"Horde URL '{self.horde_url}'. KoboldAI Client URL '{self.kai_url}'"
                    "Worker Type: Scribe"
                ),
                status="Joining Horde",
            )

    @logger.catch(reraise=True)
    def validate_kai(self) -> None:
        logger.debug("Retrieving settings from KoboldAI Client...")
        try:
            req = requests.get(self.kai_url + "/api/latest/model")
            self.model = req.json()["result"]
            # Normalize huggingface and local downloaded model names
            if "/" not in self.model:
                self.model = self.model.replace("_", "/", 1)

            if self.model not in self.softprompts:
                req = requests.get(self.kai_url + "/api/latest/config/soft_prompts_list")
                self.softprompts[self.model] = [sp["value"] for sp in req.json()["values"]]
            req = requests.get(self.kai_url + "/api/latest/config/soft_prompt")
            self.current_softprompt = req.json()["value"]
        except requests.exceptions.JSONDecodeError:
            logger.error(f"Server {self.kai_url} is up but does not appear to be a KoboldAI server.")
            self.kai_available = False
            return
        except requests.exceptions.ConnectionError:
            logger.error(f"Server {self.kai_url} is not reachable. Are you sure it's running?")
            self.kai_available = False
            return
        self.kai_available = True
