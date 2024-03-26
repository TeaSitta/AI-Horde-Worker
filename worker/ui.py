# A simple terminal worker UI
# Supports audio alerts on low VRAM / RAM and toggling worker maintenance mode.
import contextlib
import curses
import locale
import os
import re
import sys
import textwrap
import threading
import time
from collections import deque
from math import trunc
from urllib import parse

import psutil
import requests

from worker.consts import RELEASE_VERSION
from worker.logger import config, logger
from worker.stats import bridge_stats
from worker.utils.gpuinfo import GPUInfo


class DequeOutputCollector:
    def __init__(self) -> None:
        self.deque = deque()

    def write(self, s) -> None:
        if s != "\n":
            self.deque.append(s.strip())

    def set_size(self, size) -> None:
        while len(self.deque) > size:
            self.deque.popleft()

    def flush(self) -> None:
        pass

    def isatty(self) -> bool:
        # No, we are not a TTY
        return False

    def close(self) -> None:
        pass


class TerminalUI:
    LOGURU_REGEX = re.compile(
        r"(\d\d\d\d-\d\d-\d\d \d\d:\d\d:\d\d).*\| "
        r"(INIT_OK|INIT_ERR|INIT_WARN|INIT|DEBUG|INFO|WARNING|ERROR).*\| (.*) - (.*)$",
    )
    KUDOS_REGEX = re.compile(r".*average kudos per hour: (\d+)")
    JOBDONE_REGEX = re.compile(
        r".*(Generation for id.*finished successfully|Finished interrogation.*)",
    )

    ART = {
        "top_left": "╓",
        "top_right": "╖",
        "bottom_left": "╙",
        "bottom_right": "╜",
        "horizontal": "─",
        "vertical": "║",
        "left-join": "╟",
        "right-join": "╢",
        "progress": "▓",
    }

    # Refresh interval in seconds to call API for remote worker stats
    REMOTE_STATS_REFRESH = 5
    # Refresh interval in seconds for API calls to get overall ai horde stats
    REMOTE_HORDE_STATS_REFRESH = 30

    COLOUR_RED = 1
    COLOUR_GREEN = 2
    COLOUR_YELLOW = 3
    COLOUR_BLUE = 4
    COLOUR_MAGENTA = 5
    COLOUR_CYAN = 6
    COLOUR_WHITE = 7

    DELIM = "::::"

    # Number of seconds between audio alerts
    ALERT_INTERVAL = 5

    JUNK = [
        "Result = False",
        "Result = True",
        "Try again with a different prompt and/or seed.",
    ]

    CLIENT_AGENT = f"AI Horde Worker:{RELEASE_VERSION}:https://github.com/TeaSitta/AI-Horde-Worker"

    def __init__(self, bridge_data, shutdown_event) -> None:
        self.shutdown_event = shutdown_event
        self.should_stop = False
        self.bridge_data = bridge_data
        self.worker_name = self.bridge_data.worker_name
        if hasattr(self.bridge_data, "horde_url"):
            self.url = self.bridge_data.horde_url
        elif hasattr(self.bridge_data, "kai_url"):
            self.url = self.bridge_data.kai_url
        self._worker_info_thread = None
        self._horde_stats_thread = None
        self._worker_model_info_thread = None
        self.main = None
        self.width = 0
        self.height = 0
        self.status_height = 17
        self.show_module = False
        self.show_debug = False
        self.last_key = None
        self.pause_log = False
        self.input = DequeOutputCollector()
        self.output = DequeOutputCollector()
        self.worker_id = None
        threading.Thread(target=self.load_worker_id, daemon=True).start()
        self.last_stats_refresh = time.time() - (TerminalUI.REMOTE_STATS_REFRESH - 3)
        self.last_horde_stats_refresh = time.time() - (TerminalUI.REMOTE_HORDE_STATS_REFRESH - 3)
        self.maintenance_mode = False
        self.gpu = GPUInfo()
        self.gpu.samples_per_second = 5
        self.commit_hash = self.get_commit_hash()
        self.cpu_average = []
        self.audio_alerts = False
        self.last_audio_alert = 0
        self.stdout = DequeOutputCollector()
        self._bck_stdout = sys.stdout
        self.stderr = DequeOutputCollector()
        self._bck_stderr = sys.stderr
        self.reset_stats()

    def initialise(self) -> None:
        # Suppress stdout / stderr
        sys.stderr = self.stderr
        sys.stdout = self.stdout
        # Remove all loguru sinks
        logger.remove()
        handlers = [sink for sink in config["handlers"] if isinstance(sink["sink"], str)]
        # Re-initialise loguru
        newconfig = {"handlers": handlers}
        logger.configure(**newconfig)
        # Add our own handler
        logger.add(self.input, level="DEBUG")
        locale.setlocale(locale.LC_ALL, "")
        self.initialise_main_window()
        self.resize()

    def load_log(self) -> None:
        self.load_log_queue()

    def parse_log_line(self, line):
        if regex := TerminalUI.LOGURU_REGEX.match(line):
            if not self.show_debug and regex.group(2) == "DEBUG":
                return None
            if regex.group(2) == "ERROR":
                self.error_count += 1
            elif regex.group(2) == "WARNING":
                self.warning_count += 1
            return f"{regex.group(2)}::::{regex.group(1)}::::{regex.group(3)}::::{regex.group(4)}"
        return None

    def load_log_queue(self) -> None:
        lines = list(self.input.deque)
        self.input.deque.clear()
        for line in lines:
            ignore = False
            for skip in TerminalUI.JUNK:
                if skip.lower() in line.lower():
                    ignore = True
            if ignore:
                continue
            log_line = self.parse_log_line(line)
            if not log_line:
                continue
            self.output.write(log_line)
            if regex := TerminalUI.KUDOS_REGEX.match(line):
                self.kudos_per_hour = int(regex.group(1))
            if regex := TerminalUI.JOBDONE_REGEX.match(line):
                self.jobs_done += 1

        self.output.set_size(self.height)

    def initialise_main_window(self) -> None:
        # getch doesn't block
        self.main.nodelay(True)
        # Hide cursor
        curses.curs_set(0)
        # Define colours
        curses.start_color()
        curses.init_pair(1, curses.COLOR_RED, curses.COLOR_BLACK)
        curses.init_pair(2, curses.COLOR_GREEN, curses.COLOR_BLACK)
        curses.init_pair(3, curses.COLOR_YELLOW, curses.COLOR_BLACK)
        curses.init_pair(4, curses.COLOR_BLUE, curses.COLOR_BLACK)
        curses.init_pair(5, curses.COLOR_MAGENTA, curses.COLOR_BLACK)
        curses.init_pair(6, curses.COLOR_CYAN, curses.COLOR_BLACK)
        curses.init_pair(7, curses.COLOR_WHITE, curses.COLOR_BLACK)

    def resize(self) -> None:
        # Determine terminal size
        curses.update_lines_cols()
        # Determine terminal size
        self.height, self.width = self.main.getmaxyx()

    def print(self, win, y, x, text, colour=None) -> None:
        # Ensure we're going to fit
        height, width = win.getmaxyx()
        if y < 0 or x < 0 or x + len(text) > width or y > height:
            return
        # Always highlight certain text
        if text == "Pending":
            colour = curses.color_pair(TerminalUI.COLOUR_YELLOW)
        with contextlib.suppress(curses.error):
            if not colour:
                win.addstr(y, x, text)
            else:
                win.addstr(y, x, text, colour)

    def draw_line(self, win, y, label) -> None:
        height, width = win.getmaxyx()
        self.print(
            win,
            y,
            0,
            TerminalUI.ART["left-join"] + TerminalUI.ART["horizontal"] * (width - 2) + TerminalUI.ART["right-join"],
        )
        self.print(win, y, 2, label)

    def draw_box(self, y, x, width, height) -> None:  # noqa: ARG002
        # An attempt to work cross platform, box() doesn't.

        # Draw the top border
        self.print(
            self.main,
            0,
            0,
            TerminalUI.ART["top_left"] + TerminalUI.ART["horizontal"] * (width - 2) + TerminalUI.ART["top_right"],
        )

        # Draw the side borders
        for y in range(1, height - 1):
            self.print(self.main, y, 0, TerminalUI.ART["vertical"])
            self.print(self.main, y, width - 1, TerminalUI.ART["vertical"])

        # Draw the bottom border
        self.print(
            self.main,
            height - 1,
            0,
            TerminalUI.ART["bottom_left"] + TerminalUI.ART["horizontal"] * (width - 2),
        )
        self.print(self.main, height - 1, width - 1, TerminalUI.ART["bottom_right"])

    def seconds_to_timestring(self, seconds):
        if isinstance(seconds, str):
            return seconds
        hours = int(seconds // 3600)
        days = hours // 24
        hours %= 24
        result = ""
        if days:
            result += f"{days}d "
        if hours:
            result += f"{hours}h "
        if minutes := int((seconds % 3600) // 60):
            result += f"{minutes}m"
        return result

    def get_uptime(self) -> str:
        hours = int((time.time() - self.start_time) // 3600)
        minutes = int(((time.time() - self.start_time) % 3600) // 60)
        seconds = int((time.time() - self.start_time) % 60)
        return f"{hours}:{minutes:02}:{seconds:02}"

    def reset_stats(self) -> None:
        bridge_stats.reset()
        self.start_time = time.time()
        self.jobs_done = 0
        self.kudos_per_hour = 0
        self.pop_time = 0
        self.jobs_per_hour = "Pending"
        self.total_kudos = "Pending"
        self.total_worker_kudos = "Pending"
        self.total_uptime = "Pending"
        self.avg_kudos_per_job = "Pending"
        self.threads = "Pending"
        self.context = ""
        self.total_failed_jobs = "Pending"
        self.modelname = "Pending"
        self.total_jobs = "Pending"
        self.queued_requests = "Pending"
        self.worker_count = "Pending"
        self.thread_count = "Pending"
        # self.queued_mps = "Pending"
        # self.last_minute_mps = "Pending"
        # self.queue_time = "Pending"
        self.model_queue = "Pending"
        self.model_eta = "Pending"
        self.model_threads = "Pending"
        self.error_count = 0
        self.warning_count = 0

    def print_switch(self, y, x, label, switch):
        colour = curses.color_pair(TerminalUI.COLOUR_CYAN) if switch else curses.color_pair(TerminalUI.COLOUR_WHITE)
        self.print(self.main, y, x, label, colour)
        return x + len(label) + 2

    def get_free_ram(self) -> str:
        mem = psutil.virtual_memory().available
        percent = 100 - trunc(psutil.virtual_memory().percent)
        mem /= 1048576
        unit = "MB"
        if mem >= 1024:
            mem /= 1024
            unit = "GB"
        mem = trunc(mem)
        return f"{mem} {unit} ({percent}%)"

    def get_cpu_usage(self) -> str:
        cpu = psutil.cpu_percent()
        self.cpu_average.append(cpu)
        self.cpu_average = self.cpu_average[-(self.gpu.samples_per_second * 60 * 5) :]
        avg_cpu = trunc(sum(self.cpu_average) / len(self.cpu_average))
        cpu = f"{trunc(cpu)}%".ljust(3)
        return f"{cpu} ({avg_cpu}%)"

    def print_status(self) -> None:
        # This is the design template: (80 columns)
        # ╔═Horde Worker Name═════════════════════════════════════════(25.10.10)══000000═╗
        # ║   Uptime: 0:14:35      Jobs Completed: 6        Avg Kudos Per Job: 103       ║
        # ║ pop time: 0.58s        Kudos Per Hour: 5283         Jobs Per Hour: 524966    ║
        # ║    Model: Llama2...          Warnings: 9999                Errors: 10        ║
        # ║ CPU Load: 99% (99%)          Free RAM: 2 GB (10%)       Job Fetch: 2.32s     ║
        # ╟─NVIDIA GeForce RTX 3090──────────────────────────────────────────────────────╢
        # ║    Load: 100% (90%)        VRAM Total: 24576MiB         Fan Speed: 100%      ║
        # ║    Temp: 100C (58C)         VRAM Used: 16334MiB           PCI Gen: 5         ║
        # ║   Power: 460W (178W)        VRAM Free: 8241MiB          PCI Width: 32x       ║
        # ╟─Worker───────────────────────────────────────────────────────────────────────╢
        # ║  Threads: 6               Worker Kudos: 9385297         Total Jobs: 701138   ║
        # ║  Context: 8192            Total Uptime: 34d 19h 14m    Jobs Failed: 972      ║
        # ╟───Horde──────────────────────────────────────────────────────────────────────╢
        # ║  Model Queue: 43           Jobs Queued: 99999        Total Workers: 100      ║
        # ║    Model ETA: 120s                                   Total Threads: 1000     ║
        # ║ Model Threads: 8                                                             ║
        # ║     (m)aintenance  (s)ource  (d)ebug  (p)ause log  (a)lerts  (r)eset  (q)uit ║
        # ╙──────────────────────────────────────────────────────────────────────────────╜

        # Define three colums centres
        col_left = 12
        col_mid = self.width // 2
        col_right = self.width - 12

        # How many GPUs are we using?
        num_gpus = self.gpu.get_num_gpus()

        # Define rows on which sections start
        row_local = 0
        row_gpu = row_local + 5
        row_total = row_gpu + (4 * num_gpus)
        row_horde = row_total + 3
        self.status_height = row_horde + 6

        def label(y, x, label) -> None:
            self.print(self.main, y, x - len(label) - 1, label)

        self.draw_box(0, 0, self.width, self.status_height)
        self.draw_line(self.main, row_gpu, "")
        self.draw_line(self.main, row_total, "Worker")
        self.draw_line(self.main, row_horde, "Horde")
        self.print(self.main, row_local, 2, f"{self.worker_name}")
        self.print(self.main, row_local, self.width - 19, f"({RELEASE_VERSION})")
        self.print(self.main, row_local, self.width - 8, f"{self.commit_hash[:6]}")

        label(row_local + 1, col_left, "Uptime:")
        label(row_local + 2, col_left, "pop time:")
        label(row_local + 3, col_left, "Model:")
        label(row_local + 4, col_left, "CPU Load:")
        label(row_local + 1, col_mid, "Jobs Completed:")
        label(row_local + 2, col_mid, "Kudos Per Hour:")
        label(row_local + 3, col_mid, "Warnings:")
        label(row_local + 4, col_mid, "Free RAM:")
        label(row_local + 1, col_right, "Avg Kudos Per Job:")
        label(row_local + 2, col_right, "Jobs Per Hour:")
        label(row_local + 3, col_right, "Errors:")
        label(row_local + 4, col_right, "Job Fetch:")

        tmp_row_gpu = row_gpu
        # Was forced to 1 TODO: set via argument/config/UI control
        for gpu_i in range(num_gpus):  # noqa B007
            label(tmp_row_gpu + 1, col_left, "Load:")
            label(tmp_row_gpu + 2, col_left, "Temp:")
            label(tmp_row_gpu + 3, col_left, "Power:")
            label(tmp_row_gpu + 1, col_mid, "VRAM Total:")
            label(tmp_row_gpu + 2, col_mid, "VRAM Used:")
            label(tmp_row_gpu + 3, col_mid, "VRAM Free:")
            label(tmp_row_gpu + 1, col_right, "Fan Speed:")
            label(tmp_row_gpu + 2, col_right, "PCI Gen:")
            label(tmp_row_gpu + 3, col_right, "PCI Width:")
            tmp_row_gpu += 4

        label(row_total + 1, col_left, "Threads:")
        label(row_total + 2, col_left, "Context:")
        label(row_total + 1, col_mid, "Worker Kudos:")
        label(row_total + 2, col_mid, "Total Uptime:")
        label(row_total + 1, col_right, "Total Jobs:")
        label(row_total + 2, col_right, "Jobs Failed:")

        label(row_horde + 1, col_left + 5, "Model Queue:")
        label(row_horde + 2, col_left + 5, "Model ETA:")
        label(row_horde + 3, col_left + 5, "Model Threads:")
        label(row_horde + 1, col_mid, "Total Jobs Queued:")
        # label(row_horde + 2, col_mid, "Total Workers:")
        label(row_horde + 1, col_right, "Total Workers:")
        # label(row_horde + 1, col_right, "Total Queue Time:")
        label(row_horde + 2, col_right, "Total Threads:")

        self.print(self.main, row_local + 1, col_left, f"{self.get_uptime()}")
        self.print(self.main, row_local + 1, col_mid, f"{self.jobs_done}")
        self.print(self.main, row_local + 1, col_right, f"{self.avg_kudos_per_job}")

        self.print(self.main, row_local + 2, col_left, f"{self.pop_time} s")
        self.print(self.main, row_local + 2, col_mid, f"{self.kudos_per_hour}")
        self.print(self.main, row_local + 2, col_right, f"{self.jobs_per_hour}")

        self.print(self.main, row_local + 3, col_left, f"{self.modelname}")
        self.print(self.main, row_local + 3, col_mid, f"{self.warning_count}")
        self.print(self.main, row_local + 3, col_right, f"{self.error_count}")

        # Add some warning colours to free ram
        ram = self.get_free_ram()
        ram_colour = curses.color_pair(TerminalUI.COLOUR_WHITE)
        if re.match(r"\d{3,4} MB", ram):
            ram_colour = curses.color_pair(TerminalUI.COLOUR_MAGENTA)
        elif re.match(r"(\d{1,2}) MB", ram):
            if self.audio_alerts and time.time() - self.last_audio_alert > TerminalUI.ALERT_INTERVAL:
                self.last_audio_alert = time.time()
                curses.beep()
            ram_colour = curses.color_pair(TerminalUI.COLOUR_RED)

        self.print(self.main, row_local + 4, col_left, f"{self.get_cpu_usage()}")
        self.print(
            self.main,
            row_local + 4,
            col_mid,
            f"{self.get_free_ram()}",
            ram_colour,
        )

        gpus = []
        for gpu_i in range(num_gpus):
            gpus.append(self.gpu.get_info(gpu_i))
        for gpu_i, gpu in enumerate(gpus):
            if gpu:
                # Add some warning colours to free vram
                vram_colour = curses.color_pair(TerminalUI.COLOUR_WHITE)
                if re.match(r"\d\d\d MB", gpu["vram_free"]):
                    vram_colour = curses.color_pair(TerminalUI.COLOUR_MAGENTA)
                elif re.match(r"(\d{1,2}) MB", gpu["vram_free"]):
                    if self.audio_alerts and time.time() - self.last_audio_alert > TerminalUI.ALERT_INTERVAL:
                        self.last_audio_alert = time.time()
                        curses.beep()
                    vram_colour = curses.color_pair(TerminalUI.COLOUR_RED)

                gpu_name = gpu["product"]
                if num_gpus > 1:
                    gpu_name = f"{gpu_name} #{gpu_i}"
                self.draw_line(self.main, row_gpu, gpu_name)

                self.print(
                    self.main,
                    row_gpu + 1,
                    col_left,
                    f"{gpu['load']:4} ({gpu['avg_load']})",
                )
                self.print(self.main, row_gpu + 1, col_mid, f"{gpu['vram_total']}")
                self.print(self.main, row_gpu + 1, col_right, f"{gpu['fan_speed']}")

                self.print(
                    self.main,
                    row_gpu + 2,
                    col_left,
                    f"{gpu['temp']:4} ({gpu['avg_temp']})",
                )
                self.print(self.main, row_gpu + 2, col_mid, f"{gpu['vram_used']}")
                self.print(self.main, row_gpu + 2, col_right, f"{gpu['pci_gen']}")

                self.print(
                    self.main,
                    row_gpu + 3,
                    col_left,
                    f"{gpu['power']:4} ({gpu['avg_power']})",
                )
                self.print(
                    self.main,
                    row_gpu + 3,
                    col_mid,
                    f"{gpu['vram_free']}",
                    vram_colour,
                )
                self.print(self.main, row_gpu + 3, col_right, f"{gpu['pci_width']}")

                row_gpu += 4

        self.print(self.main, row_total + 1, col_left, f"{self.threads}")
        self.print(self.main, row_total + 1, col_mid, f"{self.total_kudos}")
        self.print(self.main, row_total + 1, col_right, f"{self.total_jobs}")

        self.print(
            self.main,
            row_total + 2,
            col_left,
            f"{self.bridge_data.max_context_length}",
        )
        self.print(
            self.main,
            row_total + 2,
            col_mid,
            f"{self.seconds_to_timestring(self.total_uptime)}",
        )
        self.print(self.main, row_total + 2, col_right, f"{self.total_failed_jobs}")

        self.print(self.main, row_horde + 1, col_left + 5, f"{self.model_queue} jobs")
        self.print(self.main, row_horde + 1, col_mid, f"{self.queued_requests}")
        # self.print(
        #     self.main,
        #     row_horde + 1,
        #     col_right,
        #     f"{self.seconds_to_timestring(self.queue_time)}",
        # )
        self.print(self.main, row_horde + 1, col_right, f"{self.worker_count}")

        self.print(self.main, row_horde + 2, col_left + 5, f"{self.model_eta}s")
        # self.print(self.main, row_horde + 2, col_mid, f"{self.worker_count}")
        self.print(self.main, row_horde + 2, col_right, f"{self.thread_count}")

        self.print(self.main, row_horde + 3, col_left + 5, f"{self.model_threads}")

        inputs = [
            "(m)aintenance",
            "(s)ource",
            "(d)ebug",
            "(p)ause log",
            "(a)udio alerts",
            "(r)eset",
            "(q)uit",
        ]
        x = self.width - len("  ".join(inputs)) - 2
        y = row_horde + 4
        x = self.print_switch(y, x, inputs[0], self.maintenance_mode)
        x = self.print_switch(y, x, inputs[1], self.show_module)
        x = self.print_switch(y, x, inputs[2], self.show_debug)
        x = self.print_switch(y, x, inputs[3], self.pause_log)
        x = self.print_switch(y, x, inputs[4], self.audio_alerts)
        x = self.print_switch(y, x, inputs[5], False)
        x = self.print_switch(y, x, inputs[6], False)

    def fit_output_to_term(self, output):
        # How many lines of output can we fit, after line wrapping?
        termrows = self.height - self.status_height
        linecount = 0
        maxrows = 0
        for i, fullline in enumerate(reversed(output)):
            line = fullline.split(TerminalUI.DELIM)[-1:][0]
            # 21 is the timestamp length
            linecount += len(textwrap.wrap(line, self.width - 21))
            if self.show_module:
                linecount += 1
            if linecount > termrows:
                maxrows = i
                break
        # Truncate the output so it fits
        return output[-maxrows:]

    def print_log(self) -> None:
        if not self.pause_log:
            self.load_log()
        output = list(self.output.deque)
        if not output:
            return

        output = self.fit_output_to_term(output)

        y = self.status_height
        inputrow = 0
        last_timestamp = ""
        while y < self.height and inputrow < len(output):
            # Print any log info we have
            cat, nextwhen, source, msg = output[inputrow].split(TerminalUI.DELIM)
            colour = TerminalUI.COLOUR_WHITE
            if cat == "DEBUG":
                colour = TerminalUI.COLOUR_WHITE
            elif cat == "ERROR":
                colour = TerminalUI.COLOUR_RED
            elif cat in ["INIT"]:
                colour = TerminalUI.COLOUR_WHITE
            elif cat in ["INIT_OK"]:
                colour = TerminalUI.COLOUR_GREEN
                msg = f"OK: {msg}"
            elif cat in ["INIT_WARN"]:
                colour = TerminalUI.COLOUR_YELLOW
                msg = f"Warning: {msg}"
            elif cat in ["INIT_ERR"]:
                colour = TerminalUI.COLOUR_RED
                msg = f"Error: {msg}"
            elif cat == "WARNING":
                colour = TerminalUI.COLOUR_YELLOW

            # Timestamp
            when = nextwhen if nextwhen != last_timestamp else ""
            last_timestamp = nextwhen
            length = len(last_timestamp) + 2
            self.print(
                self.main,
                y,
                1,
                f"{when}",
                curses.color_pair(TerminalUI.COLOUR_GREEN),
            )

            # Source file name
            if self.show_module:
                self.print(
                    self.main,
                    y,
                    length,
                    f"{source}",
                    curses.color_pair(TerminalUI.COLOUR_GREEN),
                )
                y += 1
                if y > self.height:
                    break

            # Actual log message
            text = textwrap.wrap(msg, self.width - length)
            for line in text:
                self.print(self.main, y, length, line, curses.color_pair(colour))
                y += 1
                if y > self.height:
                    break
            inputrow += 1

    def load_worker_id(self) -> None:
        try:
            while not self.worker_id:
                if not self.worker_name:
                    logger.warning("Still waiting to determine worker name")
                    time.sleep(5)
                    continue
                workers_url = f"{self.url}/api/v2/workers"
                try:
                    r = requests.get(
                        workers_url,
                        headers={"client-agent": TerminalUI.CLIENT_AGENT},
                        timeout=5,
                    )
                except requests.exceptions.Timeout:
                    logger.warning("Timeout while waiting for worker ID from API")
                except requests.exceptions.RequestException as ex:
                    logger.error(f"Failed to get worker ID {ex}")
                if r.ok:
                    worker_json = r.json()
                    self.worker_id = next(
                        (item["id"] for item in worker_json if item["name"] == self.worker_name),
                        None,
                    )
                    if self.worker_id:
                        logger.warning(f"Found worker ID {self.worker_id}")
                    else:
                        # Our worker is not yet in the worker results from the API (cache delay)
                        logger.warning("Waiting for Worker ID from the AI Horde")
                else:
                    logger.warning(f"Failed to get worker ID {r.status_code}")
                if self.shutdown_event.is_set():
                    break
                time.sleep(5)
        except Exception as ex:
            logger.warning(str(ex))

    def set_maintenance_mode(self, enabled) -> None:
        if not self.bridge_data.api_key or not self.worker_id:
            return
        header = {
            "apikey": self.bridge_data.api_key,
            "client-agent": TerminalUI.CLIENT_AGENT,
        }
        payload = {"maintenance": enabled}
        if enabled:
            logger.warning("Attempting to enable maintenance mode.")
        else:
            logger.warning("Attempting to disable maintenance mode.")
        worker_URL = f"{self.url}/api/v2/workers/{self.worker_id}"
        res = requests.put(worker_URL, json=payload, headers=header)
        if not res.ok:
            logger.error(f"Maintenance mode failed: {res.text}")

    def get_remote_worker_info(self) -> None:
        """API call for worker ID (Maint mode, kudos, uptime, etc)"""
        try:
            if not self.worker_id:
                return
            worker_URL = f"{self.url}/api/v2/workers/{self.worker_id}"

            # request worker data from horde API
            try:
                r = requests.get(
                    worker_URL,
                    headers={"client-agent": TerminalUI.CLIENT_AGENT},
                    timeout=5,
                )
            except requests.exceptions.Timeout:
                logger.warning("Worker info API failed to respond in time")
                return
            except requests.exceptions.RequestException:
                logger.warning("Worker info API request failed {ex}")
                return
            if not r.ok:
                logger.warning(
                    f"Calling Worker information API failed ({r.status_code})",
                )
                return
            data = r.json()

            self.maintenance_mode = data.get("maintenance_mode", False)
            self.total_worker_kudos = data.get("kudos_details", {}).get("generated", 0)
            if self.total_worker_kudos is not None:
                self.total_worker_kudos = int(self.total_worker_kudos)
            self.total_jobs = data.get("requests_fulfilled", 0)
            self.total_kudos = int(data.get("kudos_rewards", 0))
            self.threads = data.get("threads", 0)
            self.total_uptime = data.get("uptime", 0)
            self.total_failed_jobs = data.get("uncompleted_jobs", 0)
            self.modelname = data.get("models")[0]
        except Exception as ex:
            logger.warning(str(ex))

    def get_remote_horde_stats(self) -> None:
        try:
            url = f"{self.url}/api/v2/status/performance"
            try:
                r = requests.get(
                    url,
                    headers={"client-agent": TerminalUI.CLIENT_AGENT},
                    timeout=10,
                )
            except requests.exceptions.Timeout:
                pass
            except requests.exceptions.RequestException:
                return
            if not r.ok:
                logger.warning(f"Calling AI Horde stats API failed ({r.status_code})")
                return

            data = r.json()
            self.queued_requests = int(data.get("queued_requests", 0))
            self.worker_count = int(data.get("worker_count", 1))
            self.thread_count = int(data.get("thread_count", 0))
            # self.queued_mps = int(data.get("queued_megapixelsteps", 0))
            # self.last_minute_mps = int(data.get("past_minute_megapixelsteps", 0))
            # self.queue_time = (self.queued_mps / self.last_minute_mps) * 60

            # Get model queue stats
            if self.modelname == "Pending" or not self.worker_id:
                # logger.info(f"Skipping model info API call")
                return
            # Must double encode forward slashes in model names for this horde API call
            modelname_singleenc = parse.quote(self.modelname, safe="")
            modelname_doubleenc = parse.quote(modelname_singleenc, safe="")
            models_url = f"{self.url}/api/v2/status/models/{modelname_doubleenc}"
            try:
                r_models = requests.get(
                    models_url,
                    headers={"client-agent": TerminalUI.CLIENT_AGENT},
                    timeout=5,
                )
            except requests.exceptions.Timeout:
                return
            except requests.exceptions.RequestException as ex:
                logger.warning(f"Models info API request failed {ex}")
                return
            if not r_models.ok:
                logger.warning(
                    f"Calling Models information API failed ({r_models.status_code})",
                )
                return
            models_json = r_models.json()
            self.model_queue = int(models_json[0].get("jobs", 0))
            self.model_eta = models_json[0].get("eta", 0)
            self.model_threads = models_json[0].get("count", 0)
        except IndexError:
            return
        except Exception as ex:
            logger.warning(str(ex))

    def update_stats(self) -> None:
        # Recent job pop times
        if "pop_time_avg_5_mins" in bridge_stats.stats:
            self.pop_time = bridge_stats.stats["pop_time_avg_5_mins"]
        if "jobs_per_hour" in bridge_stats.stats:
            self.jobs_per_hour = bridge_stats.stats["jobs_per_hour"]
        if "avg_kudos_per_job" in bridge_stats.stats:
            self.avg_kudos_per_job = bridge_stats.stats["avg_kudos_per_job"]

        if time.time() - self.last_stats_refresh > TerminalUI.REMOTE_STATS_REFRESH:
            self.last_stats_refresh = time.time()
            if (self._worker_info_thread and not self._worker_info_thread.is_alive()) or not self._worker_info_thread:
                self._worker_info_thread = threading.Thread(
                    target=self.get_remote_worker_info,
                    daemon=True,
                ).start()

        if time.time() - self.last_horde_stats_refresh > TerminalUI.REMOTE_HORDE_STATS_REFRESH:
            self.last_horde_stats_refresh = time.time()
            if (self._horde_stats_thread and not self._horde_stats_thread.is_alive()) or not self._horde_stats_thread:
                self._horde_stats_thread = threading.Thread(
                    target=self.get_remote_horde_stats,
                    daemon=True,
                ).start()

    def get_commit_hash(self):
        head_file = os.path.join(".git", "HEAD")
        if not os.path.exists(head_file):
            return ""
        try:
            with open(head_file) as f:
                head_contents = f.read().strip()

            if not head_contents.startswith("ref:"):
                return head_contents

            ref_path = os.path.join(".git", *head_contents[5:].split("/"))

            with open(ref_path) as f:
                return f.read().strip()

        except Exception:
            return ""

    def get_input(self) -> bool:
        """Get keyboard input from the UI
        Return false on quit, else true"""
        x = self.main.getch()
        self.last_key = x
        if x == curses.KEY_RESIZE:
            self.resize()
        elif x == ord("d") or x == ord("D"):
            self.show_debug = not self.show_debug
        elif x == ord("s") or x == ord("S"):
            self.show_module = not self.show_module
        elif x == ord("a") or x == ord("A"):
            self.audio_alerts = not self.audio_alerts
        elif x == ord("r") or x == ord("R"):
            self.reset_stats()
        elif x == ord("q") or x == ord("Q"):
            self.shutdown_event.set()
            raise KeyboardInterrupt

        elif x == ord("m") or x == ord("M"):
            self.maintenance_mode = not self.maintenance_mode
            self.set_maintenance_mode(self.maintenance_mode)
        elif x == ord("p") or x == ord("P"):
            self.pause_log = not self.pause_log
        return True

    def poll(self) -> bool:
        if not self.get_input():
            return False
        self.main.erase()
        self.update_stats()
        self.print_status()
        self.print_log()
        self.main.refresh()
        return True

    def main_loop(self, stdscr) -> None:
        if not stdscr:
            self.stop()
            logger.error("Failed to initialise curses")
            return

        self.main = stdscr
        while True:
            try:
                self.initialise()
                while True:
                    if self.should_stop:
                        return
                    if not self.poll():
                        return
                    time.sleep(1 / self.gpu.samples_per_second)
            except KeyboardInterrupt:
                self.should_stop = True
                return
            except Exception as exc:
                logger.error(str(exc))

    def run(self) -> None:
        self.should_stop = False
        curses.wrapper(self.main_loop)
        self.stop()

    def stop(self) -> None:
        self.should_stop = True
        # Restore the terminal
        sys.stdout = self._bck_stdout
        sys.stderr = self._bck_stderr
        curses.nocbreak()
        self.main.keypad(False)
        curses.echo()
        curses.endwin()


if __name__ == "__main__":
    print("Enable the terminal UI in bridgeData.yaml")
