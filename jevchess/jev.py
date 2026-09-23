"""Jev chooses one move from the legal moves supplied by the game."""

import json
import os
import random
import threading
import time
import urllib.error
import urllib.request

from dotenv import load_dotenv

from .game import COLORS, GameError


URL = "https://ai-gateway.vercel.sh/v1/evaluate"
PARALLEL_URL = "https://ai-gateway.vercel.sh/v4/ai/evaluation-model"


class RequestGate:
    def __init__(self, interval=0.12):
        self.interval = interval
        self._lock = threading.Lock()
        self._next = 0.0

    def wait(self):
        with self._lock:
            now = time.monotonic()
            delay = max(0.0, self._next - now)
            self._next = max(now, self._next) + self.interval
        if delay:
            time.sleep(delay)


PARALLEL_GATE = RequestGate()
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


def ask(body, key=None, attempts=12, url=URL, gate=None):
    load_dotenv()
    data = json.dumps({"model": "typesafe-ai/jev", **body} if url == URL else body).encode()
    headers = {
        "Authorization": f"Bearer {key or os.environ['AI_GATEWAY_API_KEY']}",
        "content-type": "application/json",
    }
    if url == PARALLEL_URL:
        headers.update({
            "ai-gateway-protocol-version": "0.0.1",
            "ai-evaluation-model-specification-version": "4",
            "ai-model-id": "typesafe-ai/jev",
        })
    for attempt in range(attempts):
        try:
            if gate:
                gate.wait()
            request = urllib.request.Request(url, data=data, headers=headers, method="POST")
            with urllib.request.urlopen(request, timeout=20) as response:
                return json.loads(response.read())
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError) as error:
            code = getattr(error, "code", None)
            transient = code is None or code == 429 or code >= 500
            if not transient or attempt == attempts - 1:
                raise
            time.sleep(min(4.0, 0.25 * 2**attempt) + random.random() * 0.2)
    raise RuntimeError("Jev request did not complete")


def ask_parallel(body, key=None, attempts=12, gate=PARALLEL_GATE):
    return ask(body, key=key, attempts=attempts, url=PARALLEL_URL, gate=gate)


def evaluate_moves(game, key=None, ask_fn=ask):
    legal = game.state()["legal_moves"]
    legal_set = set(legal)
    if not legal:
        raise GameError("Jev has no legal move")
    result = ask_fn(request_body(game), key=key)
    try:
        answer = result["answers"]["move"]
    except (KeyError, TypeError) as error:
        raise GameError("Jev did not return a legal move") from error
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
    usage = result.get("usage") or {}
    return probabilities, {"input_tokens": int(usage.get("inputTokens", 0))}


def choose_move(game, key=None, ask_fn=ask):
    probabilities, metadata = evaluate_moves(game, key=key, ask_fn=ask_fn)
    move = max(probabilities, key=probabilities.get)
    return move, metadata
