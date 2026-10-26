from __future__ import annotations

import io
import re
from collections import Counter, defaultdict
from datetime import datetime, timezone
from typing import Any, Callable
from urllib.parse import unquote

import chess
import chess.pgn

from .engine import StockfishAnalyzer
from .models import GameAnalysis, MoveAnalysis, ReportData


CLOCK_RE = re.compile(r"\[%clk\s+(\d+):(\d+):(\d+(?:\.\d+)?)\]")
PIECE_NAMES = {
    chess.PAWN: "pawn",
    chess.KNIGHT: "knight",
    chess.BISHOP: "bishop",
    chess.ROOK: "rook",
    chess.QUEEN: "queen",
    chess.KING: "king",
}


def clock_seconds(comment: str) -> float | None:
    match = CLOCK_RE.search(comment or "")
    if not match:
        return None
    hours, minutes, seconds = match.groups()
    return int(hours) * 3600 + int(minutes) * 60 + float(seconds)


def parse_increment(time_control: str) -> int:
    if "+" not in time_control:
        return 0
    try:
        return int(time_control.split("+", 1)[1])
    except ValueError:
        return 0


def phase_for(board: chess.Board) -> str:
    if board.fullmove_number <= 10:
        return "opening"
    non_pawns = sum(
        len(board.pieces(piece, color))
        for piece in (chess.KNIGHT, chess.BISHOP, chess.ROOK, chess.QUEEN)
        for color in (chess.WHITE, chess.BLACK)
    )
    queens = len(board.pieces(chess.QUEEN, chess.WHITE)) + len(board.pieces(chess.QUEEN, chess.BLACK))
    if non_pawns <= 6 or queens == 0:
        return "endgame"
    return "middlegame"


def classify_loss(loss: int) -> str:
    if loss >= 250:
        return "blunder"
    if loss >= 120:
        return "mistake"
    if loss >= 60:
        return "inaccuracy"
    return "ok"


def practical_score(score: int) -> int:
    """Saturate already-winning/losing positions before measuring move loss.

    At club level, failing to convert mate-in-8 into mate-in-5 while retaining a
    winning advantage should not outrank hanging a queen in an equal position.
    """
    return max(-500, min(500, score))


def opening_family(name: str) -> str:
    normalized = (
        name.replace("Queens Pawn", "Queen's Pawn")
        .replace("Kings Pawn", "King's Pawn")
        .replace("Caro Kann", "Caro-Kann")
    )
    normalized = re.split(r"\s+\d+\.", normalized, maxsplit=1)[0]
    normalized = normalized.split(" Variation", 1)[0]
    words = normalized.split()
    for index, word in enumerate(words):
        if word.rstrip(":") in {"Defense", "Opening", "Game", "Attack", "Gambit"}:
            return " ".join(words[: index + 1]).rstrip(":")
    return " ".join(words[:4]) or "Unknown opening"


def opening_name(game: dict[str, Any], parsed: chess.pgn.Game) -> str:
    for header in ("Opening", "ECOUrl"):
        value = parsed.headers.get(header)
        if value:
            if value.startswith("http"):
                value = value.rstrip("/").split("/")[-1]
            return unquote(value).replace("-", " ")
    eco_url = game.get("eco", "")
    if eco_url:
        return unquote(eco_url.rstrip("/").split("/")[-1]).replace("-", " ")
    return "Unknown opening"


def san_line(board: chess.Board, moves_uci: list[str]) -> list[str]:
    line: list[str] = []
    copy = board.copy()
    for uci in moves_uci:
        try:
            move = chess.Move.from_uci(uci)
            line.append(copy.san(move))
            copy.push(move)
        except (ValueError, AssertionError):
            break
    return line


def move_motifs(
    board_before: chess.Board,
    played: chess.Move,
    best: chess.Move | None,
    best_reply: chess.Move | None,
    loss: int,
    board_after: chess.Board,
) -> list[str]:
    motifs: list[str] = []
    if loss < 60:
        return motifs

    if best and board_before.is_capture(best) and not board_before.is_capture(played):
        captured = board_before.piece_at(best.to_square)
        motifs.append(f"missed {PIECE_NAMES.get(captured.piece_type, 'piece')} capture" if captured else "missed capture")
    if best:
        test = board_before.copy()
        test.push(best)
        if test.is_check() and not board_after.is_check():
            motifs.append("missed check")

    if loss >= 250:
        motifs.append("major evaluation swing")
    elif loss >= 120:
        motifs.append("tactical or positional mistake")

    if best_reply and board_after.is_capture(best_reply):
        victim = board_after.piece_at(best_reply.to_square)
        if victim and victim.color != board_after.turn:
            value = {chess.PAWN: 1, chess.KNIGHT: 3, chess.BISHOP: 3, chess.ROOK: 5, chess.QUEEN: 9}.get(victim.piece_type, 0)
            if value >= 3:
                motifs.append(f"left {PIECE_NAMES[victim.piece_type]} en prise")
    return list(dict.fromkeys(motifs))


