#!/usr/bin/env python3

import argparse


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


def parse_args():
    parser = argparse.ArgumentParser(description="A simple argparse example")

    parser.add_argument("--branch", help="branch (or tag?)")
    parser.add_argument("--config", help="path to JSON config file")

    return parser.parse_args()


main()
