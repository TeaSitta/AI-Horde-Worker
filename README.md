# AI Horde Worker - `Scribe only fork`
This repository acts as a bridge between a KoboldAI compatible LLM inference API (Such as KoboldAI-united or aphrodite-engine) and the AI Horde.

## Important Note:
-This repository is ONLY for text(scribe) workers.

For horde *image generation* use [horde-worker-reGen](https://github.com/Haidra-Org/horde-worker-reGen).

For horde *Alchemy* or *scribe* on *Windows* use the old [AI-HORDE-WORKER](https://github.com/Haidra-Org/AI-Horde-Worker)


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

If you should see `This worker has been put into maintenance mode by its owner (403)` in the console, 
press m to exit maintenance mode(UI mode only), it may take a few moments after first starting the bridge for the worker to begin fetching jobs from the horde.

# Stopping the bridge

* First put your worker into maintenance to avoid aborting any ongoing operations. Wait until you see no more jobs running.
* In the terminal in which it's running, simply press `Ctrl+C` together.

# Updating

Use this approach if you cloned the original repository using `git clone`

1. Navigate a shell session to the folder you have the AI Horde Worker repository installed.
1. Run `git pull`
1. If git tells you the `requirements.txt` file has been updated, run `pip install -r requirements.txt -U`
1. Run `horde_scribe_bridge` script as usual.