def result_for(game: dict[str, Any], username: str) -> tuple[str, str, str, dict[str, Any], dict[str, Any]]:
    white = game.get("white", {})
    black = game.get("black", {})
    user_is_white = white.get("username", "").lower() == username.lower()
    user = white if user_is_white else black
    opponent = black if user_is_white else white
    detail = user.get("result", "unknown")
    if detail == "win":
        outcome = "win"
    elif detail in {"agreed", "repetition", "stalemate", "insufficient", "50move", "timevsinsufficient"}:
        outcome = "draw"
    else:
        outcome = "loss"
    return outcome, detail, "white" if user_is_white else "black", user, opponent


def analyze_game(
    raw: dict[str, Any],
    username: str,
    engine: StockfishAnalyzer,
    progress: Callable[[str], None],
) -> GameAnalysis:
    parsed = chess.pgn.read_game(io.StringIO(raw.get("pgn", "")))
    if parsed is None:
        raise ValueError(f"Could not parse PGN for {raw.get('url', raw.get('uuid', 'unknown game'))}")

    outcome, detail, user_color_name, user, opponent = result_for(raw, username)
    user_color = chess.WHITE if user_color_name == "white" else chess.BLACK
    increment = parse_increment(raw.get("time_control", ""))
    previous_clock: dict[chess.Color, float | None] = {chess.WHITE: None, chess.BLACK: None}
    board = parsed.board()
    evaluation = engine.evaluate(board)
    analyses: list[MoveAnalysis] = []

    total_plies = sum(1 for _ in parsed.mainline_moves())
    for ply, node in enumerate(parsed.mainline(), start=1):
        move = node.move
        mover = board.turn
        before = board.copy()
        san = before.san(move)
        before_eval = evaluation
        board.push(move)
        evaluation = engine.evaluate(board)

        current_clock = clock_seconds(node.comment)
        spent = None
        if current_clock is not None:
            prior = previous_clock[mover]
            if prior is not None:
                spent = max(0.0, prior + increment - current_clock)
            previous_clock[mover] = current_clock

        if mover != user_color:
            continue

        sign = 1 if user_color == chess.WHITE else -1
        score_before = sign * int(before_eval["score_white_cp"])
        score_after = sign * int(evaluation["score_white_cp"])
        loss = max(0, practical_score(score_before) - practical_score(score_after))
        best_uci = before_eval.get("best_move_uci", "")
        best = chess.Move.from_uci(best_uci) if best_uci else None
        try:
            best_san = before.san(best) if best else ""
        except (ValueError, AssertionError):
            best_san = best_uci

        reply_uci = evaluation.get("best_move_uci", "")
        reply = chess.Move.from_uci(reply_uci) if reply_uci else None
        analyses.append(
            MoveAnalysis(
                ply=ply,
                move_number=before.fullmove_number,
                color=user_color_name,
                san=san,
                uci=move.uci(),
                fen_before=before.fen(),
                fen_after=board.fen(),
                best_move_uci=best_uci,
                best_move_san=best_san,
                eval_before_cp=score_before,
                eval_after_cp=score_after,
                centipawn_loss=loss,
                classification=classify_loss(loss),
                phase=phase_for(before),
                clock_seconds=current_clock,
                seconds_spent=spent,
                motifs=move_motifs(before, move, best, reply, loss, board),
                pv_san=san_line(before, before_eval.get("pv_uci", [])),
            )
        )
        if ply % 20 == 0:
            progress(f"    analyzed ply {ply}/{total_plies}")

    accuracy = raw.get("accuracies", {}).get(user_color_name)
    date = datetime.fromtimestamp(raw.get("end_time", 0), tz=timezone.utc).date().isoformat()
    return GameAnalysis(
        uuid=raw.get("uuid", ""),
        url=raw.get("url", ""),
        end_time=raw.get("end_time", 0),
        date=date,
        user_color=user_color_name,
        opponent=opponent.get("username", "Unknown"),
        user_rating=user.get("rating"),
        opponent_rating=opponent.get("rating"),
        result=outcome,
        result_detail=detail,
        opening=opening_name(raw, parsed),
        eco_url=raw.get("eco", ""),
        time_control=raw.get("time_control", ""),
        chess_com_accuracy=accuracy,
        moves=analyses,
    )


