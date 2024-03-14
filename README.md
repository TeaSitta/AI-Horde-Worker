THIS BRANCH IS A STRIPPED DOWN SCRIBE ONLY BRIDGE!


This repository acts as a bridge between a KoboldAI compatible inference API (Such as KoboldAI-united or aphrodite-engine) and the Kobold Horde.
It will fetch available text generation jobs from the horde, feed them to your inference API, and award you kudos for work completed.

# AI Horde Worker

## Important Note:
-This repository is ONLY for text(scribe) workers.

For *image generation* use [horde-worker-reGen](https://github.com/Haidra-Org/horde-worker-reGen).
For *Alchemy* use the old [AI-HORDE-WORKER](https://github.com/Haidra-Org/AI-Horde-Worker)



# Installing

If you haven't already, go to [AI Horde and register an account](https://aihorde.net/register), then store your API key somewhere secure. You will need it later in these instructions.

This will allow your worker to gather kudos for your account.

## Windows

### Using git (recommended)

Use these instructions if you have installed [git for windows](https://gitforwindows.org/).

This option is recommended as it will make keeping your repository up to date much easier.

1. Use your start menu to open `git GUI`
1. Select "Clone Existing Repository".
1. In the Source location put `https://github.com/Haidra-Org/AI-Horde-Worker.git`
1. In the target directory, browse to any folder you want to put the horde worker folder.
1. Press `Clone`
1. In the new window that opens up, on the top menu, go to `Repository > Git Bash`. A new terminal window will open.
1. continue with the [Running](#running) instructions

### Without git

Use these instructions if you do not have git for windows and do not want to install it. These instructions make updating the worker a bit more difficult down the line.

1. Download [the zipped version](https://github.com/Haidra-Org/AI-Horde-Worker/archive/refs/heads/main.zip)
1. Extract it to any folder of your choice
1. continue with the [Running](#running) instructions

## Linux

This assumes you have git installed

Open a bash terminal and run these commands (just copy-paste them all together)

```bash
git clone https://github.com/Haidra-Org/AI-Horde-Worker.git
cd AI-Horde-Worker
```

Continue with the [Running](#running) instructions

# Running

The below instructions refer to running scripts `horde-bridge` or `update-runtime`. Depending on your OS, append `.cmd` for windows, or `.sh` for linux.

You can double click the provided script files below from a file explorer or run it from a terminal like `bash`, `git bash` or `cmd` depending on your OS.
The latter option will allow you to see errors in case of a crash, so it's recommended.

## Update runtime

If you have just installed or updated your worker code run the `update-runtime` script. This will ensure the dependencies needed for your worker to run are up to date

This script can take 10-15 minutes to complete.

## Configure

In order to connect to the horde with your username and a good worker name, you need to configure your horde bridge. To this end, we've developed an easy WebUI you can use

To load it, simply run `bridge-webui`. It will then show you a URL you can open with your browser. Open it and it will allow you to tweak all horde options. Once you press `Save Configuration` it will create a `bridgeData.yaml` file with all the options you set.

Fill in at least:
   * Your worker name (has to be unique horde-wide)
   * Your AI Horde API key

You can use this UI and update your bridge settings even while your worker is running. Your worker should then pick up the new settings within 60 seconds.

You can also edit this file using a text editor. We also provide a `bridgeData_template.yaml` with comments on each option which you can copy into a new `bridgeData.yaml` file. This info should soon be onboarded onto the webui as well.

## Startup

For linux run `horde-scribe-bridge.sh`
For windows run `horde-scribe-bridge.cmd`



# Updating

The AI Horde workers are under constant improvement. In case there is more recent code to use follow these steps to update

First step: Shut down your worker by putting it into maintenance, and then pressing ctrl+c

## git

Use this approach if you cloned the original repository using `git clone`

1. Open a or `bash`, `git bash`, `cmd`, or `powershell` terminal depending on your OS
1. Navigate to the folder you have the AI Horde Worker repository installed if you're not already there.
1. run `git pull`
1. continue with [Running](#running) instructions above

Afterwards run the `horde-bridge` script for your OS as usual.

## zip

Use this approach if you downloaded the git repository as a zip file and extracted it somewhere.


1. delete the `worker/` directory from your folder
1. Download the [repository from github as a zip file](https://github.com/db0/AI-Horde-Worker/archive/refs/heads/main.zip)
1. Extract its contents into the same the folder you have the AI Horde Worker repository installed, overwriting any existing files
1. continue with [Running](#running) instructions above


# Stopping

* First put your worker into maintenance to avoid aborting any ongoing operations. Wait until you see no more jobs running.
* In the terminal in which it's running, simply press `Ctrl+C` together.


# Docker

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
