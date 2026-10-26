from __future__ import annotations

import hashlib
import json
import os
import shutil
from pathlib import Path
from typing import Any

import chess
import chess.engine


def find_stockfish(explicit: str | None = None) -> str:
    candidates = [
        explicit,
        os.environ.get("STOCKFISH_EXECUTABLE"),
        shutil.which("stockfish"),
        "/usr/games/stockfish",
        "/opt/homebrew/bin/stockfish",
        "/usr/local/bin/stockfish",
    ]
    for candidate in candidates:
        if candidate and Path(candidate).is_file() and os.access(candidate, os.X_OK):
            return str(Path(candidate).resolve())
    raise FileNotFoundError(
        "Stockfish executable not found. Pass --stockfish PATH, set "
        "STOCKFISH_EXECUTABLE, or install it with `brew install stockfish` "
        "(macOS) / `apt install stockfish` (Ubuntu)."
    )


class PositionCache:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            try:
                self.data: dict[str, dict[str, Any]] = json.loads(path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                self.data = {}
        else:
            self.data = {}
        self.dirty = False

    @staticmethod
    def key(fen: str, nodes: int, engine_name: str) -> str:
        raw = f"{fen}|nodes={nodes}|engine={engine_name}".encode()
        return hashlib.sha256(raw).hexdigest()

    def get(self, key: str) -> dict[str, Any] | None:
        return self.data.get(key)

    def put(self, key: str, value: dict[str, Any]) -> None:
        self.data[key] = value
        self.dirty = True

    def save(self) -> None:
        if self.dirty:
            temp = self.path.with_suffix(".tmp")
            temp.write_text(json.dumps(self.data, separators=(",", ":")), encoding="utf-8")
            temp.replace(self.path)
            self.dirty = False


class StockfishAnalyzer:
    def __init__(self, executable: str, nodes: int, cache_path: Path, hash_mb: int = 128) -> None:
        self.nodes = nodes
        self.engine = chess.engine.SimpleEngine.popen_uci(executable)
        self.engine_name = self.engine.id.get("name", "Stockfish")
        available = self.engine.options
        options: dict[str, Any] = {}
        if "Hash" in available:
            options["Hash"] = min(hash_mb, int(available["Hash"].max or hash_mb))
        if "Threads" in available:
            options["Threads"] = 1
        if options:
            self.engine.configure(options)
        self.cache = PositionCache(cache_path)

    def close(self) -> None:
        self.cache.save()
        self.engine.quit()

    def __enter__(self) -> "StockfishAnalyzer":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def evaluate(self, board: chess.Board, pv_length: int = 5) -> dict[str, Any]:
        fen = board.fen()
        key = self.cache.key(fen, self.nodes, self.engine_name)
        cached = self.cache.get(key)
        if cached is not None:
            return cached

        info = self.engine.analyse(board, chess.engine.Limit(nodes=self.nodes))
        score = info["score"].pov(chess.WHITE).score(mate_score=10_000)
        pv = list(info.get("pv", []))[:pv_length]
        pv_uci = [move.uci() for move in pv]
        result = {
            "score_white_cp": int(score if score is not None else 0),
            "best_move_uci": pv_uci[0] if pv_uci else "",
            "pv_uci": pv_uci,
            "depth": info.get("depth"),
            "nodes": info.get("nodes"),
        }
        self.cache.put(key, result)
        if len(self.cache.data) % 100 == 0:
            self.cache.save()
        return result

