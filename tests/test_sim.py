import math
import random
import threading
import time
import json

from jevchess.records import RecordStore, replay_record
from jevchess.sim import run_matches, sample_move


def test_sample_move_is_seeded_and_always_legal():
    probabilities = {"e2e4": 0.7, "d2d4": 0.2, "illegal": 100, "g1f3": math.nan}
    legal = ["e2e4", "d2d4", "g1f3"]

    first = [sample_move(probabilities, legal, random.Random(7)) for _ in range(4)]
    second = [sample_move(probabilities, legal, random.Random(7)) for _ in range(4)]

    assert first == second
    assert set(first) <= set(legal)


def test_sample_move_falls_back_to_a_seeded_legal_choice():
    legal = ["e2e4", "d2d4"]

    move = sample_move({}, legal, random.Random(3))

    assert move in legal


def test_parallel_matches_save_exact_ply_limited_games(tmp_path):
    active = 0
    peak = 0
    lock = threading.Lock()

    def choose(game, rng):
        nonlocal active, peak
        with lock:
            active += 1
            peak = max(peak, active)
        time.sleep(0.02)
        move = rng.choice(list(game.board.legal_moves)).uci()
        with lock:
            active -= 1
        return move, {"input_tokens": 1}

    store = RecordStore(tmp_path)
    rows = run_matches(count=4, workers=4, max_plies=2, store=store, chooser=choose, seeds=range(10, 14))

    assert peak > 1
    assert [row["seed"] for row in rows] == [10, 11, 12, 13]
    assert all(row["plies"] == 2 for row in rows)
    assert all(row["result"] == "1/2-1/2" for row in rows)
    assert all(row["termination"] == "2-ply limit" for row in rows)
    for row in rows:
        data = json.loads((tmp_path / f"{row['id']}.json").read_text())
        assert replay_record(data)[-1]["result"] == "1/2-1/2"
        assert (tmp_path / f"{row['id']}.pgn").exists()
