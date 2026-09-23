"""Summarize completed human-versus-Jev games without inventing results."""

import json
from pathlib import Path


def summarize(directory="results/games"):
    totals = {"games": 0, "human_wins": 0, "jev_wins": 0, "draws": 0}
    for path in Path(directory).glob("*.json"):
        record = json.loads(path.read_text(encoding="utf-8"))
        if record.get("status") != "finished":
            continue
        totals["games"] += 1
        result = record.get("result")
        if result == "1/2-1/2":
            totals["draws"] += 1
            continue
        winner = "white" if result == "1-0" else "black"
        name = record["players"][winner]
        totals["human_wins" if name == "Human" else "jev_wins"] += 1
    return totals


def main():
    totals = summarize()
    output = Path("results/summary.json")
    output.parent.mkdir(exist_ok=True)
    output.write_text(json.dumps(totals, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(totals, indent=2))


if __name__ == "__main__":
    main()
