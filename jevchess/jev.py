"""Jev chooses one move from the legal moves supplied by the game."""

import json
import os
import random
import time
import urllib.error
import urllib.request

import chess
from dotenv import load_dotenv

from .game import COLORS, GameError


URL = "https://ai-gateway.vercel.sh/v4/ai/evaluation-model"
PIECE_NAMES = {
    chess.PAWN: "pawn",
    chess.KNIGHT: "knight",
    chess.BISHOP: "bishop",
    chess.ROOK: "rook",
    chess.QUEEN: "queen",
    chess.KING: "king",
}
PIECE_VALUES = {chess.PAWN: 1, chess.KNIGHT: 3, chess.BISHOP: 3, chess.ROOK: 5, chess.QUEEN: 9}


def _history(game):
    board = chess.Board(game.initial_fen)
    moves = [chess.Move.from_uci(item["uci"]) for item in game.moves]
    return board.variation_san(moves) if moves else "No moves yet"


def _captured_piece(board, move):
    if board.is_en_passant(move):
        return chess.Piece(chess.PAWN, not board.turn)
    return board.piece_at(move.to_square)


def describe_move(board, move):
    san = board.san(move)
    captured = _captured_piece(board, move)
    moved = board.piece_at(move.from_square)
    board.push(move)
    if captured:
        value = PIECE_VALUES[captured.piece_type]
        material = f"captures a {PIECE_NAMES[captured.piece_type]} (+{value})"
    else:
        material = "even"
    if move.promotion:
        gain = PIECE_VALUES[move.promotion] - 1
        material += f"; promotes to a {PIECE_NAMES[move.promotion]} (+{gain})"
    replies = []
    for reply in board.legal_moves:
        capture = board.is_capture(reply)
        check = board.gives_check(reply)
        if not capture and not check:
            continue
        text = board.san(reply)
        notes = []
        if capture and reply.to_square == move.to_square:
            notes.append(f"captures the moved {PIECE_NAMES[moved.piece_type]}")
        elif capture:
            victim = _captured_piece(board, reply)
            notes.append(f"captures a {PIECE_NAMES[victim.piece_type]}")
        if check:
            notes.append("gives check")
        replies.append(text + (" " + " and ".join(notes) if notes else ""))
    side = COLORS[board.turn].capitalize()
    check_text = " Gives check." if board.is_check() else ""
    reply_text = "; ".join(replies) if replies else "none"
    return (
        f"{san}. Resulting FEN: {board.fen()}. Material: {material}."
        f"{check_text} {side} has {board.legal_moves.count()} legal replies."
        f" Forcing replies: {reply_text}."
    )


def request_body(game):
    criteria = {move.uci(): describe_move(game.board.copy(), move) for move in game.board.legal_moves}
    return {
        "state": {
            "game": "Chess. Choose the strongest legal move for your side.",
            "fen": game.board.fen(),
            "side_to_move": COLORS[game.board.turn],
            "move_history": _history(game),
        },
        "questions": {
            "move": {
                "type": "choice",
                "instructions": (
                    "Choose exactly one supplied legal move in UCI notation. Look at the resulting position "
                    "and the opponent's forcing replies. Prefer moves that remain sound after the best reply; "
                    "avoid leaving the moved piece or king exposed for a short-term gain."
                ),
                "criteria": criteria,
            }
        },
    }


def ask(body, key=None, attempts=12):
    load_dotenv()
    data = json.dumps(body).encode()
    headers = {
        "Authorization": f"Bearer {key or os.environ['AI_GATEWAY_API_KEY']}",
        "content-type": "application/json",
        "ai-gateway-protocol-version": "0.0.1",
        "ai-evaluation-model-specification-version": "4",
        "ai-model-id": "typesafe-ai/jev",
    }
    for attempt in range(attempts):
        try:
            request = urllib.request.Request(URL, data=data, headers=headers, method="POST")
            with urllib.request.urlopen(request, timeout=20) as response:
                return json.loads(response.read())
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError) as error:
            code = getattr(error, "code", None)
            transient = code is None or code == 429 or code >= 500
            if not transient or attempt == attempts - 1:
                raise
            time.sleep(min(4.0, 0.25 * 2**attempt) + random.random() * 0.2)
    raise RuntimeError("Jev request did not complete")


def choose_move(game, key=None, ask_fn=ask):
    legal = set(game.state()["legal_moves"])
    if not legal:
        raise GameError("Jev has no legal move")
    result = ask_fn(request_body(game), key=key)
    try:
        answer = result["answers"]["move"]
    except (KeyError, TypeError) as error:
        raise GameError("Jev did not return a legal move") from error
    probabilities = answer.get("probabilities") or {}
    ranked = [(float(score), move) for move, score in probabilities.items() if move in legal]
    move = max(ranked)[1] if ranked else answer.get("choice")
    if move not in legal:
        raise GameError("Jev did not return a legal move")
    usage = result.get("usage") or {}
    return move, {"input_tokens": int(usage.get("inputTokens", 0))}
