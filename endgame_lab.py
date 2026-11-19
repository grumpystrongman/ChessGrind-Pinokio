"""Endgame laboratory: small, verified positions and local engine feedback.

Without locally installed Syzygy files, the lab never claims exact WDL/DTZ.
Authored teaching themes are geometric/strategic cues; game-tree continuation
and move comparison come from Stockfish at limited depth.
"""
from __future__ import annotations
import datetime as dt
import os,re
import chess,chess.engine
from chess_grind import db
from game_analysis import find_engine
from engine_grade import engine_gap
from lesson_explainer import move_reasons,variation

def position(pieces,color="w"):
 board=chess.Board(None)
 for sq,symbol in pieces.items():
  board.set_piece_at(chess.parse_square(sq),chess.Piece.from_symbol(symbol))
 board.turn=color=="w";board.castling_rights=0;board.fullmove_number=40
 if not board.is_valid():raise ValueError("Illegal endgame scenario: "+str(pieces))
 return board.fen()

LESSONS=[
 {"id":"opposition","title":"The opposition","category":"King and pawn",
  "subtitle":"Whose turn is it—and which king must step aside?",
  "principle":"Kings facing one another with a single empty square between them are in direct opposition. The turn to move matters, but pawn moves can change the result.",
  "hint":"The kings face each other along the e-file. Find a legal move that keeps your king useful, then compare the reply.",
  "fen":position({"e4":"K","e3":"P","e6":"k"},"b"),
  "focus":["e4","e5","e6"],"idea":"Notice the opposing kings on e4 and e6, with e5 between them. Don't infer the winning side from opposition alone."},
 {"id":"promotion-race","title":"The promotion race","category":"Pawn endgames",
  "subtitle":"Count the tempo to promotion before choosing.",
  "principle":"A passed pawn can create a promotion threat. Count its remaining steps and the opponent king's distance. A pawn can be passed yet still be captured.",
  "hint":"The white pawn on a6 is two advances away from promotion. Which squares must it cross?",
  "fen":position({"g1":"K","a6":"P","h8":"k"},"w"),
  "focus":["a6","a7","a8"],"idea":"The a-pawn has no opposing pawns in its way. Counting its moves is a start; test whether Black's king can interfere."},
 {"id":"rook-activity","title":"Rook behind the passer","category":"Rook endgames",
  "subtitle":"Use an active rook to support a passed pawn.",
  "principle":"A rook often supports its own passed pawn effectively from behind, allowing the pawn to advance without cutting off the rook. This is a useful plan, not a universally best move.",
  "hint":"White has a passed a-pawn. Can the rook on e1 find the open a-file behind it?",
  "fen":position({"g2":"K","e1":"R","a5":"P","g8":"k","h7":"r"},"w"),
  "focus":["a5","a1","e1"],"idea":"The pawn on a5 has no enemy pawn ahead of it. The rook on e1 can potentially shift to the a-file to support its advance."},
 {"id":"king-support","title":"Support your passer","category":"Pawn endgames",
  "subtitle":"An active king helps a pawn, but safety still matters.",
  "principle":"In pawn endings the king is a fighting piece. It can help a passed pawn advance and restrict the opponent's king, but every move must respect opposition and pawn tempo.",
  "hint":"Check the distance between the kings and the e-pawn. Which king move improves its influence without allowing a capture?",
  "fen":position({"e4":"K","e5":"P","e7":"k"},"w"),
  "focus":["e4","e5","e6","e7"],"idea":"White's king supports its e-pawn, but Black's king blocks the road. Compare king maneuvers before blindly pushing."},
 {"id":"queen-mate","title":"Coordinate king and queen","category":"Basic checkmates",
  "subtitle":"Look for a forcing, legal checkmate.",
  "principle":"A queen and king together can cover adjacent escape squares. Checkmate requires the king to be in check with no legal escape, capture, or block.",
  "hint":"Black's king sits on h8. Which queen move controls the eighth rank while White's king covers g7 and h7?",
  "fen":position({"g6":"K","d5":"Q","h8":"k"},"w"),
  "focus":["d8","g7","h7","h8"],"idea":"White's king covers g7 and h7. Look for a queen move that checks along the eighth rank and leaves Black no legal escape."},
 {"id":"rook-checks","title":"Active rook checks","category":"Rook endgames",
  "subtitle":"Learn the difference between an active check and a useful check.",
  "principle":"Rooks attack along open ranks and files. A check forces an immediate response, but a check is useful only if the ensuing position helps your plan.",
  "hint":"From a1 the rook can operate along the a-file and the first rank. Which checks are available?",
  "fen":position({"f6":"K","a1":"R","h8":"k"},"w"),
  "focus":["a1","a8","h8"],"idea":"The rook can check along the eighth rank after Ra8+, but calculate Black's legal replies rather than assuming every check is mate."},
]
# Dedicated lessons for both colors. Mirroring swaps piece colors and
# vertically mirrors squares; every mirrored position is separately validated.
_BLACK_EXPLANATIONS={
 "opposition":("Look at the two kings from White's side. Who must yield the file, and what pawn tempi remain?",
               "Direct opposition depends on whose turn it is. The board is the mirrored legal counterpart of the Black-to-move example."),
 "promotion-race":("As Black, count your pawn's advances to promotion and where the white king can intervene.",
                    "Your black pawn is passed. Promotion is not automatic: check the white king's interception path."),
 "rook-activity":("As Black, look for a rook maneuver behind your passed pawn.",
                  "Rooks are often effective behind passers; verify whether a rook maneuver is safe here."),
 "king-support":("As Black, look for ways your king can help the passed pawn.",
                 "Your king and pawn need coordination. Test whether the opposing king can block or capture."),
 "queen-mate":("As Black, coordinate your queen with your king to restrict every legal escape.",
                "A queen and king together can build a mating net. A check is not mate if any legal escape remains."),
 "rook-checks":("As Black, examine checking rook moves and calculate the reply.",
                 "Checking moves force answers, but even a legal check may only trade the initiative.")
}
ORIGINAL_LESSONS=list(LESSONS)
for original in ORIGINAL_LESSONS:
 b=chess.Board(original["fen"]);flipped=b.mirror()
 hint,idea=_BLACK_EXPLANATIONS[original["id"]]
 swapped={
    **original,
    "id":original["id"]+"-mirror",
    "title":original["title"]+" · opposite side",
    "subtitle":"Practice the same concept from the opposite color.",
    "fen":flipped.fen(),
    "focus":[chess.square_name(chess.square_mirror(chess.parse_square(sq)))
             for sq in original["focus"]],
    "hint":hint,"idea":idea
 }
 LESSONS.append(swapped)

