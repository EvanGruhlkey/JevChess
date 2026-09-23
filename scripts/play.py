"""Play Jev from a terminal using the same Python game core as the browser."""

import argparse

import chess

from jevchess.game import COLORS, Game, GameError
from jevchess.jev import choose_move
from jevchess.records import RecordStore


def parse_move(board, text):
    value = text.strip()
    try:
        move = chess.Move.from_uci(value.lower())
        if move in board.legal_moves:
            return move
    except ValueError:
        pass
    try:
        return board.parse_san(value)
    except ValueError as error:
        raise ValueError("Enter a legal move in SAN or UCI notation") from error


def main():
    parser = argparse.ArgumentParser(description="Play chess against Jev")
    parser.add_argument("--color", choices=("white", "black"), default="white")
    parser.add_argument("--seconds", type=int, default=600)
    args = parser.parse_args()
    game = Game(args.color, seconds=args.seconds)
    store = RecordStore()
    store.save(game)
    while game.status == "playing":
        print(f"\n{game.board}\n")
        if COLORS[game.board.turn] == game.human_color:
            try:
                move = parse_move(game.board, input("Your move: "))
                game.play(move.uci(), "human")
            except (ValueError, GameError) as error:
                print(error)
                continue
        else:
            print("Jev is thinking...")
            move, metadata = choose_move(game)
            game.play(move, "jev")
            game.jev_metadata.append(metadata)
            print(f"Jev plays {game.moves[-1]['san']}")
        store.save(game)
    store.finish(game)
    print(f"\n{game.board}\n{game.result} — {game.termination}")


if __name__ == "__main__":
    main()
