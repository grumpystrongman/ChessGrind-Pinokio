# ChessGrind Chess Intelligence v1

ChessGrind now maintains a persistent local chess evidence graph and semantic example index alongside existing player games. This is **not a perfect chess oracle**. A vector match is an analogy, an Academy lesson is a pedagogical example, a historical master move is a recorded choice, and Stockfish is an approximate search evaluation. Those kinds of evidence must never be conflated.

## Storage and provenance

The tables `kg_nodes`, `kg_edges`, `kg_positions`, `kg_examples`, `kg_examples_fts`, `kg_vectors`, `kg_position_evaluations`, and `kg_player_events` are added without changing existing application tables. They live in the usual `userdata/chess.db` SQLite database. Exact positions are indexed by EPD (piece placement, turn, castling, and legal en passant). The half-move clock is preserved in stored FEN; results that depend on the 50-move rule are therefore **not assumed** solely from an EPD match.

In the first build on the existing Pinokio installation: 15 concepts, 3,006 Academy examples, 586 examples from locally analyzed personal games, and 1,500 annotated historical game decisions (from 150 imported master games). There are 5,092 examples over 4,377 normalized positions, with 9,484 graph nodes and 12,282 typed relationships. This is a corpus of sourced examples, not 5,092 independent, uniquely engine-proven chess puzzles.

Historical example moves are legal selections from source-attributed game scores, **not guaranteed best**. Academy examples have legal geometry checked and acceptance squares retained; pedagogical interpretation is not a complete engine proof. Personal game alternatives are from prior depth-limited Stockfish analyses. The result includes the origin and verification scope.

## Semantic search

All 5,092 examples were embedded using ChessGrind's already-installed FastEmbed MiniLM ONNX model `sentence-transformers/all-MiniLM-L6-v2`. Normalized float vectors are stored in the `kg_vectors` SQLite table; no separate Qdrant service or model download is required. The search supports:
- exact position matches;
- SQLite FTS5 keyword retrieval;
- cosine similarity against stored local vectors;
- result deduplication and source-kind diversification;
- source attribution and explicit uncertainty labels.

The vector model cache remains local to the user profile. Vectors are not uploaded to any hosted service.

## Stockfish verification and endgames

`verified_chess.verify(fen, played_uci=None, depth=12, multipv=3)` checks the FEN and move legality, then evaluates up to five candidate moves using locally installed Stockfish. It returns each legal move and SAN variation, evaluation in centipawns and mate information when available, search depth, and a cache hit flag. Results are cached by position, engine executable signature, requested depth and MultiPV. It **does not** claim a forced outcome beyond a validated terminal state.

Optional Syzygy lookup uses existing files referenced by `CHESSGRIND_SYZYGY_DIR`. No tablebases were downloaded as part of this release. If the files are absent or don't cover a position, the result reports no tablebase; it never invents exact endgame information.

## In-game user experience

In the full-screen match conversation rail, **Chess intelligence** provides:
- **Related lessons**: sourced, concept-associated examples from the position, FTS, and vectors, clearly marked as analogies or exact matches.
- **Engine variations**: depth-limited MultiPV after a game finishes. Both the button and the server endpoint block engine-best alternatives during active competitive play.
- Current learner patterns from stored game decisions, where available.

The Ollama coach conversation receives a small, source-attributed set of examples and learner patterns. The character model chooses the teaching language, never the Stockfish moves or evaluations. The evidence is introduced as untrusted source material, not executable instructions.

## Commands

From the ChessGrind app directory with its Python environment:

```powershell
python chess_knowledge.py status
python chess_knowledge.py build --master-games 150
python chess_knowledge.py vectors
python chess_knowledge.py search --fen "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1" --query "control the center"
```

Build and vectorization are incremental/idempotent. New live sparring decisions are recorded automatically. Other imported historical and game-analysis sources can be refreshed with the build command. Existing saved user games are never deleted.

## Verification performed

- Parsed all Python and JavaScript integration modules.
- Built 5,092 examples and their corresponding graphs, positions, and vectors locally.
- Verified semantic retrieval finds concept-relevant positions; exact starting-position results are correctly labeled.
- Verified real Stockfish MultiPV and conversion of returned variations to legal SAN moves.
- End-to-end local HTTP test using a temporary copy of the user database: index statistics, sourced evidence, block engine analysis while game active, record a played move into learning history, enable engine analysis after resignation, and read cached results on subsequent calls.
- Original Pinokio data was preserved, and code was copied directly into the installed application.

## Next improvements

This first release does not claim human-master move-choice fidelity, perfect chess explanation, complete Syzygy coverage or source-perfect classification of all Academy puzzles. Future quality work should add seven-piece tablebases where storage permits, multi-depth agreement checks, PGN-provenance reviews, broader nonduplicated tactical examples, and automatic graph refresh after external game imports. Every coaching claim should be testable against chess rules and engine evidence rather than accepted because an LLM sounds confident.
