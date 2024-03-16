"""Get and process a job from the horde"""
import contextlib
import copy
import json
import sys
import threading
import time
import traceback

import requests

from worker.consts import RELEASE_VERSION
from worker.enums import JobStatus
from worker.logger import logger
from worker.stats import bridge_stats


class HordeJob:
    """Get and process a job from the horde"""

    retry_interval = 1

    def __init__(self, bd, pop):
        self.bridge_data = copy.deepcopy(bd)
        self.pop = pop
        self.loop_retry = 0
        self.status = JobStatus.INIT
        self.start_time = time.time()
        self.process_time = time.time()
        self.stale_time = None
        self.submit_dict = {}
        self.headers = {"apikey": self.bridge_data.api_key}

    def is_finished(self):
        """Check if the job is finished"""
        return self.status not in [JobStatus.WORKING, JobStatus.POLLING, JobStatus.INIT]

    def is_polling(self):
        """Check if the job is polling"""
        return self.status in [JobStatus.POLLING]

    def is_finalizing(self):
        """True if generation has finished even if upload is still remaining"""
        return self.status in [JobStatus.FINALIZING, JobStatus.FINALIZING_FAULTED]

    def is_stale(self):
        """Check if the job is stale"""
        if time.time() - self.start_time > 1200:
            return True
        if not self.stale_time:
            return False
        # Jobs which haven't started yet are not considered stale.
        if self.status != JobStatus.WORKING:
            return False
        return time.time() > self.stale_time

    def is_faulted(self):
        """Check if the job is faulted"""
        return self.status in [JobStatus.FAULTED, JobStatus.FINALIZING_FAULTED, JobStatus.OUT_OF_MEMORY]

    def is_out_of_memory(self):
        """Check if the job ran out of memory"""
        return self.status in [JobStatus.OUT_OF_MEMORY]

    @logger.catch(reraise=True)
    def start_job(self):
        """Starts a job from a pop request
        This method MUST be extended with the specific logic for this worker
        At the end it MUST create a new thread to submit the results to the horde"""
        # Pop new request from the Horde
        if self.pop is None:
            self.pop = self.get_job_from_server()

        if self.pop is None:
            logger.error(
                f"Something has gone wrong with {self.bridge_data.horde_url}. Please inform its administrator!",
            )
            time.sleep(self.retry_interval)
            self.status = JobStatus.FAULTED
            # The extended function should return as well
            return
        self.process_time = time.time()
        self.status = JobStatus.WORKING
        # Continue with the specific worker logic from here
        # At the end, you must call self.start_submit_thread()

    def start_submit_thread(self):
        """Starts a thread with submit_job so that we don't wait for the upload to complete
        # Not a daemon, so that it can survive after this class is garbage collected"""
        submit_thread = threading.Thread(target=self.submit_job, args=())
        submit_thread.start()
        logger.debug("Finished job in threadpool")

    def submit_job(self, endpoint="/api/v2/generate/text/submit"):
        """Submits the job to the server to earn our kudos.
        This method MUST be extended with the specific logic for this worker
        At the end it MUST set the job state to DONE"""
        if self.status == JobStatus.FAULTED or self.status == JobStatus.OUT_OF_MEMORY:
            self.submit_dict = {
                "id": self.current_id,
                "state": "faulted",
                "generation": "faulted",
                "seed": -1,
            }
            self.status = JobStatus.FINALIZING_FAULTED
        else:
            self.status = JobStatus.FINALIZING
            self.prepare_submit_payload()
        # Submit back to horde
        while self.is_finalizing():
            if self.loop_retry > 10:
                logger.error(f"Exceeded retry count {self.loop_retry} for job id {self.current_id}. Aborting job!")
                self.status = JobStatus.FAULTED
                break
            self.loop_retry += 1
            try:
                logger.debug(
                    f"posting payload with size of {round(sys.getsizeof(json.dumps(self.submit_dict)) / 1024,1)} kb",
                )
                submit_req = requests.post(
                    self.bridge_data.horde_url + endpoint,
                    json=self.submit_dict,
                    headers=self.headers,
                    timeout=60,
                )
                logger.debug(f"Upload completed in {submit_req.elapsed.total_seconds()}")
                try:
                    submit = submit_req.json()
                except json.decoder.JSONDecodeError:
                    logger.error(
                        f"Something has gone wrong with {self.bridge_data.horde_url} during submit. "
                        f"Please inform its administrator!  (Retry {self.loop_retry}/10)",
                    )
                    time.sleep(self.retry_interval)
                    continue
                if submit_req.status_code == 404:
                    logger.warning("The job we were working on got stale. Aborting!")
                    self.status = JobStatus.FAULTED
                    break
                if not submit_req.ok:
                    if submit_req.status_code == 400:
                        logger.warning(
                            f"During gen submit, server {self.bridge_data.horde_url} "
                            f"responded with status code {submit_req.status_code}: "
                            f"Job took {round(time.time() - self.start_time,1)} seconds since queued "
                            f"and {round(time.time() - self.process_time,1)} since start."
                            f"{submit['message']}. Aborting job!",
                        )
                        self.status = JobStatus.FAULTED
                        break
                    logger.warning(
                        f"During gen submit, server {self.bridge_data.horde_url} "
                        f"responded with status code {submit_req.status_code}: "
                        f"{submit['message']}. Waiting for 2 seconds...  (Retry {self.loop_retry}/10)",
                    )
                    if "errors" in submit:
                        logger.warning(f"Detailed Request Errors: {submit['errors']}")
                    time.sleep(2)
                    continue
                reward = submit_req.json()["reward"]
                time_spent_processing = round(time.time() - self.process_time, 1)

                with contextlib.suppress(ValueError):
                    reward = float(reward)
                    if time_spent_processing > (reward * 3) and not self.bridge_data.suppress_speed_warnings:
                        logger.warning(
                            "This job took longer than expected to process.",
                        )

                logger.info(
                    f"Submitted job with id {self.current_id} and contributed for {reward:.1f}. "
                    f"Job took {round(time.time() - self.start_time,1)} seconds since queued "
                    f"and {time_spent_processing} since start.",
                )

                self.post_submit_tasks(submit_req)
                if self.status == JobStatus.FINALIZING_FAULTED:
                    self.status = JobStatus.FAULTED
                else:
                    self.status = JobStatus.DONE
                break
            except requests.exceptions.ConnectionError:
                logger.warning(
                    f"Server {self.bridge_data.horde_url} unavailable during submit. "
                    f"Waiting 10 seconds...  (Retry {self.loop_retry}/10)",
                )
                time.sleep(10)
                continue
            except requests.exceptions.ReadTimeout:
                logger.warning(
                    f"Server {self.bridge_data.horde_url} timed out during submit. "
                    f"Waiting 10 seconds...  (Retry {self.loop_retry}/10)",
                )
                time.sleep(10)
                continue

    def prepare_submit_payload(self):
        """Should be overriden and prepare a self.submit_dict dictionary with the payload needed
        for this job to be submitted"""
        self.submit_dict = {}


