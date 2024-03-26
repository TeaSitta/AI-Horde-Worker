"""This is the worker, it's the main workhorse that deals with getting requests, and spawning data processing"""

import threading
import time
from concurrent.futures import ThreadPoolExecutor

from worker.jobs import ScribeHordeJob, ScribePopper
from worker.logger import logger
from worker.stats import bridge_stats


class ScribeWorker:
    def __init__(self, this_bridge_data) -> None:
        self.bridge_data = this_bridge_data
        self.running_jobs = []
        self.waiting_jobs = []
        self.run_count = 0
        self.last_config_reload = 0
        self.is_daemon = False
        self.should_stop = False
        self.should_restart = False
        self.consecutive_executor_restarts = 0
        self.consecutive_failed_jobs = 0
        self.out_of_memory_jobs = 0
        self.soft_restarts = 0
        self.executor = None
        self.ui = None
        self.ui_class = None
        self.last_stats_time = time.time()
        self.PopperClass = ScribePopper
        self.JobClass = ScribeHordeJob
        self.shutdown_event = threading.Event()
        self.startup_terminal_ui()

    def startup_terminal_ui(self) -> None:
        # Do not launch in notebook
        self.in_notebook = hasattr(__builtins__, "__IPYTHON__")

        if self.in_notebook or self.bridge_data.disable_terminal_ui:
            return

        from worker.ui import TerminalUI

        self.ui_class = TerminalUI(self.bridge_data, self.shutdown_event)
        self.ui = threading.Thread(target=self.ui_class.run, daemon=True)
        self.ui.start()

    def on_restart(self) -> None:
        """Called when the worker loop is restarted."""
        self.soft_restarts += 1

    @logger.catch(reraise=True)
    def stop(self) -> None:
        self.should_stop = True
        self.ui_class.stop()
        logger.info("Stop methods called")

    @logger.catch(reraise=True)
    def start(self) -> None:
        self.reload_data()

        # Moved out of the loop to capture failure across soft-restarts
        self.consecutive_failed_jobs = 0

        # This is just to allow it to loop through this and handle shutdowns correctly
        while True:
            if self.should_restart:
                self.should_restart = False
                self.on_restart()
                self.run_count = 0

            with ThreadPoolExecutor(max_workers=self.bridge_data.max_threads) as self.executor:
                while not self.should_stop:
                    if self.should_restart:
                        self.executor.shutdown(wait=False)
                        self.should_restart = True
                        break
                    try:
                        if self.shutdown_event.is_set():
                            self.should_stop = True
                            self.executor.shutdown(wait=True)
                            break
                        self.process_jobs()
                    except KeyboardInterrupt:  # This is what exits on old ver
                        self.should_stop = True
                        self.shutdown_event.set()
                        break
                if self.shutdown_event.is_set() or self.soft_restarts > 15:
                    if self.soft_restarts > 15:
                        logger.error("Too many soft restarts, exiting the worker. Please review your config.")
                        logger.error("You can try asking for help in the official discord if this persists.")
                    if self.is_daemon:
                        return
                    else:  # noqa: RET505
                        logger.warning("Waiting for jobs to finish before shutting down")
                        break

    def process_jobs(self) -> None:
        if time.time() - self.last_config_reload > 30:
            self.reload_bridge_data()
        if not self.can_process_jobs():
            time.sleep(3)
            return

        # Add job to queue if we have space
        if len(self.waiting_jobs) < self.bridge_data.queue_size:
            self.add_job_to_queue()

        while len(self.running_jobs) < self.bridge_data.max_threads and self.start_job():
            pass

            # Check if any jobs are done
        for job_thread, start_time, job in self.running_jobs:
            self.check_running_job_status(job_thread, start_time, job)

        if (
            self.should_restart
            or self.should_stop
            or self.shutdown_event.is_set()
            or not self.bridge_data.kai_available
        ):
            return
        # Give the CPU a break
        time.sleep(0.02)

    def can_process_jobs(self):
        """This function returns true when this worker can start polling for jobs from the AI Horde
        This function MUST be overriden, according to the logic for this worker type"""
        kai_avail = self.bridge_data.kai_available
        if not kai_avail:
            # We do this to allow the worker to try and reload the config every 5 seconds until the KAI server is up
            self.last_config_reload = time.time() - 55
        return kai_avail

    def add_job_to_queue(self) -> None:
        """Picks up a job from the horde and adds it to the local queue
        Returns the job object created, if any"""
        if jobs := self.pop_job():
            self.waiting_jobs.extend(jobs)

    def pop_job(self):
        """Polls the AI Horde for new jobs and creates as many Job classes needed
        As the amount of jobs returned"""
        job_popper = self.PopperClass(self.bridge_data)
        pops = job_popper.horde_pop()
        if not pops:
            return None
        new_jobs = []
        for pop in pops:
            new_job = self.JobClass(self.bridge_data, pop)
            new_jobs.append(new_job)
        return new_jobs

    def start_job(self) -> bool:
        """Starts a job previously picked up from the horde
        Returns True to continue starting jobs until queue is full
        Returns False to break out of the loop and poll the horde again"""
        job = None
        # Queue disabled
        if self.bridge_data.queue_size == 0:
            if jobs := self.pop_job():
                job = jobs[0]
        elif len(self.waiting_jobs) > 0:
            job = self.waiting_jobs.pop(0)
        else:
            return False
        # Run the job
        if job:
            self.running_jobs.append((self.executor.submit(job.start_job), time.monotonic(), job))
            logger.debug("New job processing")
        else:
            logger.debug("No new job to start")
        if self.shutdown_event.is_set():
            self.should_stop = True
            return False
        return True

    def check_running_job_status(self, job_thread, start_time, job) -> None:
        """Polls the AI Horde for new jobs and creates a Job class"""
        runtime = time.monotonic() - start_time
        if job_thread.done():
            if job_thread.exception(timeout=1) or job.is_faulted():
                self.bridge_data.kai_available = False
                if job_thread.exception(timeout=1):
                    logger.error("Job failed with exception, {}", job_thread.exception())
                    logger.exception(job_thread.exception())
                if job.is_out_of_memory():
                    logger.error("Job failed with out of memory error")
                    self.out_of_memory_jobs += 1
                if self.out_of_memory_jobs >= 10:
                    logger.critical("Too many jobs have failed with out of memory error. Aborting!")
                    self.should_stop = True
                    return
                if self.consecutive_executor_restarts > 0:
                    logger.critical(
                        "Worker keeps crashing after thread executor restart. " "Cannot be salvaged. Aborting!",
                    )
                    self.should_stop = True
                    return
                self.consecutive_failed_jobs += 1
                if self.consecutive_failed_jobs >= 5:
                    logger.critical(
                        "Too many consecutive jobs have failed. " "Restarting thread executor and hope we recover...",
                    )
                    self.should_restart = True
                    self.consecutive_executor_restarts += 1
                    return
            else:
                self.consecutive_failed_jobs = 0
                self.consecutive_executor_restarts = 0
            self.run_count += 1
            logger.debug(f"Job finished successfully in {runtime:.3f}s (Total Completed: {self.run_count})")
            self.running_jobs.remove((job_thread, start_time, job))
            return

        # check if any job has run for more than 180 seconds
        if job_thread.running() and job.is_stale():
            logger.warning("Restarting all jobs, as a job is stale " f": {runtime:.3f}s")
            for (
                inner_job_thread,
                inner_start_time,
                inner_job,
            ) in self.running_jobs:  # Sometimes it's already removed
                self.running_jobs.remove((inner_job_thread, inner_start_time, inner_job))
                job_thread.cancel()
            self.should_restart = True
            return

        # Check periodically if any interesting stats should be announced
        if (
            self.bridge_data.stats_output_frequency
            and (time.time() - self.last_stats_time) > self.bridge_data.stats_output_frequency
        ):
            bonus_per_hour = self.get_uptime_kudos()
            self.last_stats_time = time.time()
            kph = bridge_stats.stats.get("kudos_per_hour", 0) + bonus_per_hour
            logger.info(f"Estimated average kudos per hour: {kph}")

    def get_uptime_kudos(self) -> int:
        """Returns the expected uptime kudos for this worker
        This should be extended for each type of worker
        """
        # *6 as this calc is per 10 minutes of uptime
        return 50 * 6

    def reload_data(self) -> None:
        """This is just a utility function to reload the configuration"""
        # Daemons are fed the configuration externally
        if not self.is_daemon:
            self.bridge_data.reload_data()

    def reload_bridge_data(self) -> None:
        self.reload_data()
        self.executor._max_workers = self.bridge_data.max_threads
        self.last_config_reload = time.time()
