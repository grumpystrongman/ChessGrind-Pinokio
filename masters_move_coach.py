"""On-demand, cached, move-by-move historical chess instruction.
Uses verified PGN replay, exact chess geometry and local Stockfish.
No private intentions, no fabricated tactical variations, no cloud model.
"""
from __future__ import annotations
import datetime as dt
import json,threading
import chess,chess.engine
from chess_grind import db
from masters_library import ensure as ensure_masters,_record,_replay,_engine_check
from game_analysis import find_engine
from opening_theory_cards import theory

GUARD=threading.RLock()
DEPTH=12

def ensure(con):
 con.execute("""CREATE TABLE IF NOT EXISTS master_move_lessons(
 game_id TEXT NOT NULL, ply INTEGER NOT NULL, depth INTEGER NOT NULL,
 payload TEXT NOT NULL, created_at TEXT NOT NULL,
 PRIMARY KEY(game_id,ply,depth))""")
 con.commit()

def classify(score,played,best):
 if played==best:return "Engine's first choice","At this search depth, the master's move is Stockfish's preferred move."
 if score<=25:return "Excellent alternative","This move is within about a quarter of a pawn of the engine's first choice."
 if score<=65:return "Strong alternative","This is close to the engine's best choice and may be comparably practical."
 if score<=105:return "Worth questioning","A more accurate alternative is available; study why the opponent can exploit the difference."
 if score<=220:return "Possible mistake","This position offered a materially stronger continuation at the current search depth."
 return "Possible serious mistake","The engine estimates a large difference; calculate the best reply before calling it a blunder."

def _stage(ply):
 return "Opening" if ply<=20 else "Middlegame" if ply<=70 else "Late game"

def _explain(board,move,frame):
 observed=(frame.get("moveFacts") or [])+(frame.get("observedChanges") or [])
 unique=[]
 for item in observed:
  t=item.strip()
  if t and t not in unique:unique.append(t)
 if board.is_capture(move):
  piece=board.piece_at(move.to_square)
  captured=("a "+chess.piece_name(piece.piece_type) if piece else
   "an opposing pawn by en passant" if board.is_en_passant(move) else "material")
  unique.insert(0,"The move captures "+captured+" on "+chess.square_name(move.to_square)+".")
 if board.gives_check(move):
  unique.insert(0,"The move checks the enemy king. The opponent must answer the check.")
 if board.is_castling(move):
  unique.insert(0,"The king castles to improve safety and connect the rooks.")
 if not unique:
  unique.append("The move changes the piece's active squares. Compare its attacks and defenders before and after.")
 return unique[:5]