class ScribeHordeJob(HordeJob):
    def __init__(self, bd, pop):
        # mm will always be None for the scribe
        super().__init__(bd, pop)
        self.current_model = None
        self.seed = None
        self.text = None
        self.current_model = self.bridge_data.model
        self.current_id = self.pop["id"]
        self.current_payload = self.pop["payload"]
        self.current_payload["quiet"] = True
        self.requested_softprompt = self.current_payload.get("softprompt")
        self.max_seconds = None

    @logger.catch(reraise=True)
    def start_job(self):
        """Starts a Scribe job from a pop request"""
        logger.debug("Starting job in threadpool for model: {}", self.current_model)

        super().start_job()
        if self.status == JobStatus.FAULTED:
            self.start_submit_thread()
            return
        # we also re-use this for the https timeout to llm inference
        self.max_seconds = (self.current_payload.get("max_length", 80) / 2) + 10
        self.stale_time = time.time() + self.max_seconds
        # These params will always exist in the payload from the horde
        gen_payload = self.current_payload
        if "width" in gen_payload or "length" in gen_payload or "steps" in gen_payload:
            logger.error(f"Stable Horde payload detected. Aborting. ({gen_payload})")
            self.status = JobStatus.FAULTED
            self.start_submit_thread()
            return
        try:
            logger.info(
                f"Starting generation for id {self.current_id}: {self.current_model} @ "
                f"{self.current_payload['max_length']}:{self.current_payload['max_context_length']} "
                f"Prompt length is {len(self.current_payload['prompt'])} characters",
            )
            time_state = time.time()
            if self.requested_softprompt != self.bridge_data.current_softprompt:
                requests.put(
                    self.bridge_data.kai_url + "/api/latest/config/soft_prompt",
                    json={"value": self.requested_softprompt},
                )
                time.sleep(1)  # Wait a second to unload the softprompt
            loop_retry = 0
            gen_success = False
            while not gen_success and loop_retry < 5:
                try:
                    gen_req = requests.post(
                        self.bridge_data.kai_url + "/api/latest/generate",
                        json=self.current_payload,
                        timeout=self.max_seconds,
                    )
                except requests.exceptions.ConnectionError:
                    logger.error(f"Worker {self.bridge_data.kai_url} unavailable. Retrying in 3 seconds...")
                    loop_retry += 1
                    time.sleep(3)
                    continue
                except requests.exceptions.ReadTimeout:
                    logger.error(f"Worker {self.bridge_data.kai_url} request timeout. Aborting.")
                    self.status = JobStatus.FAULTED
                    self.start_submit_thread()
                    return
                if not isinstance(gen_req.json(), dict):
                    logger.error(
                        (
                            f"KAI instance {self.bridge_data.kai_url} API unexpected response on generate: {gen_req}. "
                            "Retrying in 3 seconds..."
                        ),
                    )
                    time.sleep(3)
                    loop_retry += 1
                    continue
                if gen_req.status_code == 503:
                    logger.debug(
                        f"KAI instance {self.bridge_data.kai_url} Busy (attempt {loop_retry}). Will try again...",
                    )
                    time.sleep(3)
                    loop_retry += 1
                    continue
                if gen_req.status_code == 422:
                    logger.error(
                        f"KAI instance {self.bridge_data.kai_url} reported validation error.",
                    )
                    self.status = JobStatus.FAULTED
                    self.start_submit_thread()
                    return
                try:
                    req_json = gen_req.json()
                except json.decoder.JSONDecodeError:
                    logger.error(
                        (
                            f"Something went wrong when trying to generate on {self.bridge_data.kai_url}. "
                            "Please check the health of the KAI worker. Retrying 3 seconds...",
                        ),
                    )
                    loop_retry += 1
                    time.sleep(3)
                    continue
                try:
                    self.text = req_json["results"][0]["text"]
                except KeyError:
                    logger.error(
                        (
                            f"Unexpected response received from {self.bridge_data.kai_url}: {req_json}. "
                            "Please check the health of the KAI worker. Retrying in 3 seconds..."
                        ),
                    )
                    logger.debug(self.current_payload)
                    loop_retry += 1
                    time.sleep(3)
                    continue
                gen_success = True
            self.seed = 0
            logger.info(
                f"Generation for id {self.current_id} finished successfully"
                f" in {round(time.time() - time_state,1)} seconds.",
            )
        except Exception as err:
            stack_payload = gen_payload
            stack_payload["request_type"] = "text2text"
            stack_payload["model"] = self.current_model
            stack_payload["prompt"] = "PROMPT REDACTED"
            logger.error(
                "Something went wrong when processing request. "
                "Please check your trace.log file for the full stack trace. "
                f"Payload: {stack_payload}",
            )
            trace = "".join(traceback.format_exception(type(err), err, err.__traceback__))
            logger.trace(trace)
            self.status = JobStatus.FAULTED
            self.start_submit_thread()
            return
        self.start_submit_thread()

    def prepare_submit_payload(self):
        self.submit_dict = {
            "id": self.current_id,
            "generation": self.text,
            "seed": self.seed,
        }

    def post_submit_tasks(self, submit_req):
        bridge_stats.update_inference_stats(self.current_model, submit_req.json()["reward"])


class JobPopper:
    retry_interval = 1
    BRIDGE_AGENT = f"AI Horde Worker:{RELEASE_VERSION}:https://github.com/TeaSitta/AI-Horde-Worker"

    def __init__(self, bd):
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
    def __init__(self, bd):
        super().__init__(bd)
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
