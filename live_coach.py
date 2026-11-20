"""Chess evidence-based, personality-aware real-time move feedback.

Engine labels are local depth-limited *estimates*, never claims of proof or
certified human performance. Coaching selects nonrepetitive, short comments
from evaluated decisions rather than narrating every single turn.
"""
from __future__ import annotations
import hashlib,random,collections,threading
import chess,chess.engine
from arena_personas import coaches,active_coach
from game_analysis import find_engine

_RECENT=collections.defaultdict(lambda:collections.deque(maxlen=8))
_LOCK=threading.Lock()
LINES={
 "supportive":{
   "best":["That's one of Stockfish's top choices, {move}. Nicely judged.","{move} matches the engine's first choice. Keep that idea.","That was accurate: {move}. You spotted the important resource."],
   "strong":["{move} holds up well against the engine. Good decision.","You kept the position healthy with {move}.","{move} is a sensible choice; no meaningful evaluation swing."],
   "inaccuracy":["A small opportunity slipped after {move}. Compare it with {best}.","{move} is playable, but {best} was more precise.","A slight improvement was there: {best} rather than {move}."],
   "mistake":["That cost you something: {move}. Consider why {best} is safer.","After {move}, your position worsened. Look at {best} and the reply.","This is worth replaying: {best} was a stronger option than {move}."],
   "blunder":["That's a significant evaluation drop after {move}. We need to inspect it.","Hold on: {move} gives away a big advantage. {best} was the engine's choice.","That's one to revisit. {move} changed the evaluation sharply; investigate {best}."]
 },
 "challenging":{
   "best":["{move}. Correct, and the engine agrees.","Good. {move} was the strongest engine choice.","You calculated {move}. Now keep that standard."],
   "strong":["{move} is sound. What was your opponent threatening?","No serious error with {move}. Keep calculating.","{move} works. Don't get complacent."],
   "inaccuracy":["You missed some precision. Why {move} instead of {best}?","{move} costs a little. Compare concrete replies to {best}.","An avoidable concession: {best} was cleaner."],
   "mistake":["Stop. {move} isn't good enough here. Calculate {best}.","What's your opponent's best reply to {move}? The engine prefers {best}.","{move} gave away ground. Find the concrete reason before continuing."],
   "blunder":["Blunder alert. {move} swings the evaluation. What did you miss?","Big tactical or positional loss. Compare {move} to {best}.","That was costly. Reconstruct the threat you failed to see."]
 },
 "analytical":{
   "best":["{move} is the top-ranked move at this search depth.","Stockfish selects {move} as its first choice.","{move}: matches the current principal variation."],
   "strong":["{move}: evaluation remains close to optimal.","The engine finds little difference between {move} and its top move.","{move} is objectively competitive at this depth."],
   "inaccuracy":["{move}: minor evaluation loss. Top choice: {best}.","The assessment shifts slightly after {move}; examine {best}.","The alternatives favor {best}, but {move} isn't a blunder."],
   "mistake":["A meaningful evaluation loss follows {move}. Compare {best}.","At this depth, {move} gives away more than a pawn's worth of evaluation.","Stockfish ranks {best} well above {move}. Analyze the forcing reply."],
   "blunder":["Large evaluation loss: {move}. Top choice was {best}.","That is a major swing. Calculate replies to {move} and {best}.","Engine verdict: blunder. The position changes sharply after {move}."]
 },
 "playful":{
   "best":["Oho, {move}! Stockfish likes that one too.","{move} — sharp eye! That's top of the list.","That's a tasty move. {move} is the engine's favorite."],
   "strong":["{move} keeps your position humming.","No chessboard disasters from {move}. Nice.","{move} is sturdy. The pieces approve."],
   "inaccuracy":["A tiny wobble with {move}; {best} was tidier.","{move} leaves a crumb on the table. Try {best}.","One little missed chance. {best} was the sharper play."],
   "mistake":["Ouch, the board just bit back after {move}. Compare {best}.","That's a trapdoor under {move}. What did the other side gain?","{move} makes life hard. {best} was the escape route."],
   "blunder":["Yikes — {move} is a real gift to your opponent.","That one came with a warning label. Investigate {best}.","The evaluation just fell down the stairs after {move}. Let's inspect."]
 },
 "calm":{
   "best":["{move} is exactly what the engine prefers.","Well seen. {move} is the leading choice.","That move was right on target."],
   "strong":["{move} keeps things under control.","The position remains sound after {move}.","A steady move. {move} is fine here."],
   "inaccuracy":["A small detail matters here: {best} was better.","{move} gives away a little; look at {best}.","Let's compare {move} and {best} without rushing."],
   "mistake":["That decision deserves another look. {best} was stronger.","After {move}, the evaluation drops. Find the threat.","There was a better defensive idea: {best}."],
   "blunder":["That changes the position significantly. Let's examine the reply.","A serious oversight after {move}. We can learn from it.","The engine sees a major problem with {move}. Look carefully at {best}."]
 }
}
REMINDERS={
 "safety":["Count attackers and defenders before leaving a piece.","Check whether your last move left something undefended.","After every move, scan your loose pieces."],
 "calculation":["Look at forcing checks, captures and threats before quiet moves.","Calculate your opponent's strongest reply, not the reply you hope for.","Name two candidate moves and calculate one move deeper."],
 "opening":["Develop a piece with purpose, contest the center, and guard your king.","Before another pawn move, count your undeveloped pieces.","Make sure your king safety keeps pace with your development."],
 "endgame":["Bring your king into the game and count pawn tempos.","Check whether your pawn is passed, protected, or blockaded.","King activity and opposition often outweigh pretty piece placement."]
}

