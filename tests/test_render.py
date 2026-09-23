import json

from PIL import Image

from jevchess.game import Game
from jevchess.records import RecordStore
from jevchess.render import boards_at_ply, render_frame, render_gif


def records(tmp_path):
    store = RecordStore(tmp_path)
    short = Game(None)
    short.play("e2e4", "jev-white")
    short.result, short.termination = "1/2-1/2", "test"
    store.finish(short)
    long = Game(None)
    long.play("d2d4", "jev-white")
    long.play("d7d5", "jev-black")
    long.result, long.termination = "1/2-1/2", "test"
    store.finish(long)
    return [json.loads((tmp_path / f"{game.id}.json").read_text()) for game in (short, long)]


def test_boards_hold_short_games_on_their_final_position(tmp_path):
    saved = records(tmp_path)

    boards = boards_at_ply(saved, 2)

    assert boards[0].piece_at(28).symbol() == "P"  # e4
    assert boards[1].piece_at(35).symbol() == "p"  # d5


def test_render_frame_has_fixed_rgb_canvas(tmp_path):
    frame = render_frame(records(tmp_path), ply=1, canvas_size=400)

    assert frame.size == (400, 400)
    assert frame.mode == "RGB"


def test_render_gif_writes_every_shared_ply(tmp_path):
    output = tmp_path / "matches.gif"

    render_gif(records(tmp_path), output, canvas_size=400, frame_ms=40)

    with Image.open(output) as image:
        assert image.size == (400, 400)
        assert image.n_frames == 3
        assert image.info["duration"] == 40
