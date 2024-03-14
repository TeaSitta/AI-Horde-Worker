# AI Horde Worker - `Scribe only linux fork`
This repository acts as a bridge between a KoboldAI compatible LLM inference API (Such as KoboldAI-united or aphrodite-engine) and the AI Horde.

## Important Note:
-This repository is ONLY for text(scribe) workers.

For horde *image generation* use [horde-worker-reGen](https://github.com/Haidra-Org/horde-worker-reGen).

For horde *Alchemy* or *scribe* on *Windows* use the old [AI-HORDE-WORKER](https://github.com/Haidra-Org/AI-Horde-Worker)


# Installing

If you haven't already, go to [AI Horde and register an account](https://aihorde.net/register) to create an API key.

Store your API key somewhere secure, you will need it in order to run a worker for the horde.

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

## Linux
From the AI-Horde-Worker directory, run `python horde_scribe_bridge.py`

After starting the bridge your worker should be in maintenance mode. 

If your KoboldAI inference API is reachable you should see `This worker has been put into maintenance mode by its owner (403)` in the console.

Press m to exit maintenance mode, this may take a few moments after first starting the bridge.

# Updating

In case there is more recent code to use follow these steps to update

First: Shut down your worker by putting it into maintenance mode, waiting for all active jobs to complete, then pressing `q` or ctrl+c

## git

Use this approach if you cloned the original repository using `git clone`

1. Navigate a shell session to the folder you have the AI Horde Worker repository installed.
1. Run `git pull`
1. If git tells you the `requirements.txt` file has been updated, run `pip install -r requirements.txt -U`
1. Run `horde_scribe_bridge` script as usual.


# Stopping the bridge

* First put your worker into maintenance to avoid aborting any ongoing operations. Wait until you see no more jobs running.
* In the terminal in which it's running, simply press `Ctrl+C` together.
