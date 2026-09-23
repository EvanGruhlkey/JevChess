"""Render saved Jev-vs-Jev matches as an animated GIF."""

import argparse
import json
from pathlib import Path

from jevchess.render import render_gif


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--summary", default="results/jev-vs-jev.json")
    parser.add_argument("--records", default="results/jev-vs-jev-games")
    parser.add_argument("--output", default="media/jev-vs-jev.gif")
    parser.add_argument("--size", type=int, default=800)
    parser.add_argument("--frame-ms", type=int, default=90)
    args = parser.parse_args()
    summary = json.loads(Path(args.summary).read_text(encoding="utf-8"))
    directory = Path(args.records)
    records = [
        json.loads((directory / f"{row['id']}.json").read_text(encoding="utf-8"))
        for row in summary["games_detail"]
    ]
    output = render_gif(records, args.output, canvas_size=args.size, frame_ms=args.frame_ms)
    print(output)


if __name__ == "__main__":
    main()
