# Chess Grind — Pinokio launch kit

Status: Windows x64 release candidate. Not yet published to GitHub or the Pinokio directory.
Replace \`[PUBLIC INSTALL URL]\` only **after** a clean installation has been verified on a separate Windows user profile.

## Listing details

**Name:** Chess Grind

**Tagline:** Stop memorizing moves. Start understanding chess.

**Short Pinokio description (under 200 characters):**

A personal chess school that studies your Chess.com games, teaches openings and endgames, analyzes moves with Stockfish, and lets you study historical masters. Runs on your PC.

**Category:** Chess · Education · Local AI · Games

**Keywords:** chess, stockfish, chess.com, openings, endgames, local AI, historical games, learning, spaced repetition, chess analysis

**Platform:** Windows x64 (initial beta)

**Local AI:** Ollama optional; on-device chess engine available without Ollama

**App image:** \`icons/icon-192.png\` (square; verify Pinokio's listing media requirements before submission)

## Main Pinokio app description

# Chess Grind
### Chess training should teach you *why*, not just show you a better move.

After a game, Stockfish can tell you that a move lost 1.6 pawns of evaluation. That number isn't the same as understanding why it was a mistake—or recognizing the same problem in the next game.

Chess Grind is a local-first chess school built around that gap. It turns actual positions into explanations, practice, and repeatable decisions.

**Bring your own games.** In Settings, enter your own Chess.com username or public member-profile URL. Chess Grind checks that the account exists, then imports public game history after you opt in. No Chess.com password is required. The publisher's personal data is never part of the install.

**Learn both colors.** Study the full ECO opening-name catalog, explore plans as White and Black, practice with spaced repetition, and test transfer to unfamiliar positions. Recalling a memorized move isn't treated as proof of mastery.

**Make mistakes safely.** During opening, endgame and master-move drills, you get up to three attempts. Wrong answers are met with a chance to reconsider; a concrete engine-backed solution appears when you've used your attempts.

**Understand historical chess.** Replay a curated local archive of 4,404 recorded games representing 39 major players. Explore a move's actual effect, an approximate Stockfish assessment, alternative lines, and opponent replies. The coach discusses both players rather than treating the winner as always correct.

**Play, save, and review.** Play a local Stockfish opponent. Your games are saved automatically, remain discoverable, and can be replayed and exported as PGN. Post-game reviews help identify teachable decisions.

**Talk through your position.** If you have Ollama and the supported local model installed, a conversational tutor can answer follow-up questions using recorded moves and position-specific engine evidence. Core chessboard instruction still works without Ollama.

### Local by design

Your games and progress live in a local data folder, not in the publisher's cloud. The learning server listens on \`127.0.0.1\`, and remote multiplayer and public invite links remain disabled.

Chess.com syncing and optional initial downloads use the internet; this is **not** a completely offline installer. Stockfish evaluations are depth-limited, historical motives are interpretations, and no training app can certify a playing-strength rating.

**Initially available:** Windows x64 beta; installation downloads Python dependencies and the official Stockfish 19 engine. Conversational coaching requires a separate local Ollama setup.

**Install:** [PUBLIC INSTALL URL]

### Attribution

Historical game scores: [PGN Mentor](https://www.pgnmentor.com/files.html). Named ECO openings: [Lichess chess-openings](https://github.com/lichess-org/chess-openings) (CC0). Stockfish: [official project](https://github.com/official-stockfish/Stockfish) (GPLv3). Chess Grind is independent and is not affiliated with Chess.com, Stockfish, Lichess, or Pinokio.

---

## Pinokio community announcement — human, maker-focused

I started building Chess Grind because I kept coming back to the same problem with chess study: finding the strongest move is easy compared with understanding it. A chess engine can show a line, but it doesn't always help you understand what you overlooked, what your opponent could have done, or why you'd recognize the idea in a different position.

The application has grown into a local chess school built around those questions. You can connect your own public Chess.com profile, bring in your games, practice opening plans as either color, work through endgames, and play against Stockfish. The exercises give you room to think—up to three attempts before revealing the solution—because I don't think looking at the answer after one mistake is the same thing as learning it.

One part I'm especially interested in is studying historical masters. The app includes 4,404 recorded games from 39 players. You can walk through the games from both sides, inspect what each move actually changed, and compare it with Stockfish's analysis. There's an optional local conversational coach for deeper questions, but the board should teach you something before you ever need to open a chat.

This is an early Windows beta, and I'm deliberately keeping it local. Each person connects their own account; no personal Chess.com history is shipped with the app. Ollama is optional, and there are no public servers or multiplayer invite links.

I'm looking for people willing to test the install and, more importantly, test whether the coaching actually makes chess easier to understand. The most useful feedback would be a position where the explanation didn't help, or a lesson that still felt like memorization.

**Chess Grind for Pinokio:** [PUBLIC INSTALL URL]

## Short Pinokio community version

Chess Grind is a local chess learning app I've been working on because I wanted chess study to go beyond “Stockfish says this move is better.”

It brings together public Chess.com game imports (your own username), White/Black opening training, endgame practice, saved games, Stockfish reviews, and 4,404 historical games to study move by move. It gives you three chances to rethink a move before revealing the solution. Ollama is optional for conversational coaching; the core chess training works locally.

The first beta targets Windows x64. I'd especially welcome feedback on whether the explanations help you understand *why* a move works—and whether the first-run Pinokio install is straightforward.

**Install:** [PUBLIC INSTALL URL]

---

## Suggested release-page headline and subhead

**Chess Grind**
*Your games. Your mistakes. A better way to learn.*

Turn recorded moves into chess lessons. Study the best games from history, build openings from both sides, and improve with a private Stockfish-powered coach.

## Image order and exact suggested captions

1. \`02-study-masters.png\` — **Study chess history from both sides.** Follow a real recorded game, with a board, context, and an optional local coach.
2. \`08-move-by-move-coaching.png\` — **Every move can teach something.** Engine verdicts, opponent responses, possible better lines, and practical lessons.
3. \`03-opening-mastery.png\` — **Learn a plan, not a sequence.** Study White and Black with ECO opening context and transfer practice.
4. \`04-endgame-lab.png\` — **Build endgame understanding.** Practice with board positions and concrete engine-backed feedback.
5. \`05-play-ai-and-history.png\` — **Play locally, keep your games.** Stockfish opponent, saved history, replay, and PGN export.
6. \`06-learning-lab.png\` — **Spot, Move, Predict, Learn, Prove.** Work through an adaptive visual learning loop.
7. \`01-account-settings.png\` — **Your Chess.com account.** Bring your own public game history; no password or publisher's profile.
8. \`07-dashboard-first-run.png\` — **A personal training room.** Review imported games and receive lessons adapted to your own choices.

Use screenshots captured from the actual clean demo installation. No personal games, names, addresses, or developer data should appear.

## Suggested 5-image carousel cover text

1. **CHESS GRIND** — Learn the why behind the move.
2. **STUDY THE MASTERS** — One game. Two sides. Real decisions.
3. **MASTER THE OPENING** — Play White. Play Black. Understand both.
4. **REVIEW YOUR GAMES** — Stockfish evidence, not just a score.
5. **YOUR CHESS SCHOOL** — Local, personal, and built for practice.

---

## Press / creator one-paragraph pitch

Chess Grind is a Windows-first, local chess training application packaged for Pinokio. It brings public Chess.com game imports, Stockfish-based analysis, structured opening and endgame training, and a 4,404-game historical master library into one learning environment. The distinctive emphasis is on comprehension over memorization: learners are given repeated attempts, move-specific explanations, both-color perspectives, and practice on new positions. User data stays in a local application folder; an optional Ollama-based tutor adds conversational explanations.

## Community Q&A

**Does it use my Chess.com games or the developer's?** Yours. Enter and confirm your own public username or member-profile URL in Settings. There is no bundled developer profile, and no Chess.com password is requested.

**Do I need a paid account?** No paid Chess.com account is required for the public-game import. You do need a compatible Windows x64 machine and Internet access for the installer and for Chess.com synchronization.

**Do I need Ollama?** Only for conversational local LLM explanations. Interactive boards, many structured lessons, and Stockfish reviews operate without Ollama.

**Is it really offline?** The chess engine and locally installed materials run on your PC. Initial dependency downloads, optional Ollama model download, and Chess.com synchronization require Internet access.

**Can I play friends via invite link?** Not yet. Online human-vs-human play has deliberately been deferred. You can play the local engine, save your games, and review them.

**Are the 4,404 historic games all the masters' games?** No. They are a curated multi-era sample of legal recorded PGN scores; this is not the complete historical chess record.

**Does it prove I mastered an opening?** No single test does. The app keeps recall, understanding, and transfer practice separate to discourage false confidence.

**What happens on updates?** The release script is designed to preserve \`userdata/\`, where your games and local settings live. Always back up that folder before changing installations.

**Is it affiliated with Chess.com or Pinokio?** No. It uses public chess data and a local engine; it is an independent project.

**Is this a finished public release?** The materials are release-candidate drafts. Do not post the install URL or claim Pinokio directory verification until a clean install and publisher checks have passed.
