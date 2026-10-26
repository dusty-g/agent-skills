---
name: chess-analysis
description: Analyze a player’s recent Chess.com games using the bundled python-chess and Stockfish workflow. Use for running chess analysis, reviewing recent games, identifying recurring mistakes, explaining opening problems, or evaluating a practice experiment. Supports chat-only coaching and optional HTML reports.
---

# Chess Analysis

## Defaults
- Resolve the Chess.com username from the current request or an explicitly established preference. If unknown, ask for it before fetching games; never guess or assume a built-in account. Default to standard rapid chess, latest 15 completed games. For “last few” use 5; honor explicit counts and usernames.
- Fetch fresh public API data every run. Report game dates, count, results, engine and analysis budget when relevant. Convert dates to the user's timezone when describing local dates.
- Default to a concise chat summary. Generate HTML only when requested or explicitly required by the active scheduled task. Never alter a schedule merely by invoking this skill.
- Use Stockfish at 8,000 nodes per position for screening. Recheck positions used for specific coaching at 150,000 nodes or higher. Do not treat shallow scores as exact or as Chess.com accuracy.

## Run the bundled workflow
1. Locate this skill's `scripts` directory. Work and cache outside the installed skill directory.
2. Check Python for `chess` and locate Stockfish. If needed install `python-chess` in a writable environment. See `references/runtime.md` for obtaining an engine. Do not assume previous runtime installations persist.
3. Run:
   `python <skill>/scripts/run_analysis.py --username <chess-com-username> --games 5 --stockfish <engine-path> --output <scratch-output>`
   Omit `--games` for 15. Add `--html` only for an HTML report. `--pgn-json` accepts an already fetched API games array for reproduction without another fetch.
4. Read `analysis.json` and use raw PGNs to reconstruct positions, previous moves and actual replies. The run preserves `games.json`. Use `fen_before` and `fen_after` with python-chess for deeper engine checks. Never invent continuations; validate legal moves and notation.
5. Save user-facing requested reports with Library, preserving an existing report's identity if updating it. Chat-only runs need no new report artifact. Keep caches and intermediate results in scratch. Never write runtime output into the installed skill.

## Interpret carefully
- Prioritize avoidable material losses and missed immediate threats over subtle opening refinements. Distinguish missed winning chances from moves that lose an equal position.
- Automatic motif labels are heuristics: a best-reply capture does not prove a piece was undefended or lost for free. Check recaptures, pins, forks, exchange value and the whole relevant line.
- Scores are from the user's perspective; practical loss is clipped at +/-500 centipawns. Error totals omit some mistakes in already lost positions and must not be presented as exhaustive.
- Exclude nonstandard variants. Flag parsing errors, missing clocks or failed retrieval rather than silently using stale data.
- Compare time spent and clock remaining. Do not infer that the player forgot to check, was tilted or saw a particular line solely from moves or timing.
- Small batches are descriptive; avoid claiming statistically established improvement. Compare matched game counts and settings, inspect concrete examples, and distinguish observed behavior from explanations.

## Coach from evidence
Lead with the most useful finding. Give 2–3 concrete examples with opponent, game link, move, consequence and a plain-language alternative or question. Offer one small practice focus, not a broad homework list. Do not default to generic “checks, captures, threats” advice when specific failures are visible.

Choose practice experiments from the current player’s observed mistakes and stated goals. Do not assume a rating, opening repertoire, prior diagnosis, or an existing experiment. When an experiment is agreed, record its scope and game boundary in the conversation or a requested report.

For follow-up experiment reviews, establish which games belong to the new batch using timestamps/URLs or the user's supplied boundary. Do not mix baseline games into the follow-up silently.
