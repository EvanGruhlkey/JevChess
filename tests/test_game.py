import chess
import pytest

from jevchess.game import Game, GameError


class Clock:
    def __init__(self):
        self.value = 100.0

    def __call__(self):
        return self.value

    def advance(self, seconds):
        self.value += seconds


def test_new_game_exposes_authoritative_position():
    game = Game("white")

    state = game.state()

    assert state["turn"] == "white"
    assert state["human_color"] == "white"
    assert state["fen"] == chess.STARTING_FEN
    assert len(state["legal_moves"]) == 20
    assert state["moves"] == []
    assert state["status"] == "playing"


def test_move_records_uci_and_san_and_changes_turn():
    game = Game("white")

    game.play("e2e4", "human")

    state = game.state()
    assert state["turn"] == "black"
    assert state["moves"] == [{"uci": "e2e4", "san": "e4"}]
    assert state["last_move"] == "e2e4"


@pytest.mark.parametrize(
    ("move", "actor", "message"),
    [("e2e5", "human", "Illegal move"), ("e7e5", "jev", "It is not Jev's turn")],
)
def test_move_rejects_illegal_or_out_of_turn_input(move, actor, message):
    game = Game("white")

    with pytest.raises(GameError, match=message):
        game.play(move, actor)

    assert game.state()["moves"] == []


def test_promotion_preserves_the_selected_piece():
    game = Game("white", fen="8/P7/8/8/8/8/7k/4K3 w - - 0 1")

    game.play("a7a8n", "human")

    assert game.board.piece_at(chess.A8) == chess.Piece(chess.KNIGHT, chess.WHITE)
    assert game.state()["moves"][0] == {"uci": "a7a8n", "san": "a8=N"}


def test_fools_mate_finishes_the_game():
    game = Game("white")
    game.play("f2f3", "human")
    game.play("e7e5", "jev")
    game.play("g2g4", "human")
    game.play("d8h4", "jev")

    state = game.state()
    assert state["status"] == "finished"
    assert state["result"] == "0-1"
    assert state["termination"] == "checkmate"


def test_resignation_awards_the_game_to_the_other_color():
    game = Game("black")

    game.resign("human")

    assert game.state()["result"] == "1-0"
    assert game.state()["termination"] == "resignation"


def test_claim_draw_requires_a_claimable_position():
    game = Game("white")

    with pytest.raises(GameError, match="cannot be claimed"):
        game.claim_draw("human")


def test_clock_moves_to_the_next_player_and_flags_expired_side():
    clock = Clock()
    game = Game("white", seconds=10, now=clock)
    clock.advance(3)
    game.play("e2e4", "human")

    state = game.state()
    assert state["clocks"] == {"white": 7.0, "black": 10.0}

    clock.advance(11)
    state = game.state()
    assert state["status"] == "finished"
    assert state["result"] == "1-0"
    assert state["termination"] == "time forfeit"

