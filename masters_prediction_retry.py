"""A three-attempt exercise in reproducing a master's actual historical choice.

Different from objective best-move tests: a master sometimes played a
suboptimal move. No recorded answer or engine candidate leaks on misses 1–2.
"""
import re,sqlite3,datetime as dt
import chess
from chess_grind import db
from masters_library import _record,_replay,ensure as ensure_masters,USER

def ensure(con):
 ensure_masters(con)
 con.execute("""CREATE TABLE IF NOT EXISTS master_prediction_rounds(
 round_id TEXT PRIMARY KEY, username TEXT NOT NULL,game_id TEXT NOT NULL,
 ply INTEGER NOT NULL,tries INTEGER NOT NULL DEFAULT 0,
 finished INTEGER NOT NULL DEFAULT 0,created_at TEXT NOT NULL)""")
 con.commit()

def predict(game_id,ply,uci,round_id):
 if not isinstance(round_id,str) or not re.fullmatch("[a-f0-9]{32}",round_id):
  raise ValueError("Invalid prediction round ID")
 if type(ply) is not int or ply<0:raise ValueError("Invalid position")
 con=db();ensure(con)
 try:
  game=_record(game_id,con);frames=_replay(game)
  if ply>=len(frames)-1:raise ValueError("Choose a position before a recorded move")
  board=chess.Board(frames[ply]["fen"])
  try:move=chess.Move.from_uci(uci)
  except (TypeError,ValueError):raise ValueError("Choose a legal move")
  if move not in board.legal_moves:raise ValueError("Choose a legal move")
  row=con.execute("SELECT * FROM master_prediction_rounds WHERE round_id=? AND username=?",
    (round_id,USER)).fetchone()
  if row:
   if row["game_id"]!=game_id or row["ply"]!=ply:raise ValueError("Study round belongs to another position")
   if row["finished"]:raise ValueError("This round is complete; begin a new study challenge")
   attempts=row["tries"]+1
  else:
   attempts=1
   con.execute("INSERT INTO master_prediction_rounds VALUES(?,?,?,?,0,0,?)",
    (round_id,USER,game_id,ply,dt.datetime.now(dt.timezone.utc).isoformat()))
  master=frames[ply+1];same=master["uci"]==move.uci()
  finished=bool(same or attempts>=3)
  con.execute("UPDATE master_prediction_rounds SET tries=?,finished=? WHERE round_id=?",
    (attempts,int(finished),round_id))
  con.execute("""INSERT INTO master_predictions
    (username,game_id,ply,uci,same_as_master,created_at) VALUES(?,?,?,?,?,?)""",
    (USER,game_id,ply,move.uci(),int(same),
     dt.datetime.now(dt.timezone.utc).isoformat()))
  con.commit()
  response={"sameAsMaster":same,"attemptNumber":attempts,"remaining":max(0,3-attempts),
    "finished":finished,"retry":not finished,"yourMove":board.san(move)}
  if not finished:
   response["interpretation"]=("Not quite — try again. Which squares would the "+
      "master have wanted to control? "+str(3-attempts)+
      " attempts left. I haven't revealed the recorded move.")
   return response
  response.update({"masterMove":master["san"],"masterUci":master["uci"],
    "masterSide":master["side"],"revealed":not same,
    "interpretation":("Yes — you reproduced the actual historical move." if same else
     "Three attempts used. The master actually played "+master["san"]+
     ". This is a record of what happened, not necessarily Stockfish's best move.")})
  try:
   from masters_move_coach import teach
   insight=teach(game_id,ply+1)
   response["engineBestSan"]=insight["bestSan"]
   response["engineBestUci"]=insight["bestUci"]
   response["engineVerdict"]=insight["verdict"]
   response["note"]=("Historical choice: "+master["san"]+
    ". Engine choice at depth "+str(insight["engineDepth"])+": "+insight["bestSan"]+
    ". The two can differ.")
  except (RuntimeError,OSError,sqlite3.Error):
   response["note"]="No engine comparison available; studying the recorded move is not proof of objective strength."
  return response
 finally:con.close()
