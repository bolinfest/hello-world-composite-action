#!/usr/bin/env python3

import argparse
import json
import subprocess


def main():
    args = parse_args()
    print(f"branch: {args.branch}")
    print(f"config: {args.config}")

    import os

    token = os.getenv("GITHUB_TOKEN")
    is_token_none = token is None or len(token) == 0
    print(f"is_token_none: {is_token_none}")

    env_vars = os.environ
    for key, value in env_vars.items():
        if "GITHUB" in key:
            print(f"{key}: {value}")


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
        "-f",
        f"ref={ref}",
    ]
    output = subprocess.check_output(args)
    config = json.loads(output.decode("utf-8"))
    print(json.dumps(config, indent=2))


def parse_args():
    parser = argparse.ArgumentParser(description="A simple argparse example")

    parser.add_argument("--branch", help="branch (or tag?)")
    parser.add_argument("--config", help="path to JSON config file")

    return parser.parse_args()


main()