# Board-verified practice variations. The same principle is trained on
# different legal arrangements, not repeated on an identical FEN.
def _extra_endgames():
    original=list(LESSONS)
    seen={chess.Board(x["fen"]).board_fen()+(" w" if chess.Board(x["fen"]).turn else " b") for x in original}
    for lesson in original:
        board=chess.Board(lesson["fen"])
        new=0
        for flip in (False,True):
            for dx in (0,1,-1,2,-2,3,-3):
                for dy in (0,1,-1,2,-2):
                    if not flip and dx==0 and dy==0:continue
                    mapping={}
                    valid=True
                    for sq,piece in board.piece_map().items():
                        f=chess.square_file(sq);r=chess.square_rank(sq)
                        if flip:f=7-f
                        f+=dx;r+=dy
                        if not 0<=f<8 or not 0<=r<8:
                            valid=False;break
                        mapping[chess.square_name(chess.square(f,r))]=piece.symbol()
                    if not valid:continue
                    try:fen=position(mapping,"w" if board.turn else "b")
                    except ValueError:continue
                    b=chess.Board(fen)
                    if b.is_game_over() or not any(b.legal_moves):continue
                    key=b.board_fen()+(" w" if b.turn else " b")
                    if key in seen:continue
                    new_focus=[]
                    for name in lesson["focus"]:
                        f=chess.square_file(chess.parse_square(name))
                        r=chess.square_rank(chess.parse_square(name))
                        if flip:f=7-f
                        f+=dx;r+=dy
                        if not 0<=f<8 or not 0<=r<8:
                            new_focus=[];break
                        new_focus.append(chess.square_name(chess.square(f,r)))
                    if not new_focus:continue
                    seen.add(key)
                    new+=1
                    variant={**lesson,
                        "id":lesson["id"]+"-variation-"+str(new).zfill(2),
                        "title":lesson["title"]+" - Practice "+str(new),
                        "subtitle":"A different legal position. Test the same principle without memorizing the board.",
                        "fen":fen,"focus":new_focus,
                        "hint":"Use the lesson principle, inspect checks/captures, and calculate the opponent's reply.",
                        "idea":"This is a new, board-validated example of the lesson theme. The best move must be established by Stockfish in this specific position."}
                    LESSONS.append(variant)
                    if new>=8:break
                if new>=8:break
            if new>=8:break
        if new<1:raise RuntimeError("No legal endgame practice variant: "+lesson["id"])
