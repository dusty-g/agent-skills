from __future__ import annotations

import csv
import html
import json
from pathlib import Path
from typing import Any

import chess
import chess.pgn
import chess.svg

from .models import GameAnalysis, MoveAnalysis, ReportData


def _pct_record(record: dict[str, int]) -> str:
    return f"{record.get('win', 0)}–{record.get('loss', 0)}–{record.get('draw', 0)}"


def _primary_findings(data: ReportData) -> list[str]:
    summary = data.summary
    findings: list[str] = []
    rates = summary.get("serious_rate_by_phase_percent", {})
    if rates:
        worst_phase = max(rates, key=rates.get)
        findings.append(
            f"Your highest mistake rate was in the {worst_phase}: {rates[worst_phase]:.1f}% of your moves there were mistakes or blunders."
        )
    motifs = summary.get("motifs", {})
    if motifs:
        motif, count = next(iter(motifs.items()))
        findings.append(f"Most repeated detectable motif: {motif} ({count} times).")
    serious = summary.get("serious_mistakes", 0)
    games = max(1, summary.get("games_analyzed", 1))
    findings.append(f"You averaged {serious / games:.1f} mistakes or blunders per game.")
    fast = summary.get("fast_serious_mistakes", 0)
    if fast:
        findings.append(f"At least {fast} serious mistakes came after using five seconds or less.")
    low_clock = summary.get("low_clock_serious_mistakes", 0)
    if low_clock:
        findings.append(f"{low_clock} serious mistakes occurred with one minute or less remaining.")
    opening_rows = []
    for opening, record in summary.get("by_opening", {}).items():
        total = sum(record.values())
        if total >= 3:
            score = record.get("win", 0) + 0.5 * record.get("draw", 0)
            opening_rows.append((score / total, total, opening, record))
    if opening_rows:
        rate, total, opening, record = min(opening_rows)
        if rate < 0.5:
            findings.append(
                f"Your weakest repeated opening result was the {opening}: {_pct_record(record)} across {total} games."
            )
    colors = summary.get("by_color", {})
    if len(colors) == 2:
        def color_score(record: dict[str, int]) -> float:
            total = max(1, sum(record.values()))
            return (record.get("win", 0) + 0.5 * record.get("draw", 0)) / total
        weaker = min(colors, key=lambda color: color_score(colors[color]))
        stronger = max(colors, key=lambda color: color_score(colors[color]))
        if color_score(colors[stronger]) - color_score(colors[weaker]) >= 0.2:
            findings.append(
                f"The recent color split is notable: {_pct_record(colors[stronger])} as {stronger}, versus {_pct_record(colors[weaker])} as {weaker}."
            )
    return findings


def _practice_plan(data: ReportData) -> list[str]:
    summary = data.summary
    motifs = summary.get("motifs", {})
    plan = [
        "Before every move, scan checks, captures, and attacks—for both players.",
        "For each critical position below, choose a move before revealing Stockfish’s answer.",
    ]
    if any("en prise" in motif for motif in motifs):
        plan.insert(0, "Do a final loose-piece scan before releasing every move: queen, rooks, then minor pieces.")
    if summary.get("fast_serious_mistakes", 0) >= 2:
        plan.append("When the position is tactical and you have time, force yourself to spend at least 10 seconds.")
    rates = summary.get("serious_rate_by_phase_percent", {})
    if rates and max(rates, key=rates.get) == "opening":
        plan.append("Review only the first major deviation in each opening; do not memorize long theory yet.")
    elif rates and max(rates, key=rates.get) == "endgame":
        plan.append("Spend one practice session on basic king-and-pawn and rook endgames.")
    return plan[:5]


def write_json(data: ReportData, path: Path) -> None:
    path.write_text(json.dumps(data.to_dict(), indent=2), encoding="utf-8")


def write_csv(data: ReportData, path: Path) -> None:
    fields = [
        "date", "opponent", "result", "color", "opening", "game_url", "move_number",
        "move", "best_move", "centipawn_loss", "classification", "phase", "seconds_spent",
        "clock_seconds", "motifs", "fen_before",
    ]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for game in data.games:
            for move in game.moves:
                writer.writerow({
                    "date": game.date,
                    "opponent": game.opponent,
                    "result": game.result,
                    "color": game.user_color,
                    "opening": game.opening,
                    "game_url": game.url,
                    "move_number": move.move_number,
                    "move": move.san,
                    "best_move": move.best_move_san,
                    "centipawn_loss": move.centipawn_loss,
                    "classification": move.classification,
                    "phase": move.phase,
                    "seconds_spent": move.seconds_spent,
                    "clock_seconds": move.clock_seconds,
                    "motifs": "; ".join(move.motifs),
                    "fen_before": move.fen_before,
                })


