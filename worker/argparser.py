import argparse

arg_parser = argparse.ArgumentParser()

arg_parser.add_argument(
    "-n",
    "--worker_name",
    action="store",
    required=False,
    type=str,
    help="The server name for the Horde. It will be shown to the world and there can be only one.",
)
arg_parser.add_argument(
    "-a",
    "--api_key",
    action="store",
    required=False,
    type=str,
    help="The API key corresponding to the owner of this Horde instance.",
)
arg_parser.add_argument(
    "-u",
    "--horde_url",
    action="store",
    required=False,
    type=str,
    help="The SH Horde URL. Where the worker will pickup prompts and send the finished generations.",
)
arg_parser.add_argument(
    "--max_threads",
    type=int,
    required=False,
    help="How many threads to use. Min: 1",
)
arg_parser.add_argument(
    "--queue_size",
    type=int,
    required=False,
    help="How many requests to keep in the queue. Min: 0",
)
arg_parser.add_argument(
    "-v",
    "--verbosity",
    action="count",
    default=0,
    help=(
        "The default logging level is ERROR or higher. "
        "This value increases the amount of logging seen in your screen"
    ),
)
arg_parser.add_argument(
    "-q",
    "--quiet",
    action="count",
    default=0,
    help=(
        "The default logging level is ERROR or higher. "
        "This value decreases the amount of logging seen in your screen"
    ),
)
arg_parser.add_argument(
    "--log_file",
    action="store_true",
    default=False,
    help="If specified will dump the log to the specified file",
)
arg_parser.add_argument(
    "--kai_url",
    action="store",
    required=False,
    help="The URL at which the KoboldAI Client API can be found.",
)
arg_parser.add_argument(
    "--disable_ui",
    action="store_true",
    required=False,
    help=("Disable the curses terminal UI and only display logging"),
)

args = arg_parser.parse_args()
