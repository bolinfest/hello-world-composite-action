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
    repo: str = args.repo
    if not repo:
        raise ValueError(
            "no repo specified: must specify --repo or set the GITHUB_REPOSITORY environment variable"
        )

    output_folder = args.output
    if not output_folder:
        output_folder = tempfile.mkdtemp(prefix=f"{repo.replace('/', '_')}_dotslash")
    logging.info(f"DotSlash files will be written to `{output_folder}")

    tag = args.tag
    github_server_url = args.server
    api_server_url = args.api_server
    gh_repo_arg = f"{github_server_url}/{repo}"

    config = get_config(
        path_to_config=args.config,
        config_ref=args.config_ref,
        github_repository=repo,
        api_url=api_server_url,
    )
    logging.info(json.dumps(config, indent=2))

    name_to_asset = get_release_assets(tag=tag, github_repository=repo)
    logging.info(json.dumps(name_to_asset, indent=2))

    platform_entries = map_platforms(config, name_to_asset)
    if not isinstance(platform_entries, dict):
        logging.error("failed with error type {platform_entries}")
        return 1

    logging.info(json.dumps(platform_entries, indent=2))

    manifest_file_contents = generate_manifest_file(gh_repo_arg, tag, platform_entries)
    logging.info(manifest_file_contents)

    release_filename = config.get("release_filename")
    if release_filename:
        output_file = os.path.join(output_folder, release_filename)
        with open(output_file, "w") as f:
            f.write(manifest_file_contents)
        logging.info(f"wrote manifest to {output_file}")

        # Upload manifest to release, but do not clobber. Note that this may
        # fail if this action has been called more than once for the same config.
        subprocess.run(
            [
                "gh",
                "release",
                "upload",
                tag,
                output_file,
                "--repo",
                gh_repo_arg,
            ]
        )

    return 0


def generate_manifest_file(gh_repo_arg: str, tag: str, platform_entries) -> str:
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

            hash_hex = compute_hash(gh_repo_arg, temp_dir, tag, name, hash_algo, size)
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

    return f"""#!/usr/bin/env dostuff

// This is where stuff happens.

{json.dumps(manifest, indent=2)}
"""


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
    gh_repo_arg: str,
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
        import hashlib

        hasher = hashlib.sha256()
        with open(output_filename, "rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                hasher.update(chunk)
        return hasher.hexdigest()


def get_config(
    *, path_to_config: str, config_ref: str, github_repository: str, api_url: str
) -> Any:
    args = [
        "gh",
        "api",
        "-X",
        "GET",
        f"{api_url}/repos/{github_repository}/contents/{path_to_config}",
        "-H",
        "Accept: application/vnd.github.raw",
        "-f",
        f"ref={config_ref}",
    ]
    output = subprocess.check_output(args)
    return json.loads(output.decode("utf-8"))


def get_release_assets(*, tag: str, github_repository) -> Dict[str, Any]:
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

    parser.add_argument("--tag", required=True, help="tag identifying the release")
    parser.add_argument("--config", required=True, help="path to JSON config file")
    parser.add_argument(
        "--repo",
        help="github repo specified in `ORG/REPO` format",
        default=os.getenv("GITHUB_REPOSITORY"),
    )

    # It would make things slightly easier for the user to default to the
    # default branch of the repo, which might not be main.
    default_config_ref = "main"
    parser.add_argument(
        "--config-ref",
        help=f"SHA of Git commit to look up the config, defaults to {default_config_ref}",
        default=os.getenv("GITHUB_SHA", default_config_ref),
    )

    default_server = "https://github.com"
    parser.add_argument(
        "--server",
        help=f"URL for the GitHub server, defaults to {default_server}",
        default=os.getenv("GITHUB_SERVER_URL", default_server),
    )

    default_api_server = "https://api.github.com"
    parser.add_argument(
        "--api-server",
        help=f"URL for the GitHub API server, defaults to {default_api_server}",
        default=os.getenv("GITHUB_API_URL", default_api_server),
    )

    parser.add_argument(
        "--output",
        help=f"folder where DotSlash files should be written, defaults to $GITHUB_WORKSPACE",
        default=os.getenv("GITHUB_WORKSPACE"),
    )

    return parser.parse_args()


main()
