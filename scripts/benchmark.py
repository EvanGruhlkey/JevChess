"""Play reproducible Jev matches against Elo-limited Stockfish."""

import argparse
import json
from pathlib import Path

import chess
import chess.engine

from jevchess.game import COLORS, Game
from jevchess.jev import choose_move
from jevchess.records import RecordStore


def play_game(engine, elo, jev_color, store, max_plies=160):
    bot_color = "black" if jev_color == "white" else "white"
    names = {jev_color: "Jev", bot_color: f"Stockfish {elo}"}
    game = Game(bot_color, seconds=3600, players=names)
    engine.configure({"UCI_LimitStrength": True, "UCI_Elo": elo})
    store.save(game)
    while game.status == "playing" and len(game.moves) < max_plies:
        color = COLORS[game.board.turn]
        if color == jev_color:
            move, metadata = choose_move(game)
            game.play(move, "jev")
            game.jev_metadata.append(metadata)
        else:
            move = engine.play(game.board, chess.engine.Limit(time=0.1)).move
            game.play(move.uci(), "human")
        store.save(game)
    if game.status == "playing":
        game.result, game.termination = "1/2-1/2", "160-ply limit"
    store.finish(game)
    return {"id": game.id, "elo": elo, "jev_color": jev_color, "result": game.result,
            "termination": game.termination, "plies": len(game.moves)}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("engine")
    parser.add_argument("--elos", default="1350,1700,2100,2500")
    parser.add_argument("--output", default="results/stockfish-benchmark.json")
    args = parser.parse_args()
    store = RecordStore()
    results = []
    engine = chess.engine.SimpleEngine.popen_uci(args.engine)
    try:
        for elo in map(int, args.elos.split(",")):
            for color in ("white", "black"):
                row = play_game(engine, elo, color, store)
                results.append(row)
                print(json.dumps(row), flush=True)
    finally:
        engine.quit()
    Path(args.output).write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
