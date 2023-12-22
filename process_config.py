#!/usr/bin/env python3

import argparse
import json
import os
import subprocess
from typing import Any, Dict


def main():
    args = parse_args()
    print(f"tag: {args.tag}")
    print(f"config: {args.config}")

    env_vars = os.environ
    for key, value in env_vars.items():
        if "GITHUB" in key:
            print(f"{key}: {value}")

    config = get_config(args.config)
    print(json.dumps(config, indent=2))

    name_to_asset = get_release_assets(args.tag)
    print(json.dumps(name_to_asset, indent=2))

    platform_to_asset = map_platforms_to_assets(config, name_to_asset)


def map_platforms_to_assets(config, name_to_asset: Dict[str, Any]) -> None:
    platforms = config.get("platforms")
    if platforms is None:
        raise Exception("'platforms' field missing from config: {config}")

    platform_to_asset = {}
    for platform, value in platforms.items():
        matcher = value.get("matcher")
        if not matcher:
            raise Exception(f"missing 'matcher' field in '{value}'")
        name = matcher.get("name")
        if name:
            # Try to match the name exactly:
            for asset_name, asset in name_to_asset.items():
                if asset_name == name:
                    platform_to_asset[platform] = asset
                    break
            if platform in platform_to_asset:
                continue
            else:
                raise Exception(f"could not find asset with name '{name}'")

        name_regex = matcher.get("name_regex")
        if name_regex:
            # Try to match the name using a regular expression.
            regex = re.compile(name_regex)
            for asset_name, asset in name_to_asset.items():
                if regex.match(asset_name):
                    platform_to_asset[platform] = asset
                    break
            if platform in platform_to_asset:
                continue
            else:
                raise Exception(f"could not find asset matching regex '{name_regex}'")

    print(json.dumps(platform_to_asset, indent=2))


def get_config(path_to_config: str) -> Any:
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


def get_release_assets(tag: str) -> Dict[str, Any]:
    api_url = os.getenv("GITHUB_API_URL")
    repository = os.getenv("GITHUB_REPOSITORY")
    ref = os.getenv("GITHUB_SHA")

    args = [
        "gh",
        "release",
        "view",
        tag,
        "--repo",
        repository,
        "--json",
        "assets",
    ]
    output = subprocess.check_output(args)
    release_data = json.loads(output.decode("utf-8"))
    assets = release_data.get("assets")
    if not assets:
        raise Exception(f"no assets found for release '{tag}'")
    return {asset["name"]: asset for asset in assets if asset["state"] == "uploaded"}


def parse_args():
    parser = argparse.ArgumentParser(description="A simple argparse example")

    parser.add_argument("--tag", help="tag identifying the release")
    parser.add_argument("--config", help="path to JSON config file")

    return parser.parse_args()


main()
