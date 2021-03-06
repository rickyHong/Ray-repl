from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

import copy
import json
import tempfile
import time
import sys

import yaml

from ray.autoscaler.autoscaler import validate_config, hash_runtime_conf, \
    hash_launch_conf
from ray.autoscaler.node_provider import get_node_provider, NODE_PROVIDERS
from ray.autoscaler.tags import TAG_RAY_NODE_TYPE, TAG_RAY_LAUNCH_CONFIG, \
    TAG_RAY_RUNTIME_CONFIG, TAG_NAME
from ray.autoscaler.updater import NodeUpdaterProcess


def create_or_update_cluster(
        config_file, override_min_workers, override_max_workers, sync_only):
    """Create or updates an autoscaling Ray cluster from a config json."""

    config = yaml.load(open(config_file).read())

    validate_config(config)
    if override_min_workers is not None:
        config["min_workers"] = override_min_workers
    if override_max_workers is not None:
        config["max_workers"] = override_max_workers
    if sync_only:
        config["worker_init_commands"] = []
        config["head_init_commands"] = []

    importer = NODE_PROVIDERS.get(config["provider"]["type"])
    if not importer:
        raise NotImplementedError(
            "Unsupported provider {}".format(config["provider"]))

    bootstrap_config, _ = importer()
    config = bootstrap_config(config)
    get_or_create_head_node(config)


def teardown_cluster(config_file):
    """Destroys all nodes of a Ray cluster described by a config json."""

    config = yaml.load(open(config_file).read())

    validate_config(config)
    provider = get_node_provider(config["provider"], config["cluster_name"])
    head_node_tags = {
        TAG_RAY_NODE_TYPE: "Head",
    }
    for node in provider.nodes(head_node_tags):
        print("Terminating head node {}".format(node))
        provider.terminate_node(node)
    nodes = provider.nodes({})
    while nodes:
        for node in nodes:
            print("Terminating worker {}".format(node))
            provider.terminate_node(node)
        time.sleep(5)
        nodes = provider.nodes({})


def get_or_create_head_node(config):
    """Create the cluster head node, which in turn creates the workers."""

    provider = get_node_provider(config["provider"], config["cluster_name"])
    head_node_tags = {
        TAG_RAY_NODE_TYPE: "Head",
    }
    nodes = provider.nodes(head_node_tags)
    if len(nodes) > 0:
        head_node = nodes[0]
    else:
        head_node = None

    launch_hash = hash_launch_conf(config["head_node"], config["auth"])
    if head_node is None or provider.node_tags(head_node).get(
            TAG_RAY_LAUNCH_CONFIG) != launch_hash:
        if head_node is not None:
            print("Terminating outdated head node {}".format(head_node))
            provider.terminate_node(head_node)
        print("Launching new head node...")
        head_node_tags[TAG_RAY_LAUNCH_CONFIG] = launch_hash
        head_node_tags[TAG_NAME] = "ray-{}-head".format(config["cluster_name"])
        provider.create_node(config["head_node"], head_node_tags, 1)

    nodes = provider.nodes(head_node_tags)
    assert len(nodes) == 1, "Failed to create head node."
    head_node = nodes[0]

    runtime_hash = hash_runtime_conf(config["file_mounts"], config)

    if provider.node_tags(head_node).get(
            TAG_RAY_RUNTIME_CONFIG) != runtime_hash:
        print("Updating files on head node...")

        # Rewrite the auth config so that the head node can update the workers
        remote_key_path = "~/ray_bootstrap_key.pem"
        remote_config = copy.deepcopy(config)
        remote_config["auth"]["ssh_private_key"] = remote_key_path

        # Adjust for new file locations
        new_mounts = {}
        for remote_path in config["file_mounts"]:
            new_mounts[remote_path] = remote_path
        remote_config["file_mounts"] = new_mounts

        # Now inject the rewritten config and SSH key into the head node
        remote_config_file = tempfile.NamedTemporaryFile(
            "w", prefix="ray-bootstrap-")
        remote_config_file.write(json.dumps(remote_config))
        remote_config_file.flush()
        config["file_mounts"].update({
            remote_key_path: config["auth"]["ssh_private_key"],
            "~/ray_bootstrap_config.yaml": remote_config_file.name
        })

        updater = NodeUpdaterProcess(
            head_node,
            config["provider"],
            config["auth"],
            config["cluster_name"],
            config["file_mounts"],
            config["head_init_commands"],
            runtime_hash,
            redirect_output=False)
        updater.start()
        updater.join()
        if updater.exitcode != 0:
            print("Error: updating {} failed".format(
                provider.external_ip(head_node)))
            sys.exit(1)
    print(
        "Head node up-to-date, IP address is: {}".format(
            provider.external_ip(head_node)))
    print(
        "To monitor auto-scaling activity, you can run:\n\n"
        "  ssh -i {} {}@{} 'tail -f /tmp/raylogs/monitor-*'\n".format(
            config["auth"]["ssh_private_key"],
            config["auth"]["ssh_user"],
            provider.external_ip(head_node)))
