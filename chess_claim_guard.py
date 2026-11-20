"""Deterministic chess-claim guard for locally generated coach conversations.

Only a narrow, auditable set of concrete claims is certified. Unknown
claims are flagged or left unverified, never magically proved by an LLM.
The chess rules, a recorded prior-move evaluation, and optional engine
variation are the evidence sources. All output is safe plain text.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, asdict

import chess

PIECE = {
    "pawn": chess.PAWN, "knight": chess.KNIGHT, "bishop": chess.BISHOP,
    "rook": chess.ROOK, "queen": chess.QUEEN, "king": chess.KING,
}
SAN_WORD = re.compile(r"(?<![A-Za-z0-9])(?:[KQRBN](?:[a-h]?[1-8]?x?)?[a-h][1-8](?:=[QRBN])?[+#]?|[a-h](?:x[a-h])?[1-8](?:=[QRBN])?[+#]?|O-O(?:-O)?[+#]?)(?![A-Za-z0-9])")
SQUARE = re.compile(r"\b([a-h][1-8])\b")
PIECE_SQUARE = re.compile(
    r"\b(?:(your|my|white|black)\s+)?(pawn|knight|bishop|rook|queen|king)\s+(?:on|at)\s+([a-h][1-8])\b",
    re.I,
)
UNSUPPORTED_MATE = re.compile(r"\b(?:mate\s+in\s+\d+|forced\s+(?:mate|checkmate)|guaranteed\s+(?:mate|win))\b",re.I)
GAME_END = re.compile(r"\b(?:checkmate|stalemate|game\s+over|you\s+(?:won|lost)\s+the\s+game)\b",re.I)
UNSAFE_ENGINE = re.compile(r"\b(?:stockfish|the\s+engine)\s+(?:says|confirms|recommends|prefers|found|chooses)\b",re.I)
SCORE = re.compile(r"\b(?:you|i|white|black)\s+(?:are|am|is)\s+(?:clearly\s+)?(?:winning|lost|losing|ahead\s+by\s+\d+\s+pawns?)\b",re.I)
LIVE_SUGGESTION = re.compile(r"\b(?:best\s+move\s+is|play\s+|you\s+should\s+play\s+|engine\s+recommends\s+)\s*([KQRBN]?[a-h][1-8]|O-O(?:-O)?)",re.I)
CHECK_CLAIM = re.compile(r"\b(?:you(?:r\s+king)?|my\s+king|white|black)\s+(?:are|is|am)\s+in\s+check\b",re.I)
EMPTY_BOARD = re.compile(
    r"\b(?:the|this|your|our)?\s*board\s+(?:is|was|looks|that\s+is)\s+(?:entirely\s+|completely\s+|totally\s+)?empty\b|\bno\s+pieces\s+(?:on|left\s+on)\s+(?:the|this)\s+board\b",re.I)
ADJACENT_KINGS = re.compile(
    r"\b(?:kings?|both\s+kings)\b.{0,38}\b(?:side\s+by\s+side|adjacent|next\s+to\s+each\s+other|touching)\b",re.I)


@dataclass(frozen=True)
class Finding:
    code: str
    message: str
    severity: str = "block"

def inspect(text,board,*,human_color,game_finished=False,grade=None,previous_fen=None):
    if not isinstance(text,str) or len(text)>1200:
        return [Finding("bad_text","Response is empty or too long.")]
    if not board.is_valid():
        return [Finding("invalid_board","The position is invalid.")]
    findings=[]
    if EMPTY_BOARD.search(text) and board.piece_map():
        findings.append(Finding("false_empty_board",
                                "The board contains "+str(len(board.piece_map()))+" pieces."))
    if UNSUPPORTED_MATE.search(text):
        findings.append(Finding("unproven_mate","No complete mate proof was supplied."))
    # A legal chess position can never have two touching kings. The local
    # model did hallucinate "your kings side by side" at the start board.
    if ADJACENT_KINGS.search(text):
        white,black=board.king(chess.WHITE),board.king(chess.BLACK)
        if white is None or black is None or chess.square_distance(white,black)>1:
            findings.append(Finding("false_king_geometry",
                                    "The kings are not adjacent in this position."))

    # 'Checkmate' in a question or generic lesson isn't an actual claim;
    # reject explicit status declarations when the game has not ended.
    if not game_finished and not board.is_checkmate() and re.search(
        r"\b(?:this\s+is\s+checkmate|it's\s+checkmate|that\s+is\s+mate|the\s+game\s+is\s+over|you\s+are\s+checkmated)\b",
        text,re.I):
        findings.append(Finding("false_termination","The board does not show a finished game."))
    if re.search(r"\b(?:this\s+is\s+stalemate|it's\s+stalemate)\b",text,re.I) and not board.is_stalemate():
        findings.append(Finding("false_stalemate","The board is not stalemate."))
    # A false 'king in check' is reliably testable against python-chess.
    for matched in CHECK_CLAIM.finditer(text):
        label=matched.group(0).lower()
        if label.startswith("white"):target=chess.WHITE
        elif label.startswith("black"):target=chess.BLACK
        elif label.startswith("my"):target=(human_color=="Black")
        else:target=(human_color=="White")
        if not board.is_check() or board.turn!=target:
            findings.append(Finding("false_check","The named player's king is not in check."))
    # Unjustified winning evaluations are particularly harmful to learners.
    # A grade for a previous human move cannot prove the current position
    # is objectively winning. Require explicit position evaluation, which
    # the live conversational model is intentionally not given.
    if SCORE.search(text):
        findings.append(Finding("unverified_evaluation","No independently verified CURRENT position result supports this evaluation."))
    if UNSAFE_ENGINE.search(text):
        if not grade or not (grade.get("categoryOfPreviousHumanMove") or grade.get("category")):
            findings.append(Finding("attributed_to_engine","No relevant engine assessment was provided."))
        elif re.search(r"\b(?:now|next|here|in this position)\b",text,re.I):
            findings.append(Finding("stale_engine_claim","Previous-move analysis is not a current-position recommendation."))
    # Literal assertions about pieces at squares can be verified geometrically.
    for match in PIECE_SQUARE.finditer(text):
        side,kind,sq=match.groups()
        piece=board.piece_at(chess.parse_square(sq))
        color={"white":chess.WHITE,"black":chess.BLACK,
               "your":human_color=="White","my":human_color=="Black"}.get((side or "").lower())
        if piece is None or piece.piece_type!=PIECE[kind.lower()] or (color is not None and piece.color!=color):
            findings.append(Finding("false_piece_square","No matching "+kind.lower()+" occupies "+sq+"."))
    # A legal move named in a past variation is not a recommendation for the
    # current board. Restrict *explicit instructions* to play SAN during live
    # competition. Legal moves may be taught after the game ends.
    if not game_finished and LIVE_SUGGESTION.search(text):
        findings.append(Finding("live_best_move","A rival should not reveal specific best moves during play."))
    # Previous move names are only certified by the previous board, not by
    # current FEN. Don't mark all SAN-like text as legal in the current board.
    # When an explicit 'now play X' occurs, require that X be legal.
    if game_finished:
        m=LIVE_SUGGESTION.search(text)
        if m:
            san=m.group(1)
            try:board.parse_san(san)
            except ValueError:
                # Avoid blocking historical variations described from other
                # boards unless sentence explicitly anchors 'right now'.
                if re.search(r"\b(?:right\s+now|in\s+this\s+position)\b",text,re.I):
                    findings.append(Finding("illegal_current_move","Suggested move is illegal here."))
    # Deduplicate without masking severity.
    return list(dict.fromkeys(findings))

def validate(text,board,**kw):
    failures=inspect(text,board,**kw)
    return {"ok":not any(x.severity=="block" for x in failures),
            "findings":[asdict(x) for x in failures],
            "checker":"board-rules-v1",
            "coverage":"selected mechanically-checkable claims only; does not certify arbitrary chess explanations"}

def safe_fallback(*,persona,event,grade,board,finished=False):
    name=persona.get("name","Your opponent")
    key=persona.get("id","")
    short=key.endswith("vera") or key=="vera"
    if finished:
        outcome=board.outcome(claim_draw=True)
        if outcome and outcome.termination==chess.Termination.CHECKMATE:
            text="That's checkmate. Let's go back to the decision that led here."
        elif outcome and outcome.winner is None:
            text="The position is drawn. Let's examine the decisions that mattered."
        else:
            text="Our game is finished. Let's review the key decisions rather than guess what might have worked."
    elif grade and grade.get("categoryOfPreviousHumanMove") in ("blunder","mistake","inaccuracy"):
        category=grade["categoryOfPreviousHumanMove"]
        san=grade.get("previousHumanMove","your last move")
        text=("Your move "+san+" was a "+category+" in the recorded depth-limited analysis. "+
              "Can you identify your opponent's strongest reply before we look at alternatives?")
    elif grade and grade.get("categoryOfPreviousHumanMove") in ("best","strong"):
        text="That previous move held up in the engine check. What do you think it changed about the position?"
    elif board.is_check():
        text="The side to move is in check. Start by looking at every legal way to get out of check."
    elif short:
        text="Count the forcing moves. Then decide."
    else:
        text="Look at the checks, captures and threats for both players. Which piece is doing the least work?"
    return text
