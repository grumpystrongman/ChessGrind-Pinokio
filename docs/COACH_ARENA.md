# ChessGrind Coach Arena

The roster includes 22 fictional bots: Stockfish Skill Level 0-20 and a
MAX opponent (unrestricted skill, longer thinking budget, still time-limited).
The opponents' names, bios and illustrated SVG avatars are narrative skins.
Stockfish chooses every move. Ratings are intentionally not represented as
calibrated human Elo strengths. Active and solid are shallow, bounded
move-selection biases and are not reliable human personality simulations.

Up to five custom coach cards are stored in userdata/arena_coaches.json.
They include a name, specialty, biography, guidance tone, local voice ID
and speaking speed. Creating/deleting a coach does not delete games.

Voice options: ChessGrind can reuse %%LOCALAPPDATA%%/EmberWriter/models/kokoro
when the EmberWriter Kokoro v1.0 model and voice bank are already installed.
Choose Install optional neural coach voices in Pinokio to install the
kokoro-onnx runtime and download the model from the official release only if
neither EmberWriter nor ChessGrind already has the files. The alternative
asset location is %%LOCALAPPDATA%%/ChessGrind/models/kokoro. Model files
are never added to Git. No text is submitted to a hosted speech service.
Browsers with Web Speech synthesis can read coaching messages without Kokoro,
though available voices and offline behavior depend on the OS/browser.

Selecting a coach changes the narrator and the saved coaching profile.
It is not yet a separate LLM fine-tune or real-time chess strategy engine.
The active coaching advice remains board-grounded and deliberately withholds
preferred chess moves during live play. Neural rendering is CPU-based and
may take a few seconds on first use. Users can turn off automatic speech.

The 3,000 Academy positions are validated variants of authored positions,
not 3,000 externally sourced, unique human-level puzzles. Before claiming
puzzle-quality certification, add adversarial ambiguity tests, independent
difficulty calibration and held-out source positions.

## Playable custom coaches and home entry point

Each of the five locally saved coach cards now carries its own Stockfish skill (0-20) and style (balanced, active, solid). Saved profiles from earlier builds automatically receive skill 8 and balanced style without overwriting names or voice settings. From the home page, choose a coach card to open the Coach Arena with that exact coach selected as the opponent. Coaches also appear at the top of Play & Review, above the 22 fictional preset rivals. The opponent is Stockfish, while the same coach may narrate educational feedback; a voice model does not choose chess moves.

## Character-first coaching cast (2026-11-20)

Users now recruit up to five named, authored coach characters rather than choosing teaching quirks or inventing personalities. Morgan (threat awareness), Quinn (candidate calculations), Iris (pawn structure), Rook (loose pieces), and Vera (endgame tempos) each have a fixed biography, personality, coaching tone, habit, and signature neural voice. The playing level and speaking rate can still be adjusted; these do not rewrite character identity. Existing saved coaches are retained, with prior custom coaches left available. The backend refuses changes to canonical identity fields for the five authored characters; the browser no longer presents tone/quirk/name/biography/voice editing. Recruit via POST /api/arena/coach/recruit, after selecting a coach in the Play & Review studio. Their voices and authored habits are part of the characters, not user-created stereotypes.
