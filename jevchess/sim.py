"""Concurrent, reproducible Jev-vs-Jev chess matches."""

import json
import math
import random
import time

from .game import COLORS, Game
from .jev import ask, legal_probabilities
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


def choose_sampled_moves(games, randoms, ask_fn=ask):
    state = {str(seed): {"fen": game.board.fen(), "side_to_move": COLORS[game.board.turn]}
             for seed, game in games.items()}
    questions = {}
    legal_by_seed = {}
    for seed, game in games.items():
        legal = game.state()["legal_moves"]
        legal_by_seed[seed] = legal
        questions[f"game_{seed}"] = {
            "type": "choice",
            "instructions": f"Choose the strongest move for game {seed} using state.games.{seed}.",
            "criteria": {move: move for move in legal},
        }
    result = ask_fn({"state": {"games": state}, "questions": questions})
    usage = result.get("usage") or {}
    input_tokens = int(usage.get("inputTokens", 0))
    choices = {}
    try:
        answers = result["answers"]
        for seed in games:
            probabilities = legal_probabilities(answers[f"game_{seed}"], legal_by_seed[seed])
            move = sample_move(probabilities, legal_by_seed[seed], randoms[seed])
            choices[seed] = (move, {
                "input_tokens": round(input_tokens / len(games)),
                "probabilities": probabilities,
            })
    except (KeyError, TypeError) as error:
        raise ValueError("Jev did not answer every simulated game") from error
    return choices


def _saved_games(store, seeds):
    wanted = set(seeds)
    saved = {}
    for path in store.directory.glob("*.json"):
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
            seed = record["seed"]
        except (OSError, ValueError, KeyError):
            continue
        if seed in wanted and (
            seed not in saved or len(record.get("moves", [])) > len(saved[seed].get("moves", []))
        ):
            saved[seed] = record
    return saved


def _restore_game(record, rng):
    game = Game(
        None,
        seconds=1_000_000_000,
        fen=record["initial_fen"],
        players=record.get("players"),
    )
    game.id = record["id"]
    game.created_at = record["created_at"]
    game.seed = record["seed"]
    metadata = record.get("jev", [])
    if len(metadata) != len(record.get("moves", [])):
        raise ValueError(f"Saved game {game.id} is missing Jev move data")
    for item, details in zip(record["moves"], metadata):
        legal = [move.uci() for move in game.board.legal_moves]
        expected = sample_move(details.get("probabilities", {}), legal, rng)
        if expected != item["uci"]:
            raise ValueError(f"Saved game {game.id} cannot resume from its seed")
        color = COLORS[game.board.turn]
        game.play(item["uci"], f"jev-{color}")
        game.jev_metadata.append(details)
    if record.get("status") == "finished":
        game.result = record.get("result")
        game.termination = record.get("termination")
    return game


def run_matches(count=16, max_plies=80, store=None, chooser=choose_sampled_moves,
                seeds=None, progress=None, sleep=time.sleep, retry=None):
    store = store or RecordStore("results/jev-vs-jev-games")
    seeds = list(range(count)) if seeds is None else list(seeds)
    if len(seeds) != count:
        raise ValueError("Seed count must match game count")
    randoms = {seed: random.Random(seed) for seed in seeds}
    saved = _saved_games(store, seeds)
    games = {}
    for seed in seeds:
        if seed in saved:
            games[seed] = _restore_game(saved[seed], randoms[seed])
        else:
            games[seed] = Game(None, seconds=1_000_000_000)
            games[seed].seed = seed
    started = time.perf_counter()
    for seed, game in games.items():
        if seed not in saved:
            store.save(game)

    rows = []
    active = {}
    for seed, game in games.items():
        if game.status == "playing" and len(game.moves) < max_plies:
            active[seed] = game
            continue
        if game.status == "playing":
            game.result = "1/2-1/2"
            game.termination = f"{max_plies}-ply limit"
            store.finish(game)
        rows.append({
            "id": game.id,
            "seed": seed,
            "result": game.result,
            "termination": game.termination,
            "plies": len(game.moves),
        })

    failures = 0
    while active:
        try:
            choices = chooser(active, randoms)
        except (OSError, TimeoutError) as error:
            failures += 1
            delay = min(60, 2 ** (min(failures, 6) - 1))
            if retry:
                retry(failures, delay, error)
            sleep(delay)
            continue
        failures = 0
        if set(choices) != set(active):
            raise ValueError("Chooser must answer every active game")
        for seed, game in list(active.items()):
            move, metadata = choices[seed]
            color = COLORS[game.board.turn]
            game.play(move, f"jev-{color}")
            game.jev_metadata.append(metadata)
            store.save(game)
            if game.status == "playing" and len(game.moves) < max_plies:
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
            del active[seed]
            if progress:
                progress(len(rows), count, row, time.perf_counter() - started)
    return sorted(rows, key=lambda row: row["seed"])
