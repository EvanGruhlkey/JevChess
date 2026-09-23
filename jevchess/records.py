"""Durable game records and exact replay validation."""

import json
from datetime import datetime
from pathlib import Path

import chess
import chess.pgn


class RecordError(ValueError):
    """A saved game cannot be replayed exactly."""


class RecordStore:
    def __init__(self, directory="results/games"):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)

    def data(self, game):
        return {
            "id": game.id,
            "created_at": game.created_at,
            "initial_fen": game.initial_fen,
            "time_control": game.time_control,
            "players": dict(game.players),
            "moves": list(game.moves),
            "clock_history": list(game.clock_history),
            "jev": list(game.jev_metadata),
            "final_fen": game.board.fen(),
            "status": game.status,
            "result": game.result,
            "termination": game.termination,
        }

    def save(self, game):
        path = self.directory / f"{game.id}.json"
        temporary = path.with_suffix(".tmp")
        temporary.write_text(json.dumps(self.data(game), indent=2) + "\n", encoding="utf-8")
        temporary.replace(path)
        return path

    def finish(self, game):
        json_path = self.save(game)
        pgn_path = self.directory / f"{game.id}.pgn"
        pgn_path.write_text(self._pgn(game), encoding="utf-8")
        return json_path, pgn_path

    def _pgn(self, game):
        record = chess.pgn.Game()
        record.headers["Event"] = "Human vs Jev"
        record.headers["Site"] = "Local"
        record.headers["Date"] = datetime.fromisoformat(game.created_at).strftime("%Y.%m.%d")
        record.headers["Round"] = "-"
        record.headers["White"] = game.players["white"]
        record.headers["Black"] = game.players["black"]
        record.headers["Result"] = game.result or "*"
        record.headers["GameId"] = game.id
        record.headers["TimeControl"] = str(game.time_control)
        if game.termination:
            record.headers["Termination"] = game.termination
        if game.initial_fen != chess.STARTING_FEN:
            record.headers["SetUp"] = "1"
            record.headers["FEN"] = game.initial_fen
        board = chess.Board(game.initial_fen)
        node = record
        for item in game.moves:
            move = chess.Move.from_uci(item["uci"])
            node = node.add_variation(move)
            board.push(move)
        return str(record) + "\n"


def replay_record(data):
    try:
        board = chess.Board(data["initial_fen"])
        moves = data["moves"]
    except (KeyError, ValueError, TypeError) as error:
        raise RecordError("Invalid game record") from error
    frames = [{"ply": 0, "fen": board.fen(), "move": None, "result": None}]
    for ply, item in enumerate(moves, 1):
        try:
            move = chess.Move.from_uci(item["uci"])
        except (KeyError, ValueError, TypeError) as error:
            raise RecordError(f"Invalid move at ply {ply}") from error
        if move not in board.legal_moves:
            raise RecordError(f"Illegal move at ply {ply}")
        san = board.san(move)
        if san != item.get("san"):
            raise RecordError(f"SAN mismatch at ply {ply}")
        board.push(move)
        frames.append({"ply": ply, "fen": board.fen(), "move": move.uci(), "result": None})
    if board.fen() != data.get("final_fen"):
        raise RecordError("Final position mismatch")
    result = data.get("result")
    outcome = board.outcome(claim_draw=False)
    if outcome and result != outcome.result():
        raise RecordError("Result mismatch")
    if result not in (None, "1-0", "0-1", "1/2-1/2"):
        raise RecordError("Invalid result")
    frames[-1]["result"] = result
    return frames
