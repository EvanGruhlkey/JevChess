import json

import pytest

from jevchess.game import Game
from jevchess.web import create_app


def app_client(tmp_path, choose_fn=None, game_factory=Game):
    app = create_app(tmp_path, choose_fn=choose_fn, game_factory=game_factory)
    app.config.update(TESTING=True)
    return app.test_client()


def create_game(client, color="white"):
    response = client.post("/api/games", json={"color": color})
    assert response.status_code == 201
    return response.get_json()


def test_create_game_for_either_color_and_persist_it(tmp_path):
    client = app_client(tmp_path)

    white = create_game(client, "white")
    black = create_game(client, "black")

    assert white["turn"] == "white"
    assert black["turn"] == "white"
    assert black["human_color"] == "black"
    assert len(list(tmp_path.glob("*.json"))) == 2


def test_human_move_requires_current_ply_and_turn(tmp_path):
    client = app_client(tmp_path)
    game = create_game(client)

    moved = client.post(f"/api/games/{game['id']}/moves", json={"move": "e2e4", "ply": 0})
    stale = client.post(f"/api/games/{game['id']}/moves", json={"move": "d2d4", "ply": 0})

    assert moved.status_code == 200
    assert moved.get_json()["moves"][-1]["san"] == "e4"
    assert stale.status_code == 409
    assert stale.get_json()["error"] == "Game state changed; refresh and try again"


def test_jev_move_is_applied_once_and_saves_metadata(tmp_path):
    calls = []

    def choose(game):
        calls.append(game.board.fen())
        return "e7e5", {"input_tokens": 19}

    client = app_client(tmp_path, choose)
    game = create_game(client)
    client.post(f"/api/games/{game['id']}/moves", json={"move": "e2e4", "ply": 0})

    first = client.post(f"/api/games/{game['id']}/jev", json={"ply": 1})
    duplicate = client.post(f"/api/games/{game['id']}/jev", json={"ply": 1})

    assert first.status_code == 200
    assert first.get_json()["moves"][-1] == {"uci": "e7e5", "san": "e5"}
    assert duplicate.status_code == 409
    assert len(calls) == 1
    record = json.loads(next(tmp_path.glob("*.json")).read_text())
    assert record["jev"] == [{"input_tokens": 19}]


@pytest.mark.parametrize("failure", [OSError("gateway unavailable"), KeyError("AI_GATEWAY_API_KEY")])
def test_jev_failure_does_not_change_the_game(tmp_path, failure):
    def fail(game):
        raise failure

    client = app_client(tmp_path, fail)
    game = create_game(client)
    client.post(f"/api/games/{game['id']}/moves", json={"move": "e2e4", "ply": 0})

    response = client.post(f"/api/games/{game['id']}/jev", json={"ply": 1})
    state = client.get(f"/api/games/{game['id']}").get_json()

    assert response.status_code == 503
    assert response.get_json()["retryable"] is True
    assert len(state["moves"]) == 1


def test_resign_finishes_json_and_pgn_records(tmp_path):
    client = app_client(tmp_path)
    game = create_game(client)

    response = client.post(f"/api/games/{game['id']}/resign")

    assert response.get_json()["termination"] == "resignation"
    assert (tmp_path / f"{game['id']}.pgn").exists()


def test_replay_endpoint_returns_verified_frames(tmp_path):
    client = app_client(tmp_path)
    game = create_game(client)
    client.post(f"/api/games/{game['id']}/moves", json={"move": "e2e4", "ply": 0})

    response = client.get(f"/api/games/{game['id']}/replay")

    assert response.status_code == 200
    assert [frame["move"] for frame in response.get_json()] == [None, "e2e4"]


def test_browser_page_and_assets_are_served(tmp_path):
    client = app_client(tmp_path)

    page = client.get("/")
    css = client.get("/style.css")
    script = client.get("/app.js")

    assert page.status_code == 200
    assert b'id="board"' in page.data
    assert b'id="move-list"' in page.data
    assert b'Play as White' in page.data
    assert css.status_code == 200
    assert script.status_code == 200


def test_standard_piece_svg_is_served(tmp_path):
    client = app_client(tmp_path)

    piece = client.get("/pieces/wn.svg")
    unknown = client.get("/pieces/wx.svg")

    assert piece.status_code == 200
    assert piece.content_type.startswith("image/svg+xml")
    assert b"<svg" in piece.data
    assert unknown.status_code == 404


def test_state_request_finalizes_a_clock_expiry(tmp_path):
    now = [100.0]
    client = app_client(
        tmp_path,
        game_factory=lambda color: Game(color, seconds=1, now=lambda: now[0]),
    )
    game = create_game(client)
    now[0] += 2

    state = client.get(f"/api/games/{game['id']}").get_json()

    assert state["termination"] == "time forfeit"
    assert (tmp_path / f"{game['id']}.pgn").exists()
