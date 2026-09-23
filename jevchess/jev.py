"""Jev chooses one move from the legal moves supplied by the game."""

import json
import os
import random
import time
import urllib.error
import urllib.request

import chess

from .game import COLORS, GameError


URL = "https://ai-gateway.vercel.sh/v4/ai/evaluation-model"


def _history(game):
    board = chess.Board(game.initial_fen)
    moves = [chess.Move.from_uci(item["uci"]) for item in game.moves]
    return board.variation_san(moves) if moves else "No moves yet"


def request_body(game):
    criteria = {move.uci(): game.board.san(move) for move in game.board.legal_moves}
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
                "instructions": "Choose exactly one supplied legal move in UCI notation.",
                "criteria": criteria,
            }
        },
    }


def ask(body, key=None, attempts=4):
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
