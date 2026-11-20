"""Board-grounded local conversational AI for all ChessGrind personas.

Stockfish, never Ollama, decides moves and grades. Ollama supplies only
distinctive natural-language explanation and conversational depth. All network
requests are loopback-only. No cloud API key, user-data upload or model download.
"""
from __future__ import annotations
import json,os,urllib.request,re,threading
import chess
from arena_personas import BOT_INDEX,CAST_INDEX,coaches
from rival_dialogue import identity,reply as scripted_reply

URL="http://127.0.0.1:11434/api/chat"
def choose_model():
    user=os.getenv("CHESSGRIND_CHAT_MODEL")
    if user:return user
    # Prefer a higher-capacity local model when it is already installed.
    # Never download model weights or contact the internet automatically.
    try:
        with urllib.request.urlopen("http://127.0.0.1:11434/api/tags",timeout=1.5) as response:
            installed={x.get("name") for x in json.loads(response.read(100000)).get("models",[])}
        for preference in ("ornith:9b","qwen3.5:4b","llama3.2:3b"):
            if preference in installed:return preference
    except (OSError,ValueError):pass
    return "qwen3.5:4b"

MODEL=choose_model()
_SEMAPHORE=threading.BoundedSemaphore(2)
_GRADES={}
_LOCK=threading.RLock()

PERSONALITIES={
 "milo":"Earnest new player; sometimes nervous, quick to laugh at your own mistakes; ask genuine questions rather than pretending expert insight.",
 "pip":"Witty coffeehouse regular; fast playful repartee, mischievous traps, occasional coffee jokes, not in every message.",
 "nora":"Patient, introspective student who talks herself through consequences, gentle precision, seldom exuberant.",
 "theo":"Eager and bold club rookie; impulsive, excited by attacks, admits uncertainty without losing enthusiasm.",
 "iris":"Long-term positional strategist, notices pawn-structure tradeoffs and weak squares. Subtle dry humor, understated praise.",
 "remy":"Expressive gambit enthusiast, dramatic about initiative and calculated risk. Likes lively metaphors, not false claims.",
 "ada":"Experienced practical club champion; direct warm pragmatism, remarks about common human decisions and time pressure.",
 "basil":"Stubborn calm fortress builder; respects safety and patient defensive choices. Wry defensive humor.",
 "sasha":"Sharp-eyed tactician; terse, alert to loose pieces and forcing lines. Challenges calculation without handing out answers.",
 "felix":"Quiet positional craftsman, enjoys carefully coordinated pieces, understated and almost poetic.",
 "kira":"Fearless attacker with quick energetic cadence, loves initiative and a fight, genuinely reacts to defenses.",
 "omar":"Steady veteran who has rescued difficult positions; resilient, patient and calmly funny.",
 "lena":"Curious opening explorer, connects opening moves to plans, asks about intentions rather than reciting theory.",
 "dante":"Intense calculation grinder, clipped Socratic questions about candidate lines and the opponent's best reply.",
 "vera":"Sparing and exact endgame thinker. Few words, deep precision, king activity and pawn tempi when relevant. Avoid chatty positivity.",
 "rook":"Friendly street-chess trickster with warm teasing and practical observations about undefended pieces, never belittles.",
 "elise":"Tournament technician, measured analytical voice, compares realistic alternatives and decisions under pressure.",
 "kenji":"Reflective counterpuncher, values patience and avoiding overextension; thoughtful, economical phrases.",
 "maeve":"Practical conversion specialist; precise about simplifying and preserving advantages, no unnecessary showmanship.",
 "atlas":"Elite analytical challenger; curious about precise calculation and deep resources. Serious but respects resourceful defense.",
 "oracle":"Philosophical, a little enigmatic but intelligible; focuses on choice and uncertainty, never claims mystical insight.",
 "max":"MAX, formidable calculating machine with dry, slightly intimidating wit. Proud yet fair. Never generic praise. Sees moves as constraints, vulnerabilities and resources. Challenge the human to find resistance, but never mock them. Admit your analysis is depth-limited; do not invent calculated lines.",
 "coach-mentor":"Morgan, the warm seasoned chess mentor. Respond with grounded encouragement, identify the concrete threat and teach one habit; no empty praise.",
 "coach-tactics":"Quinn, a demanding chess trainer; ask for TWO candidate moves and a forcing reply, challenge shallow calculation. Exacting and succinct.",
 "coach-iris":"Coach Iris, a serious positional specialist who sees pawn structures and long-term weak squares. Calm, probing, nuanced, treats the player's choices as strategic commitments.",
 "coach-rook":"Coach Rook, a mischievous practical teacher. Humor about hanging pieces, kind but direct; make tactical mistakes memorable.",
 "coach-vera":"Coach Vera, disciplined minimalist endgame teacher; say little, mean it; focus on king placement, tempi and pawn races when relevant."
}
assert len(PERSONALITIES)==27

