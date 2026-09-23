"""Jev chooses one move from the legal moves supplied by the game."""

import json
import os
import random
import time
import urllib.error
import urllib.request

from dotenv import load_dotenv

from .game import COLORS, GameError


URL = "https://ai-gateway.vercel.sh/v1/evaluate"
def request_body(game):
    legal_moves = [move.uci() for move in game.board.legal_moves]
    return {
        "state": {
            "fen": game.board.fen(),
            "side_to_move": COLORS[game.board.turn],
        },
        "questions": {
            "move": {
                "type": "choice",
                "instructions": "Choose the strongest move.",
                "criteria": {move: move for move in legal_moves},
            }
        },
    }


def ask(body, key=None, attempts=12):
    load_dotenv()
    data = json.dumps({"model": "typesafe-ai/jev", **body}).encode()
    headers = {
        "Authorization": f"Bearer {key or os.environ['AI_GATEWAY_API_KEY']}",
        "content-type": "application/json",
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


def legal_probabilities(answer, legal):
    legal_set = set(legal)
    probabilities = {}
    for move, score in (answer.get("probabilities") or {}).items():
        if move not in legal_set:
            continue
        try:
            probabilities[move] = float(score)
        except (TypeError, ValueError):
            continue
    choice = answer.get("choice")
    if not probabilities and choice in legal_set:
        probabilities[choice] = 1.0
    if not probabilities:
        raise GameError("Jev did not return a legal move")
    return probabilities


def evaluate_moves(game, key=None, ask_fn=ask):
    legal = game.state()["legal_moves"]
    if not legal:
        raise GameError("Jev has no legal move")
    result = ask_fn(request_body(game), key=key)
    try:
        answer = result["answers"]["move"]
    except (KeyError, TypeError) as error:
        raise GameError("Jev did not return a legal move") from error
    probabilities = legal_probabilities(answer, legal)
    usage = result.get("usage") or {}
    return probabilities, {"input_tokens": int(usage.get("inputTokens", 0))}


def choose_move(game, key=None, ask_fn=ask):
    probabilities, metadata = evaluate_moves(game, key=key, ask_fn=ask_fn)
    move = max(probabilities, key=probabilities.get)
    return move, metadata
