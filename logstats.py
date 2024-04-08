# logstats.py
# Calculate node pop and job request stats from the local worker log files.
# Usage: logstats.py [-h] [--today] [--yesterday]

import argparse
import datetime
import glob
import mmap
import re

from tqdm import tqdm

# Location of stable horde worker bridge log
LOG_FILE = "logs/bridge*.log"

# TIME PERIODS
PERIOD_ALL = 0
PERIOD_TODAY = 1
PERIOD_YESTERDAY = 2
PERIOD_HOUR = 3


# regex to identify model lines
POP_REGEX = re.compile(r".*(\d\d\d\d-\d\d-\d\d \d\d:\d\d).* Job pop took (\d+\.\d+).*node: (.*)\)")
JOB_PAYLOAD_REGEX = re.compile(r".*(\d\d\d\d-\d\d-\d\d \d\d:\d\d).* posting payload with size of.* (.*) kb")
JOB_START_GEN_REGEX = re.compile(r".*(\d\d\d\d-\d\d-\d\d \d\d:\d\d).* @ (.*):(.*) Prompt length is (.*) .*")
JOB_SUB_TIME_REGEX = re.compile(
    r".*(\d\d\d\d-\d\d-\d\d \d\d:\d\d).*contributed for (.*). Job took (.*) \
      seconds since queued and (.*) since start.",
)


class LogStats:
    def __init__(self, period=PERIOD_ALL, logfile=LOG_FILE) -> None:
        self.logfile = logfile
        self.period = period
        self.data = {}
        self.gendata = {
            "Gen Size": [float(0), 0, "tokens"],
            "Context Window": [float(0), 0, "tokens"],
            "Prompt Size": [float(0), 0, "chars"],
            "Sent Payload": [float(0), 0, "KB"],
            "Kudos": [0, 0, "kudos"],
            "Generation Time": [float(0), 0, "s"],
        }

    def get_date(self):
        # Dates in log format for filtering
        if self.period == PERIOD_TODAY:
            adate = datetime.datetime.now()
            adate = adate.strftime("%Y-%m-%d")
        elif self.period == PERIOD_YESTERDAY:
            adate = datetime.datetime.now() - datetime.timedelta(1)
            adate = adate.strftime("%Y-%m-%d")
        elif self.period == PERIOD_HOUR:
            adate = datetime.datetime.now()  # - datetime.timedelta(hours=1)
            adate = adate.strftime("%Y-%m-%d %H:")
        else:
            adate = None
        return adate

    def get_num_lines(self, file_path):
        with open(file_path, "r+") as fp:
            buf = mmap.mmap(fp.fileno(), 0)
            lines = 0
            while buf.readline():
                lines += 1
            return lines

    def parse_log(self):
        # Identify all log files and total number of log lines
        total_log_lines = sum(self.get_num_lines(logfile) for logfile in glob.glob(self.logfile))
        progress = tqdm(total=total_log_lines, leave=True, unit=" lines", unit_scale=True)
        for logfile in glob.glob(self.logfile):
            with open(logfile) as infile:
                for line in infile:
                    # Match and process the job pop line
                    if regex := POP_REGEX.match(line):

                        """WHAT IS THIS USED FOR?"""
                        if self.period and self.get_date() not in regex.group(1):
                            continue

                        # Extract api_node and time
                        poptime = regex.group(2)
                        api_node = regex.group(3).split(":")[0]
                        if api_node in self.data:

                            self.data[api_node] = [self.data[api_node][0] + float(poptime), self.data[api_node][1] + 1]

                        else:
                            self.data[api_node] = [float(poptime), 1]

                    # Match for gen/prompt request and prompt character length ( /3 ~ 'tokens' ?)
                    if regex := JOB_START_GEN_REGEX.match(line):
                        req = regex.group(2)
                        ctx = regex.group(3)
                        prmt = regex.group(4)

                        self.gendata["Gen Size"] = [
                            self.gendata["Gen Size"][0] + float(req),
                            self.gendata["Gen Size"][1] + 1,
                            self.gendata["Gen Size"][2],
                        ]
                        self.gendata["Context Window"] = [
                            self.gendata["Context Window"][0] + float(ctx),
                            self.gendata["Context Window"][1] + 1,
                            self.gendata["Context Window"][2],
                        ]
                        self.gendata["Prompt Size"] = [
                            self.gendata["Prompt Size"][0] + float(prmt),
                            self.gendata["Prompt Size"][1] + 1,
                            self.gendata["Prompt Size"][2],
                        ]

                    # Match for payload size
                    if regex := JOB_PAYLOAD_REGEX.match(line):
                        pld = regex.group(2)
                        self.gendata["Sent Payload"] = [
                            self.gendata["Sent Payload"][0] + float(pld),
                            self.gendata["Sent Payload"][1] + 1,
                            self.gendata["Sent Payload"][2],
                        ]

                    # Match for job submission kudos and processing time
                    if regex := JOB_SUB_TIME_REGEX.match(line):
                        kudos = regex.group(2)
                        proc = regex.group(4)

                        self.gendata["Kudos"] = [
                            self.gendata["Kudos"][0] + int(kudos),
                            self.gendata["Kudos"][1] + 1,
                            self.gendata["Kudos"][2],
                        ]
                        self.gendata["Generation Time"] = [
                            self.gendata["Generation Time"][0] + float(proc),
                            self.gendata["Generation Time"][1] + 1,
                            self.gendata["Generation Time"][2],
                        ]

                progress.update()
                print()

    def print_stats(self):
        # Parse our log files
        self.parse_log()

        # pop times
        total = sum(v[1] for k, v in self.data.items())
        tf = f"{total:,}"
        print(f"Average node pop times (out of {tf} pops in total)")
        for k, v in self.data.items():
            print(f"{k.split(':')[0]:15} {round(v[0]/v[1], 2)} secs {v[1]:-8} jobs from this node")
            total += v[1]
        print("----------------------------------------------------------------------")

        # job data

        for k, v in self.gendata.items():
            tf = f"{round(v[0]):,}"
            af = f"{round(v[0] / v[1] if v[1] else 0):,}"

            print("{:<15} {} {:<12} {:>15} {} {}".format(k, "Total:", tf, "Job Average:", af, v[2]))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate local worker job and pop statistics from logs")
    parser.add_argument(
        "-pop",
        "--pop",
        help="Generate horde worker pop stats only",
        action="store_true",
        default="True",
    )
    parser.add_argument(
        "-jobs",
        "--jobs",
        help="Generate horde worker job stats only",
        action="store_true",
        default="True",
    )
    parser.add_argument("-t", "--today", help="Statistics for today only", action="store_true")
    parser.add_argument("-y", "--yesterday", help="Statistics for yesterday only", action="store_true")
    parser.add_argument("-1", "--hour", help="Statistics for last hour only", action="store_true")
    args = vars(parser.parse_args())

    period = PERIOD_ALL
    if args["today"]:
        period = PERIOD_TODAY
    elif args["yesterday"]:
        period = PERIOD_YESTERDAY
    elif args["hour"]:
        period = PERIOD_HOUR

    logs = LogStats(period)
    print()
    logs.print_stats()
    print()
