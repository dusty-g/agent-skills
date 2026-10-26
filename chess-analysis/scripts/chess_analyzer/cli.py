from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .analyze import analyze_games
from .engine import StockfishAnalyzer, find_stockfish
from .fetch import ChessComClient, ChessComError
from .report import write_all


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="chess-analysis",
        description="Find practical patterns in recent Chess.com games.",
    )
    p.add_argument("username", help="Chess.com username to analyze")
    p.add_argument("--games", type=int, default=15, help="Number of recent games (default: 15)")
    p.add_argument("--time-class", default="rapid", choices=("rapid", "blitz", "bullet", "daily"))
    p.add_argument("--nodes", type=int, default=8000, help="Stockfish nodes per position (default: 8000)")
    p.add_argument("--stockfish", help="Path to Stockfish executable")
    p.add_argument("--output", type=Path, default=Path("output"))
    p.add_argument("--cache", type=Path, default=Path(".cache"))
    p.add_argument("--refresh", action="store_true", help="Ignore cached Chess.com responses")
    return p


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    if args.games < 1 or args.games > 500:
        print("--games must be between 1 and 500", file=sys.stderr)
        return 2
    if args.nodes < 500:
        print("--nodes must be at least 500", file=sys.stderr)
        return 2

    try:
        stockfish = find_stockfish(args.stockfish)
        client = ChessComClient(args.cache / "chess-com", refresh=args.refresh)
        print(f"Fetching the latest {args.games} {args.time_class} games for {args.username}...")
        games = client.latest_games(args.username, args.games, args.time_class)
        if not games:
            print("No matching games found.", file=sys.stderr)
            return 1
        print(f"Found {len(games)} games. Starting Stockfish...")
        with StockfishAnalyzer(
            stockfish,
            nodes=args.nodes,
            cache_path=args.cache / "positions.json",
        ) as engine:
            data = analyze_games(games, args.username, engine)
        paths = write_all(data, args.output)
        print("\nFinished:")
        for path in paths:
            print(f"  {path.resolve()}")
        return 0
    except (ChessComError, FileNotFoundError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

