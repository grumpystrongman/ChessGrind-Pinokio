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
