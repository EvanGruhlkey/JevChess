"""Concurrent, reproducible Jev-vs-Jev chess matches."""

import math
import random
import time
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait

from .game import COLORS, Game
from .jev import ask_parallel, evaluate_moves
from .records import RecordStore


def sample_move(probabilities, legal_moves, rng):
    legal = list(legal_moves)
    weighted = []
    for move in legal:
        try:
            weight = float(probabilities.get(move, 0))
        except (TypeError, ValueError):
            continue
        if math.isfinite(weight) and weight > 0:
            weighted.append((move, weight))
    if not weighted:
        return rng.choice(legal)
    target = rng.random() * sum(weight for _, weight in weighted)
    for move, weight in weighted:
        target -= weight
        if target <= 0:
            return move
    return weighted[-1][0]


def choose_sampled_move(game, rng):
    probabilities, metadata = evaluate_moves(game, ask_fn=ask_parallel)
    move = sample_move(probabilities, game.state()["legal_moves"], rng)
    metadata = {**metadata, "probabilities": probabilities}
    return move, metadata


def run_matches(count=16, workers=6, max_plies=160, store=None, chooser=choose_sampled_move,
                seeds=None, progress=None):
    store = store or RecordStore("results/jev-vs-jev-games")
    seeds = list(range(count)) if seeds is None else list(seeds)
    if len(seeds) != count:
        raise ValueError("Seed count must match game count")
    games = {seed: Game(None, seconds=3600) for seed in seeds}
    randoms = {seed: random.Random(seed) for seed in seeds}
    started = time.perf_counter()
    for game in games.values():
        store.save(game)

    rows = []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        pending = {pool.submit(chooser, games[seed], randoms[seed]): seed for seed in seeds}
        while pending:
            done, _ = wait(pending, return_when=FIRST_COMPLETED)
            for future in done:
                seed = pending.pop(future)
                game = games[seed]
                move, metadata = future.result()
                color = COLORS[game.board.turn]
                game.play(move, f"jev-{color}")
                game.jev_metadata.append(metadata)
                store.save(game)
                if game.status == "playing" and len(game.moves) < max_plies:
                    pending[pool.submit(chooser, game, randoms[seed])] = seed
                    continue
                if game.status == "playing":
                    game.result = "1/2-1/2"
                    game.termination = f"{max_plies}-ply limit"
                store.finish(game)
                row = {
                    "id": game.id,
                    "seed": seed,
                    "result": game.result,
                    "termination": game.termination,
                    "plies": len(game.moves),
                }
                rows.append(row)
                if progress:
                    progress(len(rows), count, row, time.perf_counter() - started)
    return sorted(rows, key=lambda row: row["seed"])
