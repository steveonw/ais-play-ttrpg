#!/usr/bin/env python3
"""Replay recorded role messages in a new directory. No model API calls."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from ttrpg import Campaign

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--output", required=True, help="A new campaign directory")
parser.add_argument("--input", default=str(ROOT / "examples/first-night.jsonl"))
args = parser.parse_args()
campaign = Campaign.create(args.output, json.loads((ROOT / "config/tavern-zero.json").read_text()))
for line in Path(args.input).read_text().splitlines():
    item = json.loads(line)
    campaign.submit(item["operation"], item["message"])
print(json.dumps(campaign.status(), indent=2))
