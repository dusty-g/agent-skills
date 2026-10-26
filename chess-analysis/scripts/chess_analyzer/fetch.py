from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


API_ROOT = "https://api.chess.com/pub"


class ChessComError(RuntimeError):
    pass


class ChessComClient:
    def __init__(self, cache_dir: Path, refresh: bool = False) -> None:
        self.cache_dir = cache_dir
        self.refresh = refresh
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def _get_json(self, url: str, cache_name: str, max_age: int = 300) -> dict[str, Any]:
        cache_path = self.cache_dir / cache_name
        if (
            not self.refresh
            and cache_path.exists()
            and time.time() - cache_path.stat().st_mtime <= max_age
        ):
            return json.loads(cache_path.read_text(encoding="utf-8"))

        request = urllib.request.Request(
            url,
            headers={
                "User-Agent": "chess-analysis/0.1 (public game analysis)",
                "Accept": "application/json",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                data = json.load(response)
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                raise ChessComError(f"Chess.com could not find that player or archive: {url}") from exc
            raise ChessComError(f"Chess.com returned HTTP {exc.code}: {url}") from exc
        except (urllib.error.URLError, TimeoutError) as exc:
            raise ChessComError(f"Could not reach Chess.com: {exc}") from exc

        cache_path.write_text(json.dumps(data), encoding="utf-8")
        return data

    def latest_games(self, username: str, count: int, time_class: str) -> list[dict[str, Any]]:
        username = username.strip().lower()
        archives = self._get_json(
            f"{API_ROOT}/player/{username}/games/archives",
            f"{username}-archives.json",
            max_age=300,
        ).get("archives", [])
        if not archives:
            raise ChessComError(f"No public game archives found for {username!r}.")

        selected: list[dict[str, Any]] = []
        for archive_url in reversed(archives):
            year, month = archive_url.rstrip("/").split("/")[-2:]
            payload = self._get_json(
                archive_url,
                f"{username}-{year}-{month}.json",
                max_age=300 if archive_url == archives[-1] else 31_536_000,
            )
            selected.extend(
                game for game in payload.get("games", []) if game.get("time_class") == time_class
            )
            if len(selected) >= count:
                break

        selected.sort(key=lambda game: game.get("end_time", 0), reverse=True)
        return selected[:count]

