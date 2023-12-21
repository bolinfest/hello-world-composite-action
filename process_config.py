#!/usr/bin/env python3

import argparse
import json
import os
import subprocess


def main():
    args = parse_args()
    print(f"branch: {args.branch}")
    print(f"config: {args.config}")

    env_vars = os.environ
    for key, value in env_vars.items():
        if "GITHUB" in key:
            print(f"{key}: {value}")

    config = get_config(args.config)
    # TODO: read values in platforms
    # see if the corresponding artifacts have been uploaded in the release that
    # corresponds to `branch`.`
    # Use gh to check release info. Example:
    # gh release view 0.2.20231113-145254+995db0d6 --repo facebook/sapling --json assets
    print(json.dumps(config, indent=2))


def get_config(path_to_config: str):
    api_url = os.getenv("GITHUB_API_URL")
    repository = os.getenv("GITHUB_REPOSITORY")
    ref = os.getenv("GITHUB_SHA")

    args = [
        "gh",
        "api",
        "-X",
        "GET",
        f"{api_url}/repos/{repository}/contents/{path_to_config}",
        "-H",
        "Accept: application/vnd.github.raw",
        "-f",
        f"ref={ref}",
    ]
    output = subprocess.check_output(args)
    return json.loads(output.decode("utf-8"))


def parse_args():
    parser = argparse.ArgumentParser(description="A simple argparse example")

    parser.add_argument("--branch", help="branch (or tag?)")
    parser.add_argument("--config", help="path to JSON config file")

    return parser.parse_args()


main()
