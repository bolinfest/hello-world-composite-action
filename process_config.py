#!/usr/bin/env python3

import argparse
import json
import logging
import os
import re
import subprocess
import sys
import tempfile

from functools import cache
from typing import Any, Dict, Literal, Tuple, Union


github_repository = os.getenv("GITHUB_REPOSITORY")
github_server_url = os.getenv("GITHUB_SERVER_URL")
gh_repo_arg = f"{github_server_url}/{github_repository}"


def main() -> None:
    exit_code = _main()
    sys.exit(exit_code)


def _main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[logging.StreamHandler()],
    )

    args = parse_args()
    config = get_config(args.config)
    logging.info(json.dumps(config, indent=2))

    tag = args.tag
    name_to_asset = get_release_assets(tag)
    logging.info(json.dumps(name_to_asset, indent=2))

    platform_entries = map_platforms(config, name_to_asset)
    if not isinstance(platform_entries, dict):
        logging.error("failed with error type {platform_entries}")
        return 1

    logging.info(json.dumps(platform_entries, indent=2))

    platforms = {}
    with tempfile.TemporaryDirectory() as temp_dir:
        for platform_name, platform_entry in platform_entries.items():
            asset, platform_config = platform_entry
            hash_algo = platform_config.get("hash", "blake3")
            size = asset.get("size")
            if size is None:
                logging.error(f"missing 'size' field in asset: {asset}")
                return 1

            name = asset.get("name")
            if name is None:
                logging.error(f"missing 'name' field in asset: {asset}")
                return 1

            hash_hex = compute_hash(temp_dir, tag, name, hash_algo, size)
            platform_fetch_info = {
                "url": asset["url"],
                "digest": {"type": hash_algo, "value": hash_hex},
                "size": size,
            }
            path = platform_config.get("path")
            if path:
                platform_fetch_info["path"] = path
            platforms[platform_name] = platform_fetch_info

    manifest = {
        "platforms": platforms,
    }

    manifest_file = f"""#!/usr/bin/env dostuff

// This is where stuff happens.

{json.dumps(manifest, indent=2)}
"""
    logging.info(manifest_file)

    return 0


def map_platforms(
    config, name_to_asset: Dict[str, Any]
) -> Union[Dict[str, Tuple[Any, Any]], Literal["NoMatchForAsset", "ParseError"]]:
    """Attempts to take every platform specified in the config and return a map
    of platform names to their corresponding asset information. If successful,
    each value in the dict will be a tuple of (asset, platform_config).

    Note that it is possible that not all assets have been uploaded yet, in
    which case "NoMatchForAsset" will be returned.
    """
    platforms = config.get("platforms")
    if platforms is None:
        logging.error("'platforms' field missing from config: {config}")
        return "ParseError"

    platform_entries = {}
    for platform, platform_config in platforms.items():
        matcher = platform_config.get("matcher")
        if not matcher:
            logging.error(f"missing 'matcher' field in '{platform_config}'")
            return "ParseError"

        name = matcher.get("name")
        if name:
            # Try to match the name exactly:
            for asset_name, asset in name_to_asset.items():
                if asset_name == name:
                    platform_entries[platform] = (asset, platform_config)
                    break
            if platform in platform_entries:
                continue
            else:
                logging.error(f"could not find asset with name '{name}'")
                return "NoMatchForAsset"

        name_regex = matcher.get("name_regex")
        if name_regex:
            # Try to match the name using a regular expression.
            regex = re.compile(name_regex)
            for asset_name, asset in name_to_asset.items():
                if regex.match(asset_name):
                    platform_entries[platform] = (asset, platform_config)
                    break
            if platform in platform_entries:
                continue
            else:
                logging.error(f"could not find asset matching regex '{name_regex}'")
                return "NoMatchForAsset"

    return platform_entries


@cache
def compute_hash(
    temp_dir: str,
    tag: str,
    name: str,
    hash_algo: Literal["blake3", "sha1", "sha256"],
    size: int,
) -> str:
    """Fetches the release entry corresponding to the specified (tag, name) tuple,
    fetches the contents, verifies the size matches, and computes the hash.

    Return value is a hex string representing the hash.
    """
    output_filename = os.path.join(temp_dir, name)

    # Fetch the url using the gh CLI to ensure authentication is handled correctly.
    args = [
        "gh",
        "release",
        "download",
        tag,
        "--repo",
        gh_repo_arg,
        # --pattern takes a "glob pattern", though we want to match an exact
        # filename. Using re.escape() seems to do the right thing, though adding
        # ^ and $ appears to break things.
        "--pattern",
        re.escape(name),
        "--output",
        output_filename,
    ]
    subprocess.run(args, check=True)
    stats = os.stat(output_filename)
    if stats.st_size != size:
        raise Exception(f"expected size {size} for {name} but got {stats.st_size}")

    if hash_algo == "blake3":
        import blake3

        hasher = blake3.blake3()
        with open(output_filename, "rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                hasher.update(chunk)
        digest = hasher.digest()
        return digest.hex()
    elif hash_algo == "sha1":
        raise NotImplementedError("sha1 is not supported")
    elif hash_algo == "sha256":
        raise NotImplementedError("sha256 is not supported")


def get_config(path_to_config: str) -> Any:
    api_url = os.getenv("GITHUB_API_URL")
    ref = os.getenv("GITHUB_SHA")

    args = [
        "gh",
        "api",
        "-X",
        "GET",
        f"{api_url}/repos/{github_repository}/contents/{path_to_config}",
        "-H",
        "Accept: application/vnd.github.raw",
        "-f",
        f"ref={ref}",
    ]
    output = subprocess.check_output(args)
    return json.loads(output.decode("utf-8"))


def get_release_assets(tag: str) -> Dict[str, Any]:
    api_url = os.getenv("GITHUB_API_URL")
    ref = os.getenv("GITHUB_SHA")

    args = [
        "gh",
        "release",
        "view",
        tag,
        "--repo",
        github_repository,
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
