import copy
import json
import time

import requests

from worker.consts import BRIDGE_VERSION  # KNOWN_INTERROGATORS, KNOWN_POST_PROCESSORS, POST_PROCESSORS_HORDELIB_MODELS
from worker.logger import logger
from worker.stats import bridge_stats


class JobPopper:
    retry_interval = 1
    BRIDGE_AGENT = f"AI Horde Worker:{BRIDGE_VERSION}:https://github.com/db0/AI-Horde-Worker"

    def __init__(self, mm, bd):
        self.model_manager = mm
        self.bridge_data = copy.deepcopy(bd)
        self.pop = None
        self.headers = {"apikey": self.bridge_data.api_key}
        # This should be set by the extending class
        self.endpoint = None

    def horde_pop(self):
        """Get a job from the horde"""
        try:
            # logger.debug(self.headers)
            # logger.debug(self.pop_payload)
            pop_req = requests.post(
                self.bridge_data.horde_url + self.endpoint,
                json=self.pop_payload,
                headers=self.headers,
                timeout=40,
            )
            # logger.debug(self.pop_payload)
            node = pop_req.headers.get("horde-node", "unknown")
            logger.debug(f"Job pop took {pop_req.elapsed.total_seconds()} (node: {node})")
            bridge_stats.update_pop_stats(node, pop_req.elapsed.total_seconds())
        except requests.exceptions.ConnectionError:
            logger.warning(f"Server {self.bridge_data.horde_url} unavailable during pop. Waiting 10 seconds...")
            time.sleep(10)
            return None
        except TypeError:
            logger.warning(f"Server {self.bridge_data.horde_url} unavailable during pop. Waiting 2 seconds...")
            time.sleep(2)
            return None
        except requests.exceptions.ReadTimeout:
            logger.warning(f"Server {self.bridge_data.horde_url} timed out during pop. Waiting 2 seconds...")
            time.sleep(2)
            return None
        except requests.exceptions.InvalidHeader:
            logger.warning(
                f"Server {self.bridge_data.horde_url} Something is wrong with the API key you are sending. "
                "Please check your bridgeData api_key variable. Waiting 10 seconds...",
            )
            time.sleep(10)
            return None

        try:
            self.pop = pop_req.json()  # I'll use it properly later
        except json.decoder.JSONDecodeError:
            logger.error(
                f"Could not decode response from {self.bridge_data.horde_url} as json. "
                "Please inform its administrator!",
            )
            time.sleep(2)
            return None
        if not pop_req.ok:
            logger.warning(f"{self.pop['message']} ({pop_req.status_code})")
            if "errors" in self.pop:
                logger.warning(f"Detailed Request Errors: {self.pop['errors']}")
            time.sleep(2)
            return None
        return [self.pop]

    def report_skipped_info(self):
        job_skipped_info = self.pop.get("skipped")
        if job_skipped_info and len(job_skipped_info):
            self.skipped_info = f" Skipped Info: {job_skipped_info}."
        else:
            self.skipped_info = ""
        logger.info(f"Server {self.bridge_data.horde_url} has no valid generations for us to do.{self.skipped_info}")
        time.sleep(self.retry_interval)


class ScribePopper(JobPopper):
    def __init__(self, mm, bd):
        super().__init__(mm, bd)
        self.endpoint = "/api/v2/generate/text/pop"
        # KAI Only ever offers one single model, so we just add it to the Horde's expected array form.
        self.available_models = [self.bridge_data.model]

        self.pop_payload = {
            "name": self.bridge_data.worker_name,
            "models": self.available_models,
            "max_length": self.bridge_data.max_length,
            "max_context_length": self.bridge_data.max_context_length,
            "softprompts": self.bridge_data.softprompts[self.bridge_data.model],
            "bridge_agent": self.BRIDGE_AGENT,
            "threads": self.bridge_data.max_threads,
        }

    def horde_pop(self):
        if not super().horde_pop():
            return None
        if not self.pop.get("id"):
            self.report_skipped_info()
            return None
        return [self.pop]
