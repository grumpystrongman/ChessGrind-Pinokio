# Chess Intelligence — compact endgame completion and limits

## What is implemented

ChessGrind installs and probes **all 35 three- and four-piece Syzygy WDL/DTZ pairs (70 files)** from the Lichess mirror at `https://tablebase.lichess.ovh/tables/standard`. The compact data occupies approximately **4,346,080 bytes** in `engine/syzygy/`. Binaries are ignored by Git and are not embedded in the public repository.

A new Pinokio setup automatically attempts the compact download. If the mirror is offline the normal chess application still installs, and Stockfish can still estimate endgame moves. Running `python install_syzygy.py --pieces 4` retries or repairs the data. Requests use size limits, bounded downloads, and file checksums in a local receipt. Basic KQvK/KRvK/KPvK probes verify correct WDL/DTZ output.

The existing Endgame Laboratory uses **exact tablebase WDL outcomes** for covered 3-4-piece lessons, and continues to use **depth-limited Stockfish** for positions outside the installed tables. The in-game post-match analysis shows exact WDL/DTZ and WDL-preserving legal moves when covered. A player's live competitive game does not reveal Stockfish best-move analysis before it finishes.

The tablebase status reports `maxCompletePieces=4` only when all 35 pairs are present. In the user's previously installed data, **184 of the 330 existing Endgame Laboratory lessons** have at most four pieces and are eligible for exact grading. This does not mean all 330 lessons are exact.

## Quality suite

`academy_quality_audit.py` validates the geometry of every Chess Vision Academy item: legal forks, pinned pieces, attacked undefended targets, central pawn moves, truly passed pawns, and opposition squares. **3,006 out of 3,006** original examples passed when executed against the installed ChessGrind corpus on November 20, 2026. This checks geometry, **not** an engine-proof of instructional optimality.

The existing `chess_quality_benchmark.py` checks six reproducible public positions at depths 8/12; 5/6 had the same engine-preferred first move. This is **not an accuracy percentage** or proof of perfect chess. The one disagreement was in the Italian Opening.

After code updates, verify the compact dataset with `python -m unittest discover -s tests -p 'test_exact_endgames.py'` and run `python academy_quality_audit.py` separately. A source-level test and an optional full-game lab test are included.

## Restrictions and remaining limitations

- **Five-, six-, and seven-piece** Syzygy tablebases are not installed by default. The 3-5 set is around 1 GB, the six-piece collection is vastly larger, and seven-piece files require many terabytes. These datasets require an explicit storage and bandwidth decision.
- WDL/DTZ is exact within the tablebase's stated rule context, but **DTZ is not distance to checkmate**; chess castling positions and repetition history require separate handling.
- When several moves preserve a winning WDL result, the lab calls them outcome-preserving, not necessarily quickest mate or ideal instructional technique.
- ChessGrind's local language model can still make strategic mistakes. Stockfish results and tablebase claims remain separate evidence types.
- The full example graph is built during setup and refreshed during the daily sync. Embedding builds are best-effort and require FastEmbed's model files; exact and FTS searches remain usable if the model is unavailable.
- Source changes pushed after the Desktop Commander usage limit require a fresh Pinokio source update to reach the existing user installation. The three-/four-piece files and earlier laboratory code were already installed and probed before that limit was reached.

## Primary sources

The tablebase mirror is operated by Lichess: https://tablebase.lichess.ovh/tables/standard/ .

The Syzygy probing implementation is provided by python-chess: https://python-chess.readthedocs.io/en/latest/syzygy.html .