def build_summary(games: list[GameAnalysis]) -> dict[str, Any]:
    all_moves = [move for game in games for move in game.moves]
    serious = [move for move in all_moves if move.classification in {"mistake", "blunder"}]
    phases = Counter(move.phase for move in serious)
    generic_motifs = {"major evaluation swing", "tactical or positional mistake"}
    motifs = Counter(
        motif for move in serious for motif in move.motifs if motif not in generic_motifs
    )
    classifications = Counter(move.classification for move in all_moves)
    results = Counter(game.result for game in games)

    by_color: dict[str, Counter[str]] = defaultdict(Counter)
    by_opening: dict[str, Counter[str]] = defaultdict(Counter)
    for game in games:
        by_color[game.user_color][game.result] += 1
        by_opening[opening_family(game.opening)][game.result] += 1

    timed = [move for move in serious if move.seconds_spent is not None]
    fast_serious = [move for move in timed if move.seconds_spent is not None and move.seconds_spent <= 5]
    low_clock_serious = [move for move in serious if move.clock_seconds is not None and move.clock_seconds <= 60]
    avg_cpl = round(sum(move.centipawn_loss for move in all_moves) / len(all_moves), 1) if all_moves else 0

    phase_total = Counter(move.phase for move in all_moves)
    phase_rates = {
        phase: round(phases.get(phase, 0) / total * 100, 1)
        for phase, total in phase_total.items()
        if total
    }

    candidates = sorted(
        ((move, game) for game in games for move in game.moves if move in serious),
        key=lambda pair: pair[0].centipawn_loss,
        reverse=True,
    )
    critical_items: list[dict[str, Any]] = []
    selected_by_game: Counter[str] = Counter()
    selected_moves: dict[str, list[int]] = defaultdict(list)
    for move, game in candidates:
        if selected_by_game[game.uuid] >= 2:
            continue
        if any(abs(move.move_number - prior) <= 2 for prior in selected_moves[game.uuid]):
            continue
        critical_items.append({
            "date": game.date,
            "url": game.url,
            "opponent": game.opponent,
            **move.__dict__,
        })
        selected_by_game[game.uuid] += 1
        selected_moves[game.uuid].append(move.move_number)
        if len(critical_items) == 10:
            break

    return {
        "record": dict(results),
        "games_analyzed": len(games),
        "moves_analyzed": len(all_moves),
        "average_centipawn_loss": avg_cpl,
        "classifications": dict(classifications),
        "serious_mistakes": len(serious),
        "serious_by_phase": dict(phases),
        "serious_rate_by_phase_percent": phase_rates,
        "motifs": dict(motifs.most_common()),
        "fast_serious_mistakes": len(fast_serious),
        "low_clock_serious_mistakes": len(low_clock_serious),
        "by_color": {color: dict(record) for color, record in by_color.items()},
        "by_opening": {opening: dict(record) for opening, record in by_opening.items()},
        "critical_moves": critical_items,
    }


def analyze_games(
    raw_games: list[dict[str, Any]],
    username: str,
    engine: StockfishAnalyzer,
    progress: Callable[[str], None] = print,
) -> ReportData:
    games: list[GameAnalysis] = []
    for index, raw in enumerate(raw_games, start=1):
        opponent = raw.get("black", {}).get("username") if raw.get("white", {}).get("username", "").lower() == username.lower() else raw.get("white", {}).get("username")
        progress(f"[{index}/{len(raw_games)}] Analyzing vs {opponent}...")
        games.append(analyze_game(raw, username, engine, progress))

    return ReportData(
        username=username,
        generated_at=datetime.now(timezone.utc).isoformat(),
        engine=engine.engine_name,
        analysis_limit=f"{engine.nodes:,} nodes per position",
        requested_games=len(raw_games),
        games=games,
        summary=build_summary(games),
    )
