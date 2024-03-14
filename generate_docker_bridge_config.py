import os
import random

import yaml

bridge_data_file = "bridgeData.yaml"

if os.path.isfile(bridge_data_file):
    print("bridgeData.yaml file already exists.")
    exit(0)


def get_list_environment_variable(env_var_name, default_values=None):
    env_var_value = os.getenv(env_var_name, "")
    if env_var_value == "":
        return default_values if default_values else []
    items = [item.strip() for item in env_var_value.split(",")]
    if len(items) == 1:
        return [items[0]]
    return items


def get_bool_env(env_var_name, default_value):
    value = os.getenv(env_var_name, default_value)
    if value.lower() == "false":
        return False
    if value.lower() == "true":
        return True
    raise ValueError(f"The value of {env_var_name} must be 'true' or 'false', but was {value}.")


def get_int_env(env_var_name, default_value):
    value = os.getenv(env_var_name, default_value)
    return int(value)


def get_worker_name():
    """
    HORDE_WORKER_NAME environment variable is used if it is set

    if unset, a custom prefix can be set using the envionrment variable HORDE_WORKER_PREFIX
    otherwise the default of DockerWorker will be used

    a random string of numbers will be attached to the end of the prefix to allow easy
    deployment of ephemeral containers
    """
    worker_name = os.getenv("HORDE_WORKER_NAME")
    if not worker_name:
        worker_name_prefix = os.getenv("HORDE_WORKER_PREFIX", "DockerWorker")
        worker_name = worker_name_prefix + "#" + "".join(random.choices("0123456789", k=10))
    return worker_name


config = {
    "horde_url": os.getenv("HORDE_URL", "https://aihorde.net"),
    "worker_name": get_worker_name(),
    "api_key": os.getenv("HORDE_API_KEY", "0000000000"),
    "max_length": os.getenv("MAX_LENGTH", "80"),
    "max_context_length": os.getenv("MAX_CONTEXT_LENGTH", "1024"),
    "max_threads": get_int_env("HORDE_MAX_THREADS", "1"),
    "queue_size": get_int_env("HORDE_QUEUE_SIZE", "0"),
#    "stats_output_frequency": get_int_env("HORDE_STATS_OUTPUT_FREQUENCY", "30"),
#    "ray_temp_dir": os.getenv("HORDE_RAY_TEMP_DIR", "/cache/ray"),
}

with open(bridge_data_file, "w") as file:
    print("Created bridgeData.yaml")
    yaml.dump(config, file)