_extra_endgames()

BY_ID={x["id"]:x for x in LESSONS}
def ensure(con):
 con.executescript("""CREATE TABLE IF NOT EXISTS endgame_attempts(
 id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT NOT NULL DEFAULT 'player',
 lesson_id TEXT NOT NULL, fen TEXT NOT NULL, played_uci TEXT NOT NULL,
 best_uci TEXT NOT NULL, correct INTEGER NOT NULL, assisted INTEGER NOT NULL,
 cp_gap INTEGER, seconds REAL NOT NULL, attempted_at TEXT NOT NULL);
 CREATE INDEX IF NOT EXISTS endgame_attempts_user ON endgame_attempts(username,lesson_id);
 CREATE TABLE IF NOT EXISTS endgame_practice_rounds(
 round_id TEXT PRIMARY KEY, username TEXT NOT NULL,
 lesson_id TEXT NOT NULL, tries INTEGER NOT NULL DEFAULT 0,
 finished INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL);
 """)
 con.commit()
def available_tablebase():
 folder=os.getenv("CHESSGRIND_SYZYGY_PATH","")
 if not folder or not os.path.isdir(folder):return None
 return folder if any(x.endswith(".rtbw") for x in os.listdir(folder)) else None

def validate():
 for item in LESSONS:
  b=chess.Board(item["fen"])
  if not b.is_valid() or b.is_game_over():raise ValueError("Invalid endgame lesson "+item["id"])
  for sq in item["focus"]:
   chess.parse_square(sq)
 return True
validate()

def overview():
 con=db();ensure(con)
 try:
  records=con.execute("""SELECT lesson_id,COUNT(*) attempts,
    SUM(CASE WHEN assisted=0 THEN 1 ELSE 0 END) unassisted,
    SUM(CASE WHEN assisted=0 AND correct=1 THEN 1 ELSE 0 END) correct,
    MAX(attempted_at) recent FROM endgame_attempts WHERE username='player'
    GROUP BY lesson_id""").fetchall()
  scores={r["lesson_id"]:dict(r) for r in records}
  items=[]
  for lesson in LESSONS:
   x=scores.get(lesson["id"],{})
   count=x.get("unassisted") or 0
   items.append({"id":lesson["id"],"title":lesson["title"],"category":lesson["category"],
     "subtitle":lesson["subtitle"],
     "side":"White" if chess.Board(lesson["fen"]).turn else "Black",
     "attempts":x.get("attempts",0),
     "accuracy":round(100*x.get("correct",0)/count) if count else None,
     "lastAttempt":x.get("recent")})
  return {"lessons":items,"total":len(items),"attempts":sum(x["attempts"] for x in items),
    "tablebaseInstalled":bool(available_tablebase()),
    "disclaimer":"With no installed Syzygy files, Stockfish analysis is depth-limited and cannot certify theoretical win/draw/loss in every endgame."}
 finally:con.close()

def lesson(lesson_id):
 if lesson_id not in BY_ID:raise ValueError("Unknown endgame lesson")
 x=BY_ID[lesson_id]
 return {**x,"side":"White" if chess.Board(x["fen"]).turn else "Black",
   "pieceCount":len(chess.Board(x["fen"]).piece_map()),
   "tablebaseInstalled":bool(available_tablebase())}

def _score(info,side):
 p=info["score"].pov(side)
 return p.score(mate_score=20000),p.mate()

def _line(board,pv):
 work=board.copy()
 steps=[{"fen":work.fen(),"san":None,"uci":None}]
 for m in pv[:9]:
  if m not in work.legal_moves:break
  san=work.san(m);work.push(m)
  steps.append({"fen":work.fen(),"san":san,"uci":m.uci()})
 return {"text":variation(board,pv,max_plies=9),"steps":steps}

