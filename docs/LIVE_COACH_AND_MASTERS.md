# ChessGrind: contextual coaching and master-inspired challengers

## Contextual coaching — what is actually implemented

- Every legal player move in a sparring game is compared to Stockfish's top
  legal move using an approximate depth-9 analysis. The game UI displays a
  concise grade: best / strong / inaccuracy / mistake / blunder. These labels
  are *limited-depth estimates* and are not proofs.
- Coaches do **not** repeat the same generic warning every turn.
  Comments are shown selectively, with speech further restricted to meaningful
  moves. The user's opt-in "Speak coaching automatically" toggle still governs
  actual audio playback.
- Each of the up to five user-editable coaches now has:
  a distinctive name, biography, coaching tone, a **teaching quirk**,
  speaking voice/rate, and a playable Stockfish strength/style.
- Seven teaching quirks: ask about opponent threats; require two candidates;
  watch undefended pieces; king safety; pawn structure; endgame tempos;
  minimalist guidance.
- Coach prompts are short, distinct across tones and identities, and tied to
  concrete chess decisions and occasional reminders when repeated mistakes
  occur. This is **not yet** real-time speech recognition or full LLM-generated
  chess dialogue. Local Kokoro playback is supported via the existing optional
  voice integration.
- In-progress games retain legal moves, opponent identity, and score. A coach
  speaks *after* a played decision is assessed, not before the user makes it.
- A depth-9 engine comparison runs during live play and may slightly increase
  move latency. Deeper, more reliable analysis remains in post-game review.

## Play the masters — what is actually implemented

- The local PGN Mentor archive has 4,404 historical game scores. The installed
  archive represents **39 masters**; current coverage is not comprehensive.
- A master's actual opening move can be selected **only when the live board
  exactly matches** a position from their archived games, and only when a
  shallow Stockfish sanity check rules out a gross tactical error.
- After that, *Stockfish* makes the moves with a broad historically themed
  preference for active, solid, or balanced choices and a configurable
  engine skill. Users aren't playing a neural reconstruction of the real
  chess master; this is a **master-inspired bot**.
- The app bundles 39 **descriptive style profiles** calculated from recorded
  game-score data. This analysis currently describes 3,864 of the 4,404
  records where an archive player's name could be matched to a side. It
  reports opening frequencies and basic capture/check rates; the stats
  are not rigorous proof of individual style or intent.
- The 39 fictionalized rival *insignia* images are original symbolic artwork,
  not real photographs or claimed likenesses of historical figures.
- No celebrity voices, impersonations, original game commentary, or original
  tournament footage are used. Historical game scores are source-attributed.
- User personal games and custom coaches stay in the local ChessGrind data folder.

## Where to find it

From the ChessGrind home page, select **MY COACHES & PLAY**, then switch to
**Play & Review**. **Play your custom coach** appears ahead of **Play the
masters**, which has a search field and 39 selectable master-inspired bots.
From a master profile you can also open the historical game library.

During a game, **Best move** / **Mistake** / **Blunder** is displayed beneath
the board and meaningful observations appear in the coach panel. Turn on
**Speak coaching automatically** only if you want these observations spoken.

## Known limitations and future work

- Depth-limited Stockfish grades are sensitive to search horizon and may
  misclassify complex moves. Improve using multipv, cached position evaluations
  and mate/piece-risk-aware thresholds.
- Learner struggle detection currently uses a rolling short-term queue in
  memory. Persist topic-specific mistakes and mastered skills across sessions.
- Human-master styles need statistical features for more middlegame motifs,
  pawn structures, opening transitions, and actual move-choice evaluation
  against *held-out historical games* before accuracy claims are credible.
- The voices still use neural TTS rendering of short, templated sentences.
  Full conversational voice coaching, including microphone input and
  freeform personalized questions, is a separate feature.
- Master game availability depends on completing the legal public archive
  import. If no historical games have been imported, the gallery is empty.

## Verified

- HTTP: 39 historical master profiles; master game creation; actual opponent
  reply; per-move Stockfish grades; custom coach save/play.
- Browser: selecting a master via URL, search/gallery load, game creation,
  interacting with the chessboard and visible move evaluation.
- Persona QA: the same proven blunder generates different coaching reactions
  and different teaching-quirk reminders for a calm vs playful coach.
- Local Kokoro WAV generation and baseline sparring engine behavior still pass.
