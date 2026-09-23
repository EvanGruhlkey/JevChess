"""Validate and summarize a saved Jev Chess game."""

import json
import sys
from pathlib import Path

from jevchess.records import replay_record


def main(path):
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    frames = replay_record(data)
    print(f"{data['id']}: {len(frames) - 1} plies, {data.get('result') or 'unfinished'}")


if __name__ == "__main__":
    main(sys.argv[1])
