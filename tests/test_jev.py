import io
import json
import urllib.error

import pytest

from jevchess.game import Game, GameError
from jevchess.jev import ask, choose_move, request_body


def jev_turn():
    game = Game("white")
    game.play("e2e4", "human")
    return game


def test_request_contains_position_history_and_every_legal_move():
    game = jev_turn()

    body = request_body(game)

    question = body["questions"]["move"]
    assert body["state"] == {
        "fen": game.board.fen(),
        "side_to_move": "black",
        "move_history": ["e2e4"],
    }
    assert question["type"] == "choice"
    assert question["instructions"] == "Choose the strongest move."
    assert question["criteria"] == {move: move for move in game.state()["legal_moves"]}


def test_choice_response_returns_only_the_supplied_move():
    game = jev_turn()

    move, metadata = choose_move(
        game,
        ask_fn=lambda body, key=None: {
            "answers": {"move": {"choice": "e7e5"}},
            "usage": {"inputTokens": 42},
        },
    )

    assert move == "e7e5"
    assert metadata == {"input_tokens": 42}


def test_probability_response_uses_highest_legal_choice():
    game = jev_turn()

    move, _ = choose_move(
        game,
        ask_fn=lambda body, key=None: {
            "answers": {"move": {"probabilities": {"e7e5": 0.8, "c7c5": 0.2}}}
        },
    )

    assert move == "e7e5"


@pytest.mark.parametrize(
    "answer",
    [
        {},
        {"answers": {}},
        {"answers": {"move": {"choice": "e7e4"}}},
        {"answers": {"move": {"probabilities": {"e7e4": 1.0}}}},
    ],
)
def test_malformed_or_out_of_set_answer_is_rejected(answer):
    game = jev_turn()

    with pytest.raises(GameError, match="legal move"):
        choose_move(game, ask_fn=lambda body, key=None: answer)

    assert len(game.moves) == 1


def test_gateway_retries_transient_error(monkeypatch):
    attempts = []

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            return json.dumps({"answers": {"move": {"choice": "e7e5"}}}).encode()

    def open_request(request, timeout):
        attempts.append(request)
        if len(attempts) == 1:
            raise urllib.error.HTTPError(request.full_url, 503, "busy", {}, io.BytesIO())
        return Response()

    monkeypatch.setattr("urllib.request.urlopen", open_request)
    monkeypatch.setattr("time.sleep", lambda seconds: None)

    result = ask({"questions": {}}, key="secret", attempts=2)

    assert result["answers"]["move"]["choice"] == "e7e5"
    assert len(attempts) == 2
    assert attempts[0].headers["Authorization"] == "Bearer secret"
