# AI Horde Worker - scribe only fork
This repository acts as a bridge between a KoboldAI compatible LLM inference API (Such as KoboldAI-united or aphrodite-engine) and the Kobold Horde.

## Important Note:
-This repository is ONLY for text(scribe) workers.

For horde *image generation* use [horde-worker-reGen](https://github.com/Haidra-Org/horde-worker-reGen).

For horde *Alchemy* use the old [AI-HORDE-WORKER](https://github.com/Haidra-Org/AI-Horde-Worker)


# Installing

If you haven't already, go to [AI Horde and register an account](https://aihorde.net/register) to create an API key.

Store your API key somewhere secure, you will need it in order to run a worker for the horde.

## Windows

### Using git (recommended)

Use these instructions if you have installed [git for windows](https://gitforwindows.org/).

This option is recommended as it will make keeping your repository up to date much easier.

1. Use your start menu to open `git GUI`
1. Select "Clone Existing Repository".
1. In the Source location put `https://github.com/TeaSitta/AI-Horde-Worker.git`
1. In the target directory, browse to any folder you want to put the horde worker folder.
1. Press `Clone`
1. In the new window that opens up, on the top menu, go to `Repository > Git Bash`. A new terminal window will open.


### Without git

Use these instructions if you do not have git for windows and do not want to install it. These instructions make updating the worker a bit more difficult down the line.

1. Download [the zipped version](https://github.com/TeaSitta/AI-Horde-Worker/archive/refs/heads/main.zip)
1. Extract it to any folder of your choice


## Linux

This assumes you have git installed

Open a bash terminal and run these commands

```bash
git clone https://github.com/TeaSitta/AI-Horde-Worker.git
cd AI-Horde-Worker
```

# Configuration
Make a copy of bridgeData_template.yaml to bridgeData.yaml

Edit `bridgeData.yaml` and fill in at least:
   * Your unique worker name (Can be different than the name you used for your horde api key)
   * Your AI Horde API key (https://aihorde.net/register)


# Requirements
If installing natively or using a python venv, install the dependancies with `pip install -r requirements.txt`

RUNTIME IS CURRENTLY A WORK IN PROGRESS

# Running
After starting the bridge your worker should be in maintenance mode. 

If your KoboldAI inference API is reachable you should see `This worker has been put into maintenance mode by its owner (403)` in the console.

Press m to exit maintenance mode, this may take a few moments after first starting the bridge.

## Linux
From the AI-Horde-Worker directory, run either `horde-scribe-bridge.sh` or `python horde-scribe-bridge.py`

## Windows
From the AI-Horde-Worker directory, run `python horde-scribe-bridge.py` 

`horde-scribe-bridge.cmd` and `runtime.cmd` are for the runtime environment which is currently a work in progress


# Updating

In case there is more recent code to use follow these steps to update

First: Shut down your worker by putting it into maintenance mode, waiting for all active jobs to complete, then pressing `q` or ctrl+c

## git

Use this approach if you cloned the original repository using `git clone`

1. Open a `bash`, `cmd`, or `powershell` terminal depending on your OS
1. Navigate to the folder you have the AI Horde Worker repository installed.
1. Run `git pull`
1. If git tells you the `requirements.txt` file has been updated, run `pip install -r requirements.txt -U`
1. Run the appropriate `horde-scribe-bridge` script as usual.

## zip

Use this approach if you downloaded the git repository as a zip file and extracted it somewhere.

1. Download the [repository from github as a zip file](https://github.com/TeaSitta/AI-Horde-Worker/archive/refs/heads/main.zip)
1. Extract its contents into the existing folder you have the AI Horde Worker repository installed, overwriting any existing files
1. continue with [Running](#running) instructions above


# Stopping the bridge

* First put your worker into maintenance to avoid aborting any ongoing operations. Wait until you see no more jobs running.
* In the terminal in which it's running, simply press `Ctrl+C` together.


# Docker - WORK IN PROGRESS

To run the Docker container, specify the required environment variables:

- HORDE_API_KEY: The API key to use for authentication.

ghcr.io/Haidra-Org/ai-horde-worker:<insert release tag here>

Optional environment variables:

- HORDE_URL: The URL of the Horde server to connect to. Defaults to 'https://aihorde.net'.
- HORDE_WORKER_NAME: Leave blank if using horde_worker_prefix
- HORDE_WORKER_PREFIX: Worker name used in random worker name generation, defaults to DockerWorker ${HORDE_WORKER_PREFIX}#0123097164
- HORDE_MAX_THREADS: The maximum number of inference jobs to bridge. Defaults to '1'.
- HORDE_QUEUE_SIZE: The maximum number of jobs to queue. Defaults to '0', meaning no limit.

- HORDE_RAY_TEMP_DIR: The location of the Ray temporary directory. Defaults to '/cache/ray'.
- HORDE_DISABLE_TERMINAL_UI: Whether to disable the terminal UI. Defaults to 'false'.