def _concrete(board,move,after):
 """Verifiable move effects, piece activity and attack/defense geometry."""
 side=board.turn
 mover="White" if side else "Black"
 rival="Black" if side else "White"
 pc=board.piece_at(move.from_square)
 typ=chess.piece_name(pc.piece_type)
 src=chess.square_name(move.from_square)
 dst=chess.square_name(move.to_square)
 out=[mover+"'s "+typ+" goes from "+src+" to "+dst+"."]
 if board.is_capture(move):
  victim=(board.piece_at(move.to_square))
  out.append("The move captures "+(
   rival+"'s "+chess.piece_name(victim.piece_type) if victim else
   "an opposing pawn en passant")+".")
 if board.gives_check(move):
  out.append("This is check: the opponent must respond to the king threat immediately.")
 if board.is_castling(move):
  out.append("Castling moves the king toward shelter and activates the rook as part of the same move.")
 if pc.piece_type==chess.KING and not board.is_castling(move):
  out.append("This king step changes the king's file from "+src[0]+" to "+dst[0]+
   ". Evaluate checks available on the old and new files instead of assuming the move is safe just because it is legal.")
 attacks=after.attacks(move.to_square)
 before=board.attacks(move.from_square)
 controlled=sorted({chess.square_name(sq) for sq in attacks})
 gained=sorted({chess.square_name(sq) for sq in attacks-before})
 enemy=sorted(chess.square_name(x) for x in attacks if
   after.piece_at(x) and after.piece_at(x).color!=side)
 if pc.piece_type==chess.PAWN:
  out.append("From "+dst+", the pawn attacks "+
   (", ".join(controlled) if controlled else "no diagonal square on the board")+
   ". That changes the squares the other side can occupy safely.")
  if dst in ("d4","e4","d5","e5"):
   out.append("The pawn directly occupies the center on "+dst+".")
  if dst[0]!=src[0]:
   out.append("Because it captures diagonally, the pawn changes the files that may open for rooks.")
 elif pc.piece_type==chess.KNIGHT:
  out.append("A knight attacks in an L-shape; from "+dst+" it can reach "+
   ", ".join(controlled[:8])+". Count which of those squares are important to the enemy.")
 elif pc.piece_type in (chess.ROOK,chess.QUEEN,chess.BISHOP):
  if gained:
   out.append("Compared with its previous square, this piece newly influences "+
    ", ".join(gained[:7])+". Check whether those lines stay open after an opposing pawn moves.")
  else:
   out.append("On "+dst+", its lines of attack must be checked against blocking pieces.")
 if enemy:
  out.append("From the new square, the piece attacks an occupied enemy square: "+
   ", ".join(enemy[:6])+". A target is not automatically a winning capture.")
 if pc.piece_type in (chess.QUEEN,chess.ROOK,chess.BISHOP,chess.KNIGHT):
  defenders=after.attackers(side,move.to_square)
  attackers=after.attackers(not side,move.to_square)
  out.append("On "+dst+", this piece has "+str(len(defenders))+
   " friendly defender(s) and "+str(len(attackers))+
   " opposing attacker(s). Count exchanges before treating this square as an outpost.")
 return out

def _habit(board,move,score,best_san):
 p=board.piece_at(move.from_square).piece_type
 if p==chess.KING:
  habit="Before a quiet king move, look for checks on the old and new files, and ask whether the change prevents a tactical threat."
 elif p==chess.PAWN:
  habit="Before moving a pawn, ask which squares it will control, which lines it will open, and whether it gives the opponent a central break."
 elif p==chess.KNIGHT:
  habit="After each knight move, name all new attacked squares and check whether an enemy pawn can chase it away."
 elif p==chess.BISHOP:
  habit="Follow your bishop's diagonals and name which pawns can block or open them next."
 elif p==chess.ROOK:
  habit="For a rook move, ask which file or rank it controls and whether the opponent has immediate checks or captures."
 else:
  habit="With a queen move, check opponent threats and queen exposure before counting the attack as a success."
 if score>65:
  habit+=" At this decision the stronger candidate "+best_san+" needs concrete comparison with the actual move."
 return habit

