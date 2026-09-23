"""Thin Flask API over the Python chess game."""

import threading
from pathlib import Path

import chess
import chess.svg
from flask import Flask, Response, jsonify, request, send_from_directory

from .game import COLORS, Game, GameError
from .jev import choose_move
from .records import RecordStore, replay_record


def create_app(records="results/games", choose_fn=None, game_factory=Game):
    static = Path(__file__).resolve().parents[1] / "web"
    app = Flask(__name__, static_folder=None)
    store = RecordStore(records)
    games = {}
    locks = {}
    chooser = choose_fn or choose_move

    def find(game_id):
        game = games.get(game_id)
        if not game:
            raise GameError("Game not found")
        return game

    def body():
        return request.get_json(silent=True) or {}

    def ensure_ply(game, value):
        if value != len(game.moves):
            raise GameError("Game state changed; refresh and try again")

    def save(game):
        if game.status == "finished":
            store.finish(game)
        else:
            store.save(game)

    @app.errorhandler(GameError)
    def game_error(error):
        status = 404 if str(error) == "Game not found" else 409
        return jsonify(error=str(error)), status

    @app.post("/api/games")
    def new_game():
        color = body().get("color", "white")
        try:
            game = game_factory(color)
        except GameError as error:
            return jsonify(error=str(error)), 400
        games[game.id] = game
        locks[game.id] = threading.Lock()
        store.save(game)
        return jsonify(game.state()), 201

    @app.get("/api/games/<game_id>")
    def game_state(game_id):
        game = find(game_id)
        state = game.state()
        if game.status == "finished":
            save(game)
        return jsonify(state)

    @app.post("/api/games/<game_id>/moves")
    def human_move(game_id):
        game = find(game_id)
        with locks[game_id]:
            data = body()
            ensure_ply(game, data.get("ply"))
            game.play(data.get("move", ""), "human")
            save(game)
            return jsonify(game.state())

    @app.post("/api/games/<game_id>/jev")
    def jev_move(game_id):
        game = find(game_id)
        with locks[game_id]:
            data = body()
            ensure_ply(game, data.get("ply"))
            if game.status != "playing" or COLORS[game.board.turn] != game.jev_color:
                raise GameError("It is not Jev's turn")
            try:
                move, metadata = chooser(game)
            except (GameError, KeyError, OSError, TimeoutError) as error:
                app.logger.warning("Jev move failed: %s", error)
                return jsonify(error="Jev could not choose a move", retryable=True), 503
            game.play(move, "jev")
            game.jev_metadata.append(metadata)
            save(game)
            return jsonify(game.state())

    @app.post("/api/games/<game_id>/resign")
    def resign(game_id):
        game = find(game_id)
        with locks[game_id]:
            game.resign("human")
            save(game)
            return jsonify(game.state())

    @app.post("/api/games/<game_id>/draw")
    def draw(game_id):
        game = find(game_id)
        with locks[game_id]:
            game.claim_draw("human")
            save(game)
            return jsonify(game.state())

    @app.get("/api/games/<game_id>/replay")
    def replay(game_id):
        return jsonify(replay_record(store.data(find(game_id))))

    @app.get("/pieces/<code>.svg")
    def piece(code):
        if len(code) != 2 or code[0] not in "wb" or code[1] not in "pnbrqk":
            return "", 404
        symbol = code[1].upper() if code[0] == "w" else code[1]
        svg = chess.svg.piece(chess.Piece.from_symbol(symbol), size=100)
        return Response(svg, mimetype="image/svg+xml")

    @app.get("/")
    def index():
        return send_from_directory(static, "index.html")

    @app.get("/<path:name>")
    def asset(name):
        return send_from_directory(static, name)

    return app