QUIRK_REMINDERS={
 "threats":["Before you commit, name your opponent's strongest threat.",
            "Give the other side a move. What can they force?"],
 "candidates":["Choose two candidates and calculate the replies to both.",
               "What was your second candidate move? Compare concrete lines."],
 "piece-safety":["Count attackers and defenders of every loose piece.",
                 "Which piece is left without adequate protection?"],
 "king-safety":["Where are the forcing checks against your king?",
                "Check whether either king is exposed before calculating a combination."],
 "pawn-structure":["Identify the pawn weaknesses this move leaves behind.",
                   "Think about pawn breaks and permanent weak squares."],
 "endgame":["Count king tempos. Can your king improve first?",
             "In the endgame, calculate the pawn race before moving."],
 "quiet":["Check the threat and calculate your reply.", "Remember the last blunder."]
}

def _topic(board,move):
    if board.fullmove_number<=10:return "opening"
    if board.fullmove_number>=40 or sum(1 for x in board.piece_map().values() if x.piece_type==chess.QUEEN)==0:return "endgame"
    if board.is_capture(move) or board.gives_check(move):return "calculation"
    return "safety"

def grade(board,move,game_id,ply):
    """Evaluate the player's chosen legal move against the best move at depth 9."""
    if move not in board.legal_moves:raise ValueError("Move isn't legal")
    path=find_engine()
    if not path:return None
    perspective=board.turn
    played=board.san(move)
    try:
        with chess.engine.SimpleEngine.popen_uci(path,timeout=20) as eng:
            first=eng.analyse(board,chess.engine.Limit(depth=9))
            best=first.get("pv",[move])[0]
            preferred=board.san(best)
            score=first["score"].pov(perspective).score(mate_score=20000)
            chosen=first if move==best else eng.analyse(
                board,chess.engine.Limit(depth=9),root_moves=[move])
            actual=chosen["score"].pov(perspective).score(mate_score=20000)
    except (chess.engine.EngineError,chess.engine.EngineTerminatedError,OSError,ValueError,KeyError):
        return None
    if score is None or actual is None:return None
    loss=max(0,score-actual)
    if best==move:category="best"
    elif loss<=45:category="strong"
    elif loss<=115:category="inaccuracy"
    elif loss<=260:category="mistake"
    else:category="blunder"
    topic=_topic(board,move)
    with _LOCK:
        queue=_RECENT[game_id]
        prior=sum(1 for x in queue if x in ("mistake","blunder"))
        queue.append(category)
    repeated=category in ("mistake","blunder") and prior>=2
    who=next((c for c in coaches() if c["id"]==active_coach()),None)
    tone=(who or {}).get("tone","supportive")
    if tone not in LINES:tone="supportive"
    identifier=int(hashlib.sha256((game_id+str(ply)+played+tone+(who or {}).get("id","")).encode()).hexdigest()[:8],16)
    phrase=LINES[tone][category][identifier%len(LINES[tone][category])]
    comment=phrase.format(move=played,best=preferred)
    if repeated or category=="blunder":
        quirk=(who or {}).get("quirk","threats")
        possibilities=QUIRK_REMINDERS.get(quirk,QUIRK_REMINDERS["threats"])
        note=possibilities[(identifier//3)%len(possibilities)]
        comment+=" "+note
    elif category=="mistake" and (identifier%3)==0:
        comment+=" "+REMINDERS[topic][identifier%len(REMINDERS[topic])]
    # No repetitive commentary on every decent move; always interrupt for real mistakes.
    speak=category in ("mistake","blunder") or repeated or (category=="best" and ply%8==1)
    show=category in ("best","mistake","blunder") or (category=="inaccuracy" and ply%4==1) or repeated
    return {"category":category,"yourSan":played,"bestSan":preferred,
            "lossCp":loss,"depth":9,"topic":topic,"struggling":repeated,
            "message":comment if show else None,"speak":bool(speak and show),
            "coach":(who or {}).get("name","Coach"),
            "scope":"Shallow, time-limited engine assessment. Not a proof of a forced outcome."}
