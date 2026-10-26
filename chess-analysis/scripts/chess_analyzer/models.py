from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class MoveAnalysis:
    ply: int
    move_number: int
    color: str
    san: str
    uci: str
    fen_before: str
    fen_after: str
    best_move_uci: str
    best_move_san: str
    eval_before_cp: int
    eval_after_cp: int
    centipawn_loss: int
    classification: str
    phase: str
    clock_seconds: float | None
    seconds_spent: float | None
    motifs: list[str] = field(default_factory=list)
    pv_san: list[str] = field(default_factory=list)


@dataclass
class GameAnalysis:
    uuid: str
    url: str
    end_time: int
    date: str
    user_color: str
    opponent: str
    user_rating: int | None
    opponent_rating: int | None
    result: str
    result_detail: str
    opening: str
    eco_url: str
    time_control: str
    chess_com_accuracy: float | None
    moves: list[MoveAnalysis]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ReportData:
    username: str
    generated_at: str
    engine: str
    analysis_limit: str
    requested_games: int
    games: list[GameAnalysis]
    summary: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "username": self.username,
            "generated_at": self.generated_at,
            "engine": self.engine,
            "analysis_limit": self.analysis_limit,
            "requested_games": self.requested_games,
            "summary": self.summary,
            "games": [game.to_dict() for game in self.games],
        }

