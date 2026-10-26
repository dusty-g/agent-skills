# Agent skills

A small collection of shareable agent skills. Currently includes **[chess-analysis](chess-analysis/SKILL.md)**: review recent public Chess.com games with Python and Stockfish, identify recurring mistakes, and provide practical coaching. HTML reports are optional.

## Use the skill

The installable unit is the complete `chess-analysis/` folder, including its scripts, references, and assets. This repository contains a skill folder, not a plugin package or marketplace submission. `agents/openai.yaml` is optional OpenAI interface metadata; other hosts may ignore it.

| Environment | Setup |
| --- | --- |
| Codex | Copy `chess-analysis/` into your project's `.agents/skills/` directory, then invoke `$chess-analysis` with your Chess.com username. See [OpenAI's skill documentation](https://developers.openai.com/codex/skills/). |
| Claude Code | Copy `chess-analysis/` into `.claude/skills/` in your project (or `~/.claude/skills/` for personal use), then invoke `/chess-analysis`. See [Claude Code's skill documentation](https://code.claude.com/docs/en/skills). |
| ChatGPT | Where custom skill import is available, import the complete skill folder using that environment's supported flow. Otherwise, attach the folder as a ZIP and ask ChatGPT to read `SKILL.md`; attaching files alone does not install a skill. |

Execution requires Python 3.10+, `python-chess`, a compatible Stockfish executable, and network access to the public Chess.com API. Availability depends on the host's tools and permissions; importing instructions does not provide those capabilities. No Chess.com credentials or API key are required. If Library is unavailable, use the host's supported file delivery mechanism.

Example request: “Use chess-analysis to review my latest 5 rapid games. My Chess.com username is YOUR_USERNAME. Summarize the most useful practice focus in chat.”

## Run the bundled script directly

From the repository root, with Python and Stockfish installed:

```sh
python -m pip install python-chess
python chess-analysis/scripts/run_analysis.py \
  --username YOUR_USERNAME --games 5 \
  --stockfish /path/to/stockfish \
  --output /path/to/scratch/chess-review
```

Add `--html` to create reports. Keep output and caches outside the repository and installed skill. See [runtime setup](chess-analysis/references/runtime.md) for engine discovery and [SKILL.md](chess-analysis/SKILL.md) for interpretation limits. Screening scores and heuristic labels require deeper checks before making specific coaching claims.

## Scope and license

Only the supplied shareable skill is included. No personal game records, reports, caches, credentials, or private skill collection are included. The original skill files and their existing [MIT notice](chess-analysis/scripts/LICENSE) are preserved; no additional license grant is added here. Python-chess and Stockfish are separate dependencies with their own licenses and are not bundled.
