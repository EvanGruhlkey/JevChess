import json

import chess
import pytest

from scripts.export_results import summarize
from scripts.play import parse_move


def test_parse_move_accepts_san_and_uci():
    board = chess.Board()

    assert parse_move(board, "e4").uci() == "e2e4"
    assert parse_move(board, "e2e4").uci() == "e2e4"


def test_parse_move_rejects_illegal_input():
    with pytest.raises(ValueError, match="legal move"):
        parse_move(chess.Board(), "e5")


def test_summarize_counts_only_finished_records(tmp_path):
    records = [
        {"status": "finished", "result": "1-0", "players": {"white": "Human", "black": "Jev"}},
        {"status": "finished", "result": "0-1", "players": {"white": "Human", "black": "Jev"}},
        {"status": "playing", "result": None, "players": {"white": "Human", "black": "Jev"}},
    ]
    for index, record in enumerate(records):
        (tmp_path / f"{index}.json").write_text(json.dumps(record))

    assert summarize(tmp_path) == {"games": 2, "human_wins": 1, "jev_wins": 1, "draws": 0}


def test_summarize_empty_directory_reports_no_results(tmp_path):
    assert summarize(tmp_path) == {"games": 0, "human_wins": 0, "jev_wins": 0, "draws": 0}

