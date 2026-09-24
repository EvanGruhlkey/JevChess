import math
import random
import json

from jevchess.records import RecordStore, replay_record
from jevchess.game import Game
from jevchess.sim import choose_sampled_moves, run_matches, sample_move


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


def test_multiple_games_are_chosen_in_one_gateway_request():
    games = {10: Game(None), 11: Game(None)}
    randoms = {seed: random.Random(seed) for seed in games}
    requests = []

    def answer(body, key=None):
        requests.append(body)
        return {
            "answers": {
                name: {"choice": "e2e4"}
                for name in body["questions"]
            },
            "usage": {"inputTokens": 100},
        }

    choices = choose_sampled_moves(games, randoms, ask_fn=answer)

    assert len(requests) == 1
    assert set(requests[0]["state"]["games"]) == {"10", "11"}
    assert set(requests[0]["questions"]) == {"game_10", "game_11"}
    assert choices[10][0] == "e2e4"
    assert choices[11][0] == "e2e4"


def test_parallel_matches_save_exact_ply_limited_games(tmp_path):
    batches = []

    def choose(games, randoms):
        batches.append(tuple(games))
        return {
            seed: (randoms[seed].choice(list(game.board.legal_moves)).uci(), {"input_tokens": 1})
            for seed, game in games.items()
        }

    store = RecordStore(tmp_path)
    rows = run_matches(count=4, max_plies=2, store=store, chooser=choose, seeds=range(10, 14))

    assert batches == [(10, 11, 12, 13), (10, 11, 12, 13)]
    assert [row["seed"] for row in rows] == [10, 11, 12, 13]
    assert all(row["plies"] == 2 for row in rows)
    assert all(row["result"] == "1/2-1/2" for row in rows)
    assert all(row["termination"] == "2-ply limit" for row in rows)
    for row in rows:
        data = json.loads((tmp_path / f"{row['id']}.json").read_text())
        assert data["seed"] == row["seed"]
        assert data["time_control"] == 1_000_000_000
        assert replay_record(data)[-1]["result"] == "1/2-1/2"
        assert (tmp_path / f"{row['id']}.pgn").exists()


def test_matches_resume_seeded_games_from_saved_moves(tmp_path):
    store = RecordStore(tmp_path)
    game = Game(None, seconds=1_000_000_000)
    game.seed = 23
    probabilities = {move.uci(): 1.0 for move in game.board.legal_moves}
    rng = random.Random(23)
    move = sample_move(probabilities, [move.uci() for move in game.board.legal_moves], rng)
    game.play(move, "jev-white")
    game.jev_metadata.append({"input_tokens": 1, "probabilities": probabilities})
    store.save(game)

    def choose(games, randoms):
        return {
            seed: (sample_move({move.uci(): 1 for move in current.board.legal_moves},
                               [move.uci() for move in current.board.legal_moves], randoms[seed]),
                   {"input_tokens": 1, "probabilities": {move.uci(): 1 for move in current.board.legal_moves}})
            for seed, current in games.items()
        }

    rows = run_matches(count=1, max_plies=2, store=store, chooser=choose, seeds=[23])

    assert rows[0]["id"] == game.id
    assert rows[0]["plies"] == 2
    assert len(list(tmp_path.glob("*.json"))) == 1


def test_gateway_failures_retry_without_losing_the_round(tmp_path):
    calls = 0
    delays = []

    def choose(games, randoms):
        nonlocal calls
        calls += 1
        if calls < 3:
            raise OSError("gateway unavailable")
        return {
            seed: (next(iter(game.board.legal_moves)).uci(), {"input_tokens": 1})
            for seed, game in games.items()
        }

    rows = run_matches(
        count=1,
        max_plies=1,
        store=RecordStore(tmp_path),
        chooser=choose,
        seeds=[30],
        sleep=delays.append,
    )

    assert calls == 3
    assert delays == [1, 2]
    assert rows[0]["plies"] == 1
