#!/usr/bin/env python3

import argparse


def main():
    args = parse_args()
    print(f"branch: {args.branch}")
    print(f"config: {args.config}")


def parse_args():
    parser = argparse.ArgumentParser(description="A simple argparse example")

    parser.add_argument("--branch", help="branch (or tag?)")
    parser.add_argument("--config", help="path to JSON config file")

    return parser.parse_args()


main()
