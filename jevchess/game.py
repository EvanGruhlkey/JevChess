"""Authoritative chess state shared by the terminal and browser games."""

import time

import chess


COLORS = {chess.WHITE: "white", chess.BLACK: "black"}
COLOR_VALUES = {name: value for value, name in COLORS.items()}


class GameError(ValueError):
    """A move or game action cannot be applied to the current position."""


class Game:
    def __init__(self, human_color, seconds=600, fen=chess.STARTING_FEN, now=time.monotonic):
        if human_color not in COLOR_VALUES:
            raise GameError("Color must be white or black")
        self.board = chess.Board(fen)
        self.initial_fen = fen
        self.human_color = human_color
        self.jev_color = COLORS[not COLOR_VALUES[human_color]]
        self.moves = []
        self.clocks = {"white": float(seconds), "black": float(seconds)}
        self.time_control = int(seconds)
        self.result = None
        self.termination = None
        self._now = now
        self._turn_started = now()

    @property
    def status(self):
        return "finished" if self.result else "playing"

    def _actor_color(self, actor):
        if actor == "human":
            return self.human_color
        if actor == "jev":
            return self.jev_color
        raise GameError("Unknown player")

    def _settle_clock(self):
        if self.result:
            return
        color = COLORS[self.board.turn]
        current = self._now()
        self.clocks[color] = max(0.0, self.clocks[color] - (current - self._turn_started))
        self._turn_started = current
        if self.clocks[color] == 0:
            self.result = "0-1" if color == "white" else "1-0"
            self.termination = "time forfeit"

    def _finish_from_board(self):
        outcome = self.board.outcome(claim_draw=False)
        if outcome:
            self.result = outcome.result()
            self.termination = outcome.termination.name.lower().replace("_", " ")

    def play(self, move_uci, actor):
        self._settle_clock()
        if self.result:
            raise GameError("The game is finished")
        expected = COLORS[self.board.turn]
        if self._actor_color(actor) != expected:
            name = "Jev" if actor == "jev" else "the human"
            raise GameError(f"It is not {name}'s turn")
        try:
            move = chess.Move.from_uci(move_uci)
        except ValueError as error:
            raise GameError("Illegal move") from error
        if move not in self.board.legal_moves:
            raise GameError("Illegal move")
        san = self.board.san(move)
        self.board.push(move)
        self.moves.append({"uci": move.uci(), "san": san})
        self._finish_from_board()
        return self.state()

    def resign(self, actor):
        self._settle_clock()
        if self.result:
            raise GameError("The game is finished")
        color = self._actor_color(actor)
        self.result = "0-1" if color == "white" else "1-0"
        self.termination = "resignation"
        return self.state()

    def claim_draw(self, actor):
        self._settle_clock()
        if self.result:
            raise GameError("The game is finished")
        if self._actor_color(actor) != COLORS[self.board.turn]:
            raise GameError("It is not that player's turn")
        if not self.board.can_claim_draw():
            raise GameError("A draw cannot be claimed")
        self.result = "1/2-1/2"
        self.termination = "draw claimed"
        return self.state()

    def state(self):
        self._settle_clock()
        turn = COLORS[self.board.turn]
        return {
            "fen": self.board.fen(),
            "turn": turn,
            "human_color": self.human_color,
            "jev_color": self.jev_color,
            "legal_moves": [] if self.result else [move.uci() for move in self.board.legal_moves],
            "moves": list(self.moves),
            "last_move": self.moves[-1]["uci"] if self.moves else None,
            "clocks": {color: round(value, 3) for color, value in self.clocks.items()},
            "can_claim_draw": not self.result and self.board.can_claim_draw(),
            "in_check": not self.result and self.board.is_check(),
            "status": self.status,
            "result": self.result,
            "termination": self.termination,
        }