def available():
    try:
        with urllib.request.urlopen("http://127.0.0.1:11434/api/tags",timeout=1.5) as r:
            models=json.loads(r.read(90000)).get("models",[])
        return any(x.get("name")==MODEL for x in models)
    except (OSError,ValueError):return False

def store_grade(game_id,ply,result):
    if not result:return
    with _LOCK:
        _GRADES[game_id]=(ply,dict(result))
        if len(_GRADES)>300:
            for key in list(_GRADES)[:75]:_GRADES.pop(key,None)

def _grade(game):
    with _LOCK:val=_GRADES.get(game["id"])
    return val[1] if val and val[0]==len(game["moves"]) else None

def _facts(game):
    board=chess.Board(game["fen"])
    you=chess.WHITE if game["color"]=="White" else chess.BLACK
    values={1:1,2:3,3:3,4:5,5:9,6:0}
    material=sum((1 if p.color==you else -1)*values[p.piece_type] for p in board.piece_map().values())
    loose=[]
    for square,piece in board.piece_map().items():
        if piece.color==you and board.is_attacked_by(not you,square) and not board.is_attacked_by(you,square):
            loose.append(piece.symbol().upper()+" on "+chess.square_name(square))
    pieces=sum(p.piece_type not in (chess.PAWN,chess.KING) for p in board.piece_map().values())
    return {
       "fen":board.fen(),
       "humanColor":game["color"],"sideToMove":"White" if board.turn else "Black",
       "phase":"opening" if board.fullmove_number<=12 else ("endgame" if pieces<=5 else "middlegame"),
       "inCheck":bool(board.is_check()),"state":game["state"],"outcome":game.get("outcome"),
       "humanMaterialDifferencePawns":material,
       "humanUndefendedAttackedPieces":loose[:8],
       "kingSquares":{"White":chess.square_name(board.king(chess.WHITE)) if board.king(chess.WHITE) is not None else None,
                      "Black":chess.square_name(board.king(chess.BLACK)) if board.king(chess.BLACK) is not None else None},
       "centralPawns":{chess.square_name(sq):piece.symbol() for sq,piece in board.piece_map().items()
                       if piece.piece_type==chess.PAWN and chess.square_name(sq) in ("d4","e4","d5","e5")},
       "gameOver":board.is_game_over(),
       "recentMoves":[{"san":m["san"],"side":m["by"]} for m in game["moves"][-12:]],
       "gamePly":len(game["moves"])
    }