def teach(game_id,ply):
 if type(ply) is not int or ply<1:raise ValueError("Choose a move after the game starts")
 with GUARD:
  con=db();ensure_masters(con);ensure(con)
  try:
   rec=_record(game_id,con)
   cached=con.execute("SELECT payload FROM master_move_lessons WHERE game_id=? AND ply=? AND depth=?",
      (game_id,ply,DEPTH)).fetchone()
   if cached:return json.loads(cached["payload"])
   frames=_replay(rec)
   if ply>=len(frames):raise ValueError("Move is outside the historical score")
   step=frames[ply];before=frames[ply-1]
   board=chess.Board(before["fen"]);move=chess.Move.from_uci(step["uci"])
   if move not in board.legal_moves:raise ValueError("Illegal historical game move")
   after=chess.Board(step["fen"])
   next_move=frames[ply+1] if ply+1<len(frames) else None
   path=find_engine()
   if not path:raise RuntimeError("Stockfish is needed for automatic move coaching")
   with chess.engine.SimpleEngine.popen_uci(path,timeout=35) as engine:
    engine.configure({"Threads":1,"Hash":32})
    verdict=_engine_check(board,engine,depth=DEPTH,played=move)
    if verdict is None:raise RuntimeError("Engine did not provide a legal continuation")
    if after.is_game_over():
     after_reply=None
    else:
     follow=engine.analyse(after,chess.engine.Limit(depth=9))
     follow_move=follow.get("pv",[None])[0]
     after_reply=after.san(follow_move) if follow_move else None
   score=verdict["lossCp"]
   label,meaning=classify(score,step["uci"],verdict["bestUci"])
   tips=_concrete(board,move,after)
   # Distinguish the recorded opponent response from best engine reply.
   actual_reply=(next_move["san"] if next_move else None)
   opponent= "Black" if step["side"]=="White" else "White"
   if after.is_checkmate():response="This move is checkmate. The final board has no legal defensive reply."
   elif after.is_stalemate():response="The move creates stalemate: there is no legal reply and the king is not in check."
   elif actual_reply:
    response=("In the real game, "+opponent+" answered with "+actual_reply+". "+
      ("Stockfish's local best reply is also "+after_reply+". " if after_reply==actual_reply else
       "Stockfish would instead consider "+str(after_reply)+". " if after_reply else "")+
      "The recorded reply is a fact; an engine suggestion is an alternative, not something that occurred.")
   else:response=("The PGN stops here. "+
     ("An analyzed possible reply is "+after_reply+". " if after_reply else "")+
     "Do not infer resignation or a forced result from the recorded result alone.")
   if score<=65:
    improvement=("The actual move "+step["san"]+" holds up to the depth-"+
       str(DEPTH)+" comparison. "+
       ("Stockfish also chooses this move." if step["uci"]==verdict["bestUci"] else
        "Stockfish prefers "+verdict["bestSan"]+
        " but the measured gap is small; compare their concrete follow-ups."))
   else:
    improvement=("Stockfish prefers "+verdict["bestSan"]+" in this position. "+
       "A concrete analyzed line is "+verdict["bestLine"]+
       ". Compare the resulting pawn structure, king safety, and piece activity. "+
       "The estimate is approximate and could change with deeper search.")
   stage=_stage(ply)
   ideas=theory(rec.get("opening") or "",step["side"])
   principle=_habit(board,move,score,verdict["bestSan"])
   if stage=="Opening":
    principle+=" Typical opening-family objective for this side: "+ideas["yourPlan"]+" The recorded board still controls whether this plan fits."
   elif stage=="Middlegame":
    principle+=" In this middlegame, inspect the other side's checks, captures and replies before extending the plan."
   else:
    principle+=" In the late game, count pawn tempos and king activity as well as piece threats."
   message=("On move "+str((ply+1)//2)+("." if step["side"]=="White" else "...")+
      " "+step["san"]+", "+step["side"]+" chose this continuation. "+
      " ".join(tips))
   out={"gameId":game_id,"ply":ply,"side":step["side"],"san":step["san"],
    "moveNumber":(ply+1)//2,"fenBefore":before["fen"],"fenAfter":step["fen"],
    "uci":step["uci"],"phase":stage,"verdict":label,"verdictDetail":meaning,
    "lossCp":score,"engineDepth":DEPTH,"bestSan":verdict["bestSan"],
    "bestUci":verdict["bestUci"],"bestLine":verdict["bestLine"],
    "playedLine":verdict["playedLine"],
    "playedSan":step["san"],"observations":tips,"why":message,
    "whatToStudy":improvement,"opponentReply":response,
    "actualOpponentReply":actual_reply,"engineOpponentReply":after_reply,
    "principle":principle,
    "question":("Would you choose "+step["san"]+" as "+step["side"]+
      ", or "+verdict["bestSan"]+"? What would the opponent do next?"),
    "caution":"Stockfish depth "+str(DEPTH)+" evaluates this decision, not the player's private intention or absolute truth. Review concrete lines before attributing a loss to one move."}
   con.execute("INSERT OR REPLACE INTO master_move_lessons VALUES(?,?,?,?,?)",
    (game_id,ply,DEPTH,json.dumps(out,ensure_ascii=False),
     dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")))
   con.commit()
   return out
  finally:con.close()