def write_critical_pgn(data: ReportData, path: Path) -> None:
    blocks: list[str] = []
    for index, item in enumerate(data.summary.get("critical_moves", [])[:10], start=1):
        board = chess.Board(item["fen_before"])
        game = chess.pgn.Game()
        game.setup(board)
        game.headers["Event"] = f"Critical Position {index}"
        game.headers["White"] = data.username if item["color"] == "white" else item["opponent"]
        game.headers["Black"] = data.username if item["color"] == "black" else item["opponent"]
        game.headers["Date"] = item["date"].replace("-", ".")
        game.headers["Site"] = item["url"]
        game.headers["Annotator"] = data.engine
        move = chess.Move.from_uci(item["best_move_uci"])
        if move in board.legal_moves:
            node = game.add_variation(move)
            node.comment = f"Best move. Played {item['san']} ({item['centipawn_loss']} cp loss)."
        blocks.append(str(game))
    path.write_text("\n\n".join(blocks) + "\n", encoding="utf-8")


def write_markdown(data: ReportData, path: Path) -> None:
    s = data.summary
    lines = [
        f"# Rapid review: {data.username}", "",
        f"Analyzed {s['games_analyzed']} games and {s['moves_analyzed']} player moves with {data.engine} ({data.analysis_limit}).",
        "", "## Snapshot", "",
        f"- Record: {_pct_record(s['record'])} (wins–losses–draws)",
        f"- Average centipawn loss: {s['average_centipawn_loss']}",
        f"- Inaccuracies: {s['classifications'].get('inaccuracy', 0)}",
        f"- Mistakes: {s['classifications'].get('mistake', 0)}",
        f"- Blunders: {s['classifications'].get('blunder', 0)}",
        "", "## Main findings", "",
    ]
    lines.extend(f"- {finding}" for finding in _primary_findings(data))
    lines.extend(["", "## Practice plan", ""])
    lines.extend(f"{i}. {item}" for i, item in enumerate(_practice_plan(data), start=1))
    lines.extend(["", "## Critical positions", ""])
    for index, item in enumerate(s.get("critical_moves", [])[:10], start=1):
        line = " ".join(item.get("pv_san", []))
        lines.extend([
            f"### {index}. vs {item['opponent']}, move {item['move_number']}", "",
            f"You played **{item['san']}**; Stockfish preferred **{item['best_move_san']}**. Loss: {item['centipawn_loss']} cp.",
            f"Suggested line: `{line}`" if line else "",
            f"[Open game]({item['url']}) · FEN: `{item['fen_before']}`", "",
        ])
    path.write_text("\n".join(lines), encoding="utf-8")


def _board_svg(item: dict[str, Any]) -> str:
    board = chess.Board(item["fen_before"])
    orientation = chess.WHITE if item["color"] == "white" else chess.BLACK
    arrows = []
    if item.get("best_move_uci"):
        move = chess.Move.from_uci(item["best_move_uci"])
        arrows.append(chess.svg.Arrow(move.from_square, move.to_square, color="#22c55e"))
    return chess.svg.board(board, orientation=orientation, arrows=arrows, size=360)


def write_html(data: ReportData, path: Path) -> None:
    s = data.summary
    findings = "".join(f"<li>{html.escape(x)}</li>" for x in _primary_findings(data))
    plan = "".join(f"<li>{html.escape(x)}</li>" for x in _practice_plan(data))
    cards = []
    for index, item in enumerate(s.get("critical_moves", [])[:10], start=1):
        motifs = ", ".join(item.get("motifs", [])) or "evaluation swing"
        pv = " ".join(item.get("pv_san", []))
        cards.append(f"""
        <article class="position">
          <div class="board">{_board_svg(item)}</div>
          <div class="position-copy">
            <div class="eyebrow">#{index} · {html.escape(item['date'])} · {html.escape(item['phase'])}</div>
            <h3>Move {item['move_number']} vs {html.escape(item['opponent'])}</h3>
            <p>You played <strong>{html.escape(item['san'])}</strong>. The engine preferred
            <strong>{html.escape(item['best_move_san'])}</strong>.</p>
            <div class="loss">−{item['centipawn_loss']} cp</div>
            <p class="muted">{html.escape(motifs)}</p>
            <p><code>{html.escape(pv)}</code></p>
            <a href="{html.escape(item['url'])}">Open the full game ↗</a>
          </div>
        </article>""")

    game_rows = "".join(
        f"<tr><td>{html.escape(g.date)}</td><td><a href='{html.escape(g.url)}'>{html.escape(g.opponent)}</a></td>"
        f"<td><span class='result {g.result}'>{g.result}</span></td><td>{g.user_color}</td>"
        f"<td>{html.escape(g.opening)}</td><td>{sum(m.classification == 'blunder' for m in g.moves)}</td>"
        f"<td>{sum(m.classification == 'mistake' for m in g.moves)}</td></tr>"
        for g in data.games
    )

    document = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Rapid review · {html.escape(data.username)}</title>