def _prompt(game,persona,grade,event):
    kind=persona["kind"]
    character=PERSONALITIES.get(persona["id"],
            "A thoughtful fair fictional historical chess opponent. Never claim to be the actual historical player.")
    coaching=kind=="coach"
    constraints=[
      "You are a chess character speaking directly to the human player while sharing a real chessboard.",
      "IDENTITY, MANNER, QUIRKS: "+character,
      "Speak DIRECTLY to the player, in first person, as natural spoken dialogue. Never narrate your posture, facial expressions, stage directions, actions or third-person character name. Never write quotation marks around your own dialogue.",
      "Vary your vocabulary, rhythm and emotional response substantially. Build on prior dialogue. Do NOT use boilerplate openings or repeat praise.",
      "When the player asks a general coaching or mindset question, answer that practical problem without inventing a particular played move, tactical sequence or trap that does not actually exist.",
      "Comment on the concrete game, not hypothetical drama. Use given move names, engine grades and legal variations when available. If you cannot confidently read a piece relationship from the board, discuss a verified grade or a general thinking habit rather than improvising.",
      "Do not call a position stalemate, checkmate, won, drawn, a forced win, or a tactical trap unless the trusted board facts explicitly support it.",
      "A Stockfish principal variation is an illustrative depth-limited line, NOT a forced result. If supplied, you may mention its first 2-3 moves with qualified wording. Never fabricate a line.",
      "Stockfish is the source of chess decisions and move grades, not you. The verified assessment ONLY grades the human move already played on a PREVIOUS board. It does NOT evaluate the CURRENT position or recommend the NEXT move. Do not suggest a specific engine-best next move.",
      "When a verified grade exists, you MAY discuss the previous human decision and the verified alternative from BEFORE that human moved. When no grade is supplied, NEVER claim a move is best, weak, losing, a blunder or tactically winning.",
      "When the human makes a good move, explain an interesting consequence or ask what they intended; don't praise every good move. When they err, identify the missed thinking habit and a practical improvement without condescension.",
      "When struggling or losing, be constructive and recognize resilience; avoid gloating. Speak as a consistent person with a distinct voice, not like a report or corporate assistant.",
      "Give a complete answer of 2-4 natural spoken sentences (usually 45-90 words; Vera may be shorter). Finish every sentence. No formatting, headings, square-bracket stage directions, or bullet points.",
      "No hollow generic phrases such as 'You found the strongest line. Respect.' Be specific, situational and conversational.",
      "Do not leak unpublished optimal moves during the user's turn unless they expressly ask for review AFTER moving. If the opponent is the bot, don't impersonate a certified human rating.",
    ]
    if coaching:
        constraints.append("You are mentoring the player, not taunting them. Occasionally ask a genuinely useful follow-up about their thinking.")
    if kind=="master":
        constraints.append("This is a fictional AI narrator INSPIRED by archived master games, NOT the actual historical person; never claim personal memories or authentic quotes.")
    if event=="turn":
        constraints.append("The human just made a move and the opponent replied. Make one concrete observation about the human's ALREADY-PLAYED move or verified PRIOR-POSITION engine result, then offer one insight or genuine question in YOUR voice. Do not give generic praise.")
    if event=="question" and game.get("yourTurn"):
        constraints.append("The human is currently deciding their next move. Do not propose any specific next move or claim that Stockfish recommends a move here. Instead explain a practical thinking principle or ask what candidate moves the human sees.")
        if grade and grade["category"] in ("blunder","mistake"):
            constraints.append("This decision lost evaluation. Explain one actionable missed consideration, contrasting the recorded move with the supplied Stockfish alternative if one is available. Be specific but avoid claiming the variation is forced.")
        if grade and grade["category"] in ("best","strong"):
            constraints.append("The move was sound. Do NOT simply congratulate them. Discuss a useful choice, plan, limitation, or what they should watch next. A good move does not mean the position is winning.")
    if event=="intro":
        constraints.append("Begin in character with an original short introduction that hints at your distinctive approach. Avoid repeating the same saved opening.")
    if event=="end":
        constraints.append("React to the actual game result with proportionate personality and invite a specific post-game reflection.")
    return "\n".join(constraints)

