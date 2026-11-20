# Local conversational coaches and accessible post-game review

## Why this exists

Previous rival dialogue consisted of five short lines per character, rotated by the
move counter. That caused repeated praise and very little chess reasoning. In
addition, the report for **Review my decisions** was rendered outside the
full-viewport match room, so pressing Review could appear to do nothing.

## New behavior

- All 22 fictional rivals and the five authored teaching coaches have distinct
  immutable character briefs. Same board context and engine triggers can result
  in different language, questions, emotional responses and teaching priorities.
- The installed desktop machine's local Ollama service provides natural-language
  conversation using an existing installed model. On this computer the app
  automatically prefers `ornith:9b`; other installs may use pre-existing
  `qwen3.5:4b` or `llama3.2:3b`. Override with `CHESSGRIND_CHAT_MODEL`.
  No models are downloaded and nothing is sent to a hosted LLM.
- Stockfish still selects every chess move and independently grades the user's
  moves at limited search depth. Its saved assessment is cached for the live
  match and given to the language model as evidence, with an illustrative
  short principal variation from the **previous** board position.
- The selected coach/rival sees current FEN, whose turn it is, recent SAN moves,
  king squares, material difference, vulnerable undefended pieces and the true
  result. The prompt distinguishes previous-move grades from any next-move
  suggestion and discourages unsupported claims about threats or outcomes.
- Responses are generated asynchronously so a longer LLM answer does not
  block the board. A thinking bubble is replaced by an actual response.
  A local, authored fallback remains when Ollama is unavailable. A message
  field carries recent on-screen dialogue into each new model request.
- The existing text-to-speech toggle, Listen and Stop buttons remain available.
  On this PC, the local Kokoro neural voice model is already installed.

## Post-game Review fix

- The old review panel was outside the fixed fullscreen game overlay.
  The fix relocates the report into the match-room conversation rail beside
  the chessboard, adds a prominent **Review this game** button after completion,
  and displays an active analysis state while Stockfish works.
- Players can select mistakes and inspect individual moves without leaving the
  game. **Return to conversation** switches back without deleting the report,
  game or voice history. Error messages display within the same report pane.

## Validated

- Local Ollama is reachable and the 9B model generates character dialogue.
- Five built-in coaches responded to the same question with five distinct,
  successfully generated answers. All 27 persona briefs are present.
- Browser: a new MAX game, his locally generated opening response, a real
  e4 move and engine grade, a freeform question with a real generated reply,
  resignation, Review this game, report results and return to chat. No browser
  JavaScript/API errors.
- Browser: an existing locally saved **34-ply** MAX checkmate game was opened
  using a **temporary copy of the user's SQLite database**, not the original.
  Its cached report displayed 17 decisions and 4 flagged study moments inside
  the 420-pixel visible report rail. No saved game was changed.
- The repository retains the real-browser capture
  `marketing/screenshots/32-real-ollama-conversation-and-game-review.png`.

## Limitations

- The local language model may still misinterpret positions; only Stockfish
  decisions/grades are authoritative. This is not a certified chess analysis
  model and does not provide guaranteed chess-correct commentary.
- Live engine assessments are shallow and cached for the current process;
  restarting the app can lose the most recent in-memory grade, while saved
  full-game reviews remain in SQLite.
- A cold 9B model can take several seconds to load; speech occurs only after
  the response is ready. We do not promise instantaneous answers.
- Coach conversations persist in this browser's local storage per game and
  pass recent turns to Ollama. This is short conversation context, not a
  lifelong adaptive player model.