<style>
:root {{--bg:#0b1020;--panel:#151c30;--ink:#eef2ff;--muted:#9ba8c7;--blue:#60a5fa;--green:#34d399;--red:#fb7185;--amber:#fbbf24;}}
*{{box-sizing:border-box}} body{{margin:0;background:linear-gradient(145deg,#070b16,#101a31);color:var(--ink);font:16px/1.55 Inter,ui-sans-serif,system-ui,sans-serif}}
main{{max-width:1080px;margin:auto;padding:48px 22px 90px}} h1{{font-size:clamp(2.4rem,7vw,5rem);line-height:.96;margin:.15em 0}} h2{{margin-top:55px;font-size:1.65rem}} h3{{margin:.2rem 0}}
.eyebrow{{color:var(--blue);font-size:.78rem;font-weight:800;letter-spacing:.11em;text-transform:uppercase}} .muted{{color:var(--muted)}}
.stats{{display:grid;grid-template-columns:repeat(4,1fr);gap:14px;margin:30px 0}} .stat,.panel,.position{{background:rgba(21,28,48,.92);border:1px solid #2a3553;border-radius:16px}}
.stat{{padding:20px}} .stat b{{display:block;font-size:2rem}} .grid{{display:grid;grid-template-columns:1fr 1fr;gap:18px}} .panel{{padding:22px}}
.position{{display:grid;grid-template-columns:360px 1fr;gap:28px;padding:22px;margin:18px 0}} .board svg{{display:block;width:100%;height:auto;border-radius:8px}}
.position-copy{{align-self:center}} .loss{{display:inline-block;color:#16060a;background:var(--red);font-weight:900;border-radius:999px;padding:5px 10px}}
a{{color:#93c5fd}} code{{color:#c4b5fd;white-space:normal}} table{{width:100%;border-collapse:collapse;background:rgba(21,28,48,.7)}} th,td{{padding:11px;border-bottom:1px solid #2a3553;text-align:left}} th{{color:var(--muted)}}
.result{{font-weight:800}} .win{{color:var(--green)}} .loss.result{{background:none;padding:0;color:var(--red)}} .draw{{color:var(--amber)}}
@media(max-width:760px){{.stats{{grid-template-columns:1fr 1fr}}.grid,.position{{grid-template-columns:1fr}}.board{{max-width:420px;margin:auto}}}}
</style></head><body><main>
<div class="eyebrow">Stockfish reality check</div><h1>Rapid review</h1>
<p class="muted">{html.escape(data.username)} · {s['games_analyzed']} latest games · Generated {html.escape(data.generated_at[:10])}</p>
<section class="stats">
 <div class="stat"><span>Record</span><b>{_pct_record(s['record'])}</b><small>W–L–D</small></div>
 <div class="stat"><span>Average CPL</span><b>{s['average_centipawn_loss']}</b><small>lower is better</small></div>
 <div class="stat"><span>Mistakes</span><b>{s['classifications'].get('mistake',0)}</b><small>120–249 cp</small></div>
 <div class="stat"><span>Blunders</span><b>{s['classifications'].get('blunder',0)}</b><small>250+ cp</small></div>
</section>
<section class="grid"><div class="panel"><h2>Main findings</h2><ul>{findings}</ul></div><div class="panel"><h2>Next practice</h2><ol>{plan}</ol></div></section>
<h2>Critical positions</h2><p class="muted">Green arrow shows Stockfish’s preferred move. Try solving each board before reading it.</p>
{''.join(cards)}
<h2>Game log</h2><div style="overflow-x:auto"><table><thead><tr><th>Date</th><th>Opponent</th><th>Result</th><th>Color</th><th>Opening</th><th>Blunders</th><th>Mistakes</th></tr></thead><tbody>{game_rows}</tbody></table></div>
<p class="muted">Thresholds are intentionally practical for club-level rapid: inaccuracy ≥60 cp, mistake ≥120 cp, blunder ≥250 cp. Engine: {html.escape(data.engine)}, {html.escape(data.analysis_limit)}.</p>
</main></body></html>"""
    path.write_text(document, encoding="utf-8")


def write_all(data: ReportData, output_dir: Path) -> list[Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    paths = [
        output_dir / "report.html",
        output_dir / "report.md",
        output_dir / "analysis.json",
        output_dir / "moves.csv",
        output_dir / "critical_positions.pgn",
    ]
    write_html(data, paths[0])
    write_markdown(data, paths[1])
    write_json(data, paths[2])
    write_csv(data, paths[3])
    write_critical_pgn(data, paths[4])
    return paths
