# Runtime setup

Use `python -m pip install python-chess` in a writable Python environment if needed. No requests dependency is required; fetching uses urllib.

Find Stockfish via explicit path, STOCKFISH_EXECUTABLE, PATH, /usr/games/stockfish, or /opt/homebrew/bin/stockfish. Prefer an existing compatible binary. If missing, obtain a compatible official release through https://api.github.com/repos/official-stockfish/Stockfish/releases/latest and use the returned asset URL. Select for the actual OS/architecture; do not assume an old asset naming convention. Extract in scratch using --no-same-owner, not into system directories. Do not bundle a large engine binary in the skill. Respect network restrictions and never claim engine analysis when engine setup failed.

No Chess.com credentials are needed. The public endpoints are /pub/player/{username}/games/archives followed by monthly archive URLs. Raw game exports include PGNs and clock annotations. Fetch only the requested public games; do not change account settings or submit moves.

Use Python 3.10 or newer. The only Python dependency is python-chess; Stockfish is a separate executable. No paid service, account credentials, or API key is required. If Library is unavailable in the recipient’s environment, deliver requested reports using that environment’s supported file mechanism.
