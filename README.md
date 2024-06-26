# AI Horde Worker - `Scribe only fork`
This repository acts as a bridge between a local KoboldAI compatible LLM API (Primarily aphrodite-engine) and the AI Horde.

If you are using kobold.cpp please use the integrated horde worker option instead.

## Important Note:
-This repository is ONLY for text(scribe) workers.

For horde *image generation* use [horde-worker-reGen](https://github.com/Haidra-Org/horde-worker-reGen).

For horde *Alchemy* or *scribe* on *Windows* use the old [AI-HORDE-WORKER](https://github.com/Haidra-Org/AI-Horde-Worker)

# Requirements

Python 3.10 or above and the PIP package manager. A python virtual environment such as vevn is optional but recommended.

# Installing

If you haven't already, go to [AI Horde and register an account](https://aihorde.net/register) to create an API key.

Store your API key somewhere secure, you will need it in order to run a worker for the horde.

This assumes you have git installed

Open a shell terminal and run these commands

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

Install the dependancies with `pip install -r requirements.txt -U`


# Running

From the AI-Horde-Worker directory, run `python horde_scribe_bridge.py`

If your KoboldAI inference API is reachable the bridge should create a worker entry on the Horde API with the
worker name you chose and then start to fetch and serve jobs to your inference engine.

If you see `This worker has been put into maintenance mode by its owner (403)` in the console,
press m to exit maintenance mode(UI mode only), it may take a few moments after first starting the bridge for the worker to begin fetching jobs from the horde.

# Stopping the bridge

* UI mode: First put your worker into maintenance mode if you plan to continue using the UI.
* Wait until you see no more jobs running then press the `q` key.

* UI Disabled: Simply press `Ctrl+C` once, the application will finish any currently running jobs before exiting.

# Updating

Use this approach if you cloned the original repository using `git clone`

1. Navigate a shell session to the folder you have the AI Horde Worker repository installed.
1. Run `git pull`
1. If git tells you the `requirements.txt` file has been updated, run `pip install -r requirements.txt -U`
1. Run `horde_scribe_bridge` script as usual.


# Arguments

The following commandline arguments are available when you run `python horde_scribe_bridge.py`

`-n` or `--worker_name "[worker name]"` The name of your worker instance (multiple worker names can be registered under a single API key).

`-a` or `--api_key "[api key]"` Your Horde API key used to authenticate to your account.

`--kai_url "[http://172.0.0.1]"` The backend url for your KoboldAI API inference engine.

`--max_threads [number]` The maximum amount of jobs to bridge between the API and inference engine at any time.

`-g` or `--gpu_display [number]` Sets the number of GPUs to display on the UI (Default = number of gpus)

`--disable_ui`  Disables the curses based console UI, displays only log messages instead.

`--queue_size [number]` The number of additional jobs to fetch from the Horde and queue until a thread becomes available (Default = 0, more than 1 should be unnessesary)

`-q` or `--quiet` Decreases the amount of logging seen

`-v` or `--verbosity` Logging level:

`-u` or `--horde_url "[http://aihorde.net]"` The horde API url to use (defaults to aihorde.net)
