"""Run reproducible Jev-vs-Jev games concurrently."""

import argparse
import json
import time
from pathlib import Path

from jevchess.records import RecordStore
from jevchess.sim import run_matches


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--games", type=int, default=16)
    parser.add_argument("--max-plies", type=int, default=80)
    parser.add_argument("--first-seed", type=int, default=1000)
    parser.add_argument("--records", default="results/jev-vs-jev-games")
    parser.add_argument("--output", default="results/jev-vs-jev.json")
    args = parser.parse_args()
    started = time.perf_counter()

    def report(done, total, row, elapsed):
        print(f"{done}/{total} seed {row['seed']}: {row['result']} in {row['plies']} plies ({elapsed:.1f}s)", flush=True)

    def report_retry(attempt, delay, error):
        print(f"Gateway unavailable ({error}); retrying in {delay}s", flush=True)

    rows = run_matches(
        count=args.games,
        max_plies=args.max_plies,
        store=RecordStore(args.records),
        seeds=range(args.first_seed, args.first_seed + args.games),
        progress=report,
        retry=report_retry,
    )
    summary = {
        "games": len(rows),
        "first_seed": args.first_seed,
        "max_plies": args.max_plies,
        "elapsed_seconds": round(time.perf_counter() - started, 3),
        "white_wins": sum(row["result"] == "1-0" for row in rows),
        "black_wins": sum(row["result"] == "0-1" for row in rows),
        "draws": sum(row["result"] == "1/2-1/2" for row in rows),
        "games_detail": rows,
    }
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