def play(lesson_id,move_uci,assisted=False,seconds=0,round_id=None):
 item=lesson(lesson_id);b=chess.Board(item["fen"])
 if not isinstance(move_uci,str) or not re.fullmatch("[a-h][1-8][a-h][1-8][qrbn]?",move_uci):raise ValueError("Choose a move on the board")
 m=chess.Move.from_uci(move_uci)
 if m not in b.legal_moves:raise ValueError("That move is not legal")
 if not isinstance(assisted,bool):raise ValueError("Invalid assistance")
 try:duration=max(0,min(float(seconds),3600))
 except (ValueError,TypeError):raise ValueError("Invalid duration")
 attempts=1;active=False
 if round_id is not None:
  if not isinstance(round_id,str) or not re.fullmatch("[a-f0-9]{32}",round_id):
   raise ValueError("Invalid endgame practice round")
  con=db();ensure(con)
  try:
   prior=con.execute("""SELECT * FROM endgame_practice_rounds
     WHERE round_id=? AND username=?""",(round_id,"player")).fetchone()
   if prior:
    if prior["lesson_id"]!=lesson_id or prior["finished"]:
     raise ValueError("This endgame round is complete or belongs to another position")
    attempts=prior["tries"]+1
   else:
    con.execute("""INSERT INTO endgame_practice_rounds
      VALUES(?,?,?,0,0,?)""",(round_id,"player",lesson_id,
         dt.datetime.now(dt.timezone.utc).isoformat()))
    con.commit()
   active=True
  finally:con.close()
 path=find_engine()
 if not path:raise RuntimeError("Stockfish is needed to grade endgames")
 with chess.engine.SimpleEngine.popen_uci(path,timeout=40) as eng:
  eng.configure({"Threads":1,"Hash":64})
  limit=chess.engine.Limit(depth=12)
  best=eng.analyse(b,limit)
  pv=best.get("pv",[])
  if not pv:raise RuntimeError("Engine did not return a legal move")
  top=pv[0]
  if m==top:chosen=best
  else:chosen=eng.analyse(b,limit,root_moves=[m])
  if not chosen.get("pv"):raise RuntimeError("Could not analyze candidate")
 root=b.turn;best_cp,best_mate=_score(best,root);move_cp,move_mate=_score(chosen,root)
 gap=engine_gap(best["score"].pov(root),chosen["score"].pov(root));accepted=gap<=65
 best_info=_line(b,pv)
 cand_pv=chosen["pv"]
 if cand_pv[0]!=m:cand_pv=[m]+cand_pv[1:]
 cand_info=_line(b,cand_pv)
 explanation=move_reasons(b,top)
 con=db();ensure(con)
 try:
  finished=bool(accepted or attempts>=3)
  if active:
   con.execute("""UPDATE endgame_practice_rounds SET tries=?,finished=?
    WHERE round_id=?""",(attempts,int(finished),round_id))
  con.execute("""INSERT INTO endgame_attempts(username,lesson_id,fen,played_uci,best_uci,
     correct,assisted,cp_gap,seconds,attempted_at) VALUES(?,?,?,?,?,?,?,?,?,?)""",
    ("player",lesson_id,b.fen(),m.uci(),top.uci(),
      int(accepted and (not active or attempts==1)),int(assisted),gap,duration,
     dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")))
  con.commit()
 finally:con.close()
 if active and not finished:
  return {"correct":False,"retry":True,"finished":False,
    "attemptNumber":attempts,"remaining":3-attempts,
    "yourSan":b.san(m),"summary":("Not quite â€” try again. Examine king activity, "+
     "pawn promotion threats and checks. "+str(3-attempts)+
     " attempt(s) remain; the engine solution stays hidden.")}
 return {"correct":accepted,"retry":False,"finished":True,
   "attemptNumber":attempts,"remaining":max(0,3-attempts),
   "revealed":bool(active and not accepted and attempts>=3),
   "assisted":assisted,"yourSan":b.san(m),
   "bestSan":b.san(top),"gapCp":gap,"yourLine":cand_info,"bestLine":best_info,
   "principle":item["principle"],"idea":item["idea"],"reasons":explanation,
   "bestScore":best_cp,"yourScore":move_cp,
   "forcedMate":best_mate if best_mate else None,
   "tablebaseVerified":False,
   "summary":("Your move is competitive at this search depth." if accepted else
              "Stockfish finds a stronger continuation. Replay both branches to see the key difference."),
   "limit":"The move grading is Stockfish depth 12. No tablebase proof was used; do not interpret the score as an exact win/draw/loss."}
