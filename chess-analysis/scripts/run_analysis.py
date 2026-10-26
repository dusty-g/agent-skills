from pathlib import Path
import argparse
import dataclasses
import json
from chess_analyzer.fetch import ChessComClient
from chess_analyzer.engine import StockfishAnalyzer, find_stockfish
from chess_analyzer.analyze import analyze_games

def main():
    p = argparse.ArgumentParser()
    p.add_argument('--username', required=True, help='Chess.com username to analyze')
    p.add_argument('--games', type=int, default=15)
    p.add_argument('--nodes', type=int, default=8000)
    p.add_argument('--stockfish')
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--html', action='store_true')
    p.add_argument('--pgn-json', type=Path)
    args = p.parse_args()
    if not 1 <= args.games <= 500 or args.nodes < 500:
        p.error('games must be 1–500 and nodes at least 500')
    args.output.mkdir(parents=True, exist_ok=True)
    if args.pgn_json:
        games = json.loads(args.pgn_json.read_text())
    else:
        games = ChessComClient(args.output / 'api-cache', refresh=True).latest_games(args.username, args.games, 'rapid')
    games = sorted((g for g in games if g.get('rules', 'chess') == 'chess' and g.get('time_class') == 'rapid'), key=lambda g:g.get('end_time',0), reverse=True)[:args.games]
    if not games:
        raise SystemExit('No matching standard rapid games found')
    (args.output / 'games.json').write_text(json.dumps(games))
    with StockfishAnalyzer(find_stockfish(args.stockfish), args.nodes, args.output / 'positions.json') as engine:
        data = analyze_games(games, args.username, engine)
    (args.output / 'analysis.json').write_text(json.dumps(dataclasses.asdict(data)))
    if args.html:
        from chess_analyzer.report import write_all
        write_all(data, args.output)
    print(json.dumps({k:v for k,v in data.summary.items() if k != 'critical_moves'}))

if __name__ == '__main__':
    main()
