"""Render exact saved chess matches as a synchronized animated grid."""

import math
from pathlib import Path

import chess
from PIL import Image, ImageDraw, ImageEnhance, ImageFont


LIGHT = "#f0d9b5"
DARK = "#b58863"
LAST = "#cdd26a"
BACKGROUND = "#262421"
INK = "#f0f0f0"
MUTED = "#aaa7a2"
PIECES = {
    "K": "♔", "Q": "♕", "R": "♖", "B": "♗", "N": "♘", "P": "♙",
    "k": "♚", "q": "♛", "r": "♜", "b": "♝", "n": "♞", "p": "♟",
}


def _font(size, bold=False):
    candidates = [
        Path("C:/Windows/Fonts/seguisym.ttf"),
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else
             "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
        Path("/System/Library/Fonts/Supplemental/Arial Unicode.ttf"),
    ]
    for path in candidates:
        if path.exists():
            return ImageFont.truetype(path, max(8, int(size)))
    return ImageFont.load_default(size=max(8, int(size)))


def boards_at_ply(records, ply):
    boards = []
    for record in records:
        board = chess.Board(record["initial_fen"])
        for item in record["moves"][:ply]:
            board.push_uci(item["uci"])
        boards.append(board)
    return boards


def _draw_board(record, board, ply, size):
    tile = Image.new("RGB", (size, size + 24), BACKGROUND)
    draw = ImageDraw.Draw(tile)
    square = size / 8
    last = record["moves"][ply - 1]["uci"] if 0 < ply <= len(record["moves"]) else None
    last_squares = {last[:2], last[2:4]} if last else set()
    piece_font = _font(square * 0.75)
    for rank_index, rank in enumerate(range(7, -1, -1)):
        for file_index in range(8):
            name = chess.square_name(chess.square(file_index, rank))
            color = LAST if name in last_squares else (LIGHT if (file_index + rank) % 2 else DARK)
            box = (
                round(file_index * square), round(rank_index * square),
                round((file_index + 1) * square), round((rank_index + 1) * square),
            )
            draw.rectangle(box, fill=color)
            piece = board.piece_at(chess.square(file_index, rank))
            if piece:
                glyph = PIECES[piece.symbol()]
                draw.text(
                    ((box[0] + box[2]) / 2, (box[1] + box[3]) / 2),
                    glyph,
                    font=piece_font,
                    fill="#f7f7f7" if piece.color else "#242424",
                    stroke_width=max(1, int(square / 32)),
                    stroke_fill="#353535" if piece.color else "#eeeeee",
                    anchor="mm",
                )
    complete = ply >= len(record["moves"]) and record.get("result")
    if complete:
        tile = ImageEnhance.Brightness(tile).enhance(0.68)
        draw = ImageDraw.Draw(tile)
    seed = record.get("seed")
    name = f"Seed {seed}" if seed is not None else record["id"][:8]
    result = record.get("result") if complete else f"Ply {min(ply, len(record['moves']))}"
    draw.text((4, size + 12), name, font=_font(10, bold=True), fill=INK, anchor="lm")
    draw.text((size - 4, size + 12), result or "Playing", font=_font(10), fill=MUTED, anchor="rm")
    return tile


def render_frame(records, ply, canvas_size=800):
    if not records:
        raise ValueError("At least one game record is required")
    columns = math.ceil(math.sqrt(len(records)))
    rows = math.ceil(len(records) / columns)
    gap = max(4, canvas_size // 160)
    cell_width = (canvas_size - gap * (columns + 1)) // columns
    cell_height = (canvas_size - gap * (rows + 1)) // rows
    board_size = min(cell_width, cell_height - 24)
    frame = Image.new("RGB", (canvas_size, canvas_size), BACKGROUND)
    boards = boards_at_ply(records, ply)
    for index, (record, board) in enumerate(zip(records, boards)):
        row, column = divmod(index, columns)
        tile = _draw_board(record, board, min(ply, len(record["moves"])), board_size)
        x = gap + column * (cell_width + gap) + (cell_width - board_size) // 2
        y = gap + row * (cell_height + gap) + (cell_height - board_size - 24) // 2
        frame.paste(tile, (x, y))
    return frame


def render_gif(records, output, canvas_size=800, frame_ms=90):
    maximum = max(len(record["moves"]) for record in records)
    frames = [
        render_frame(records, ply, canvas_size).convert("P", palette=Image.Palette.ADAPTIVE, colors=128)
        for ply in range(maximum + 1)
    ]
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    durations = [frame_ms] * len(frames)
    durations[-1] = max(1200, frame_ms)
    frames[0].save(
        output,
        save_all=True,
        append_images=frames[1:],
        duration=durations,
        loop=0,
        disposal=2,
        optimize=False,
    )
    return output