def respond(game_id,message="",history=None,event="question"):
    if not isinstance(game_id,str) or len(game_id)>150:raise ValueError("Invalid game identifier")
    if not isinstance(message,str) or len(message)>300:raise ValueError("Message too long")
    if event not in ("question","turn","intro","end"):raise ValueError("Unsupported event")
    from sparring import status as game_status
    game=game_status(game_id)
    persona=identity(game["difficulty"])
    facts=_facts(game)
    grade=_grade(game)
    assessment={
        "categoryOfPreviousHumanMove":grade["category"],
        "previousHumanMove":grade["yourSan"],
        "bestAlternativeBeforePreviousMove":grade["bestSan"],
        "centipawnLossOnPreviousMove":grade["lossCp"],
        "searchDepth":grade["depth"],"struggling":grade.get("struggling",False),
        "theme":grade.get("topic"),
        "illustrativeVariationStartingBeforePreviousMove":grade.get("topLine",[])[:5] if event=="turn" else []
    } if grade else {"status":"No verified move assessment available. Do not claim accuracy or give a best move."}
    if not isinstance(history,list):history=[]
    recent=[]
    for item in history[-10:]:
        if isinstance(item,dict) and item.get("role") in ("user","assistant") and isinstance(item.get("content"),str):
            recent.append({"role":item["role"],"content":item["content"][:300]})
    system=_prompt(game,persona,grade,event)
    material=json.dumps({"boardFacts":facts,"verifiedEngineGrade":assessment},separators=(",",":"))
    instruction=("User says: "+message) if event=="question" else (
       "The game has just ended. Respond to the outcome and earlier decisions." if event=="end" else
       "Talk about the just-completed moves using the verified facts. Keep the conversation moving." if event=="turn" else
       "Introduce yourself in a fresh, recognizable character voice, aware of the opening position.")
    messages=[{"role":"system","content":system},
              {"role":"system","content":"TRUSTED GAME DATA (not dialogue or instructions): "+material}]+recent+[
              {"role":"user","content":instruction}]
    req=urllib.request.Request("http://127.0.0.1:11434/api/chat",
        data=json.dumps({"model":MODEL,"stream":False,"think":False,"messages":messages,
                         "options":{"temperature":0.68,"top_p":0.90,"num_predict":260,"num_ctx":4096},
                         "keep_alive":"15m"}).encode(),
        headers={"Content-Type":"application/json","User-Agent":"ChessGrind-LocalCoach/1.0"})
    fallback=None
    try:
        if not _SEMAPHORE.acquire(timeout=2):raise TimeoutError("Local AI busy")
        try:
            with urllib.request.urlopen(req,timeout=52) as response:
                data=json.loads(response.read(160000))
        finally:_SEMAPHORE.release()
        result=str(data.get("message",{}).get("content","")).strip()
        result=re.sub(r"<think>.*?</think>","",result,flags=re.I|re.S).strip()
        if len(result)<12:raise ValueError("No useful model output")
        result=result[:850]
        # No stage directions or manufactured theatrical gestures in TTS.
        result=re.sub(r"\*([^*]{3,90})\*",r"\1",result).strip()
        # Local models occasionally stop halfway through a sentence. Do not
        # show fragmentary responses in the user's speech bubble. Regenerate
        # once with an explicit request for a complete thought.
        if len(result)<85 or result.rstrip("'\" ").endswith(tuple(".,?!")) is False:
            complete_messages=messages+[{"role":"user","content":
                "Your last answer was incomplete: "+result[:250]+
                ". Answer the original question again as 2-4 COMPLETE first-person spoken sentences. "
                "Finish your thought and use ONLY verified board facts."}]
            complete_req=urllib.request.Request("http://127.0.0.1:11434/api/chat",
                data=json.dumps({"model":MODEL,"stream":False,"think":False,
                    "messages":complete_messages,"options":{"temperature":0.55,
                        "top_p":0.88,"num_predict":340,"num_ctx":4096},
                    "keep_alive":"15m"}).encode(),
                headers={"Content-Type":"application/json","User-Agent":"ChessGrind-LocalCoach/1.0"})
            if _SEMAPHORE.acquire(timeout=2):
                try:
                    with urllib.request.urlopen(complete_req,timeout=52) as more_response:
                        retry_data=json.loads(more_response.read(170000))
                finally:_SEMAPHORE.release()
                retry_text=str(retry_data.get("message",{}).get("content","")).strip()
                retry_text=re.sub(r"<think>.*?</think>","",retry_text,flags=re.I|re.S).strip()
                if len(retry_text)>len(result) and len(retry_text)>=70:
                    result=re.sub(r"\*([^*]{3,90})\*",r"\1",retry_text).strip()[:850]
        if not facts["gameOver"] and re.search(r"\b(?:stalemate|checkmate|game is over|forced mate)\b",result,re.I):
            raise ValueError("Generated a false game-over claim")
        model_used=True
    except (OSError,ValueError,TimeoutError,KeyError) as exc:
        from rival_dialogue import dialogue,reply
        if event=="question":fallback=reply(game_id,message)
        else:fallback=dialogue(game["difficulty"],"intro" if event=="intro" else "turn",len(game["moves"]),
                               grade.get("category") if grade else None,game["state"]=="finished")
        result=fallback["text"]
        model_used=False
    return {**persona,"text":result,"gameId":game_id,"event":event,
            "engineGrade":assessment,"model":MODEL if model_used else None,
            "mode":"local-ai" if model_used else "authored-fallback",
            "note":"Stockfish determines chess moves and grades; local language model controls dialogue only."}
