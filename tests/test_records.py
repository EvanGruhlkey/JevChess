import json

import pytest

from jevchess.game import Game
from jevchess.records import RecordError, RecordStore, replay_record


def fools_mate(game):
    game.play("f2f3", "human")
    game.play("e7e5", "jev")
    game.play("g2g4", "human")
    game.play("d8h4", "jev")


def test_save_replaces_one_json_record_after_each_move(tmp_path):
    store = RecordStore(tmp_path)
    game = Game("white", now=lambda: 0.0)

    path = store.save(game)
    game.play("e2e4", "human")
    assert store.save(game) == path

    data = json.loads(path.read_text())
    assert data["id"] == game.id
    assert data["initial_fen"] == game.initial_fen
    assert data["moves"] == [{"uci": "e2e4", "san": "e4"}]
    assert data["clock_history"] == [{"white": 600.0, "black": 600.0}]
    assert data["final_fen"] == game.board.fen()
    assert list(tmp_path.glob("*.tmp")) == []


def test_finish_writes_standard_pgn(tmp_path):
    store = RecordStore(tmp_path)
    game = Game("white")
    fools_mate(game)

    json_path, pgn_path = store.finish(game)

    assert json_path.exists()
    pgn = pgn_path.read_text()
    assert f'[GameId "{game.id}"]' in pgn
    assert '[White "Human"]' in pgn
    assert '[Black "Jev"]' in pgn
    assert '[Result "0-1"]' in pgn
    assert "1. f3 e5 2. g4 Qh4# 0-1" in pgn


def test_replay_reconstructs_every_exact_position(tmp_path):
    store = RecordStore(tmp_path)
    game = Game("white")
    fools_mate(game)
    path, _ = store.finish(game)

    frames = replay_record(json.loads(path.read_text()))

    assert len(frames) == 5
    assert frames[0]["ply"] == 0
    assert frames[-1]["fen"] == game.board.fen()
    assert frames[-1]["result"] == "0-1"


def test_replay_rejects_changed_san(tmp_path):
    game = Game("white")
    game.play("e2e4", "human")
    data = RecordStore(tmp_path).data(game)
    data["moves"][0]["san"] = "e3"

    with pytest.raises(RecordError, match="SAN mismatch"):
        replay_record(data)
