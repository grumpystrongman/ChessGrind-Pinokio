"""Personal Opening Repertoire grounded in stored PGNs, never guessed opening theory."""
from __future__ import annotations
from collections import Counter,defaultdict
import datetime as dt
import io,json,re
import chess,chess.pgn
from chess_grind import db
from game_analysis import find_engine
from lesson_explainer import move_reasons

def current_username():
 from account_settings import username
 return username() or 'player'
MAX_PLIES=16

def ensure(con):
 con.executescript("""CREATE TABLE IF NOT EXISTS repertoire_choices(
    username TEXT NOT NULL, position_key TEXT NOT NULL, move_uci TEXT NOT NULL,
    saved_at TEXT NOT NULL, PRIMARY KEY(username,position_key));
 CREATE TABLE IF NOT EXISTS repertoire_reviews(
    id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT NOT NULL,
    position_key TEXT NOT NULL, move_uci TEXT NOT NULL, chosen_uci TEXT NOT NULL,
    correct INTEGER NOT NULL, assisted INTEGER NOT NULL, seconds REAL NOT NULL,
    reviewed_at TEXT NOT NULL);
 CREATE INDEX IF NOT EXISTS repertoire_reviews_recent
 ON repertoire_reviews(username,position_key,reviewed_at);
 CREATE TABLE IF NOT EXISTS repertoire_takeaways(
 username TEXT NOT NULL,position_key TEXT NOT NULL,
 note TEXT NOT NULL,updated_at TEXT NOT NULL,
 PRIMARY KEY(username,position_key));
 """)
 con.commit()

def board_key(board):
 # Compare chess-relevant state. Ignore fullmove and halfmove counters.
 return " ".join(board.fen().split(" ")[:4])

def _game_record(row):
 # PGNs may be absent or invalid. Don't infer missing games or moves.
 game=chess.pgn.read_game(io.StringIO(row["pgn"]))
 if not game:return None
 player=current_username().lower()
 white=str(row["white_username"] or "").lower()==player
 black=str(row["black_username"] or "").lower()==player
 if not (white or black):return None
 board=game.board();steps=[]
 for i,m in enumerate(game.mainline_moves()):
  if i>=MAX_PLIES:break
  if m not in board.legal_moves:break
  steps.append({"fen":board.fen(),"key":board_key(board),"uci":m.uci(),
    "san":board.san(m),"mover":"White" if board.turn else "Black",
    "ply":i,"after":None})
  board.push(m);steps[-1]["after"]=board.fen()
 return {"id":row["game_id"],"color":"White" if white else "Black",
   "result":row["result"],"timeClass":row["time_class"],"steps":steps,
   "opponent":row["black_username"] if white else row["white_username"]}

def _data(con):
 from chesscom_api import ensure_schema
 ensure_schema(con)
 rows=con.execute("""SELECT game_id,pgn,white_username,black_username,result,
     time_class FROM chesscom_games WHERE username=?""",(current_username(),)).fetchall()
 games=[]
 for row in rows:
  try:
   g=_game_record(row)
   if g and g["steps"]:games.append(g)
  except (ValueError,TypeError,UnicodeError):continue
 return games

def _outcome(result,color):
 # Chess.com imported result is from user's point of view; types vary.
 if result in ("win","checkmated","resigned","timeout","stalemate","agreed",
               "insufficient","repetition","timevsinsufficient","abandoned"):
  return "win" if result=="win" else "draw" if result in (
    "stalemate","agreed","insufficient","repetition","timevsinsufficient") else "loss"
 return "other"

def overview():
 con=db();ensure(con)
 try:
  games=_data(con)
  saved=con.execute("SELECT position_key,move_uci FROM repertoire_choices WHERE username=?",
                   (current_username(),)).fetchall()
  by_color={}
  for color in ("White","Black"):
   group=[g for g in games if g["color"]==color]
   first=Counter(next((s["san"] for s in g["steps"] if s["mover"]==color),"?") for g in group)
   # First move for Black is the response to White's move.
   by_color[color]={"games":len(group),"firstMoves":[{"move":m,"games":n} for m,n in first.most_common(8)]}
  reviews=con.execute("""SELECT correct,assisted FROM repertoire_reviews WHERE username=?""",(current_username(),)).fetchall()
  ind=[r for r in reviews if not r["assisted"]]
  return {"games":len(games),"colors":by_color,"savedPositions":len(saved),
    "attempts":len(reviews),"independentAccuracy":round(100*sum(r["correct"] for r in ind)/len(ind)) if ind else None,
    "method":"Opening frequencies count moves from your imported games; popularity does not imply engine strength. A saved move is your chosen repertoire preference, not the only correct chess move."}
 finally:con.close()

def lines(color="White",limit=14):
 if color not in ("White","Black"):raise ValueError("Choose White or Black")
 con=db();ensure(con)
 try:
  games=[g for g in _data(con) if g["color"]==color]
  # Group recognizable opening trajectories by the first four full moves
  # and show actual moves/positions, without inventing ECO names.
  groups=defaultdict(list)
  for g in games:
   # Require at least two full moves: one-move aborted games are poor
   # teaching examples. Group by the first two full moves, then show
   # a real representative continuation instead of hundreds of near-duplicates.
   if len(g["steps"])<4:continue
   prefix=tuple(s["san"] for s in g["steps"][:4])
   groups[prefix].append(g)
  output=[]
  for prefix,group in sorted(groups.items(),key=lambda kv:-len(kv[1]))[:max(1,min(int(limit),30))]:
   first=max(group,key=lambda g:len(g["steps"]))
   steps=[]
   for s in first["steps"][:12]:
    steps.append({"san":s["san"],"uci":s["uci"],"fen":s["fen"],"after":s["after"],
       "key":s["key"],"mover":s["mover"],"ply":s["ply"]})
   opening=prefix[0] if prefix else ""
   family="King pawn" if opening=="e4" else "Queen pawn" if opening=="d4" else (
      "English / flank pawn" if opening=="c4" else "Other first moves")
   start=prefix[0]
   reply=prefix[1] if len(prefix)>1 else None
   user_first=prefix[0] if color=="White" else reply
   title=("You start with "+user_first if color=="White" else
          "Against "+start+", you answer "+str(user_first))
   explanation=("Black's response is "+str(reply)+". Your next move in the example is "+
                (prefix[2] if len(prefix)>2 else "not recorded")+"."
                if color=="White" else
                "You are responding to White's first move. Observe White's next move "+
                (prefix[2] if len(prefix)>2 else "(not recorded)")+
                " before choosing your next plan.")
   from eco_catalog import classify
   eco_name=classify(steps[-1]["after"],
     moves=[item["uci"] for item in first["steps"]]) if steps else None
   output.append({"id":first["id"],"color":color,"family":family,
     "eco":eco_name,
     "title":title,"explanation":explanation,
     "label":" ".join(prefix),"count":len(group),"exampleOpponent":first["opponent"],
     "steps":steps,"sampleOutcomes":dict(Counter(_outcome(g["result"],color) for g in group))})
  return {"color":color,"lines":output,"totalGames":len(games),
    "disclaimer":"These are your actual opening sequences, grouped by the first four plies. Labels do not assert a named ECO opening or optimal play. Results are descriptive and sample-dependent."}
 finally:con.close()

def position(fen):
 if not isinstance(fen,str) or len(fen)>150:raise ValueError("Invalid chess position")
 board=chess.Board(fen)
 if not board.is_valid() or board.fullmove_number>15:raise ValueError("Use a valid early-game position")
 con=db();ensure(con)
 try:
  # Only give choices for positions from imported games; no arbitrary
  # fake "you often play" claims.
  key=board_key(board);counts=Counter();count=0;examples=defaultdict(list)
  for g in _data(con):
   for s in g["steps"]:
    if s["key"]!=key:continue
    counts[s["uci"]]+=1;count+=1
    if len(examples[s["uci"]])<4:examples[s["uci"]].append(g["id"])
  saved=con.execute("SELECT move_uci FROM repertoire_choices WHERE username=? AND position_key=?",
       (current_username(),key)).fetchone()
  options=[]
  for uci,n in counts.most_common(12):
   m=chess.Move.from_uci(uci)
   if m not in board.legal_moves:continue
   options.append({"uci":uci,"san":board.san(m),"games":n,
     "frequency":round(100*n/count) if count else 0,
     "reasons":move_reasons(board,m)[:2]})
  saved_note=con.execute("SELECT note FROM repertoire_takeaways WHERE username=? AND position_key=?",
                         (current_username(),key)).fetchone()
  chosen=saved["move_uci"] if saved else None
  if chosen and chess.Move.from_uci(chosen) not in board.legal_moves:chosen=None
  return {"fen":board.fen(),"positionKey":key,
    "side":"White" if board.turn else "Black","observedGames":count,
    "options":options,"savedMove":chosen,
    "myTakeaway":saved_note["note"] if saved_note else "",
    "savedSan":board.san(chess.Move.from_uci(chosen)) if chosen else None,
    "openingPrinciple":"Look for central control, development and king safety. These are study prompts; the exact position and opponent's response determine which plan works.",
    "note":"Observed moves are not ranked by quality. You choose a repertoire move; a later review checks recall of that choice."}
 finally:con.close()

def save(fen,uci):
 r=position(fen)
 if r["observedGames"]==0:raise ValueError("Choose a position from imported games")
 board=chess.Board(r["fen"])
 if not isinstance(uci,str):raise ValueError("Invalid move")
 move=chess.Move.from_uci(uci)
 if move not in board.legal_moves:raise ValueError("Your repertoire move must be legal")
 con=db();ensure(con)
 try:
  con.execute("""INSERT INTO repertoire_choices VALUES(?,?,?,?)
    ON CONFLICT(username,position_key) DO UPDATE SET
     move_uci=excluded.move_uci,saved_at=excluded.saved_at""",
    (current_username(),r["positionKey"],uci,dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")))
  con.commit()
  return {"saved":True,"move":board.san(move),"positionKey":r["positionKey"],
   "note":"Saved a preference, not an engine best-move claim."}
 finally:con.close()

def review():
 con=db();ensure(con)
 try:
  rows=con.execute("SELECT position_key,move_uci FROM repertoire_choices WHERE username=?",
     (current_username(),)).fetchall()
  completed={}
  for row in con.execute("""SELECT position_key,COUNT(*) n,
     MAX(reviewed_at) last_time FROM repertoire_reviews WHERE username=?
     GROUP BY position_key""",(current_username(),)):
   completed[row["position_key"]]=dict(row)
  for r in sorted(rows,key=lambda r:completed.get(r["position_key"],{}).get("last_time","")):
   key=r["position_key"];board=chess.Board(key+" 0 1")
   if board.is_valid() and chess.Move.from_uci(r["move_uci"]) in board.legal_moves:
    return {"fen":board.fen(),"side":"White" if board.turn else "Black",
      "positionKey":key,"pastReviews":completed.get(key,{}).get("n",0),
      "note":"Choose your saved move without being shown it. This checks repertoire recall, not whether it is objectively best."}
  return {"fen":None,"note":"Save a repertoire move from your games before training recall."}
 finally:con.close()

def grade_review(fen,uci,assisted=False,seconds=0):
 if not isinstance(assisted,bool):raise ValueError("Assistance must be true or false")
 board=chess.Board(fen)
 if not board.is_valid():raise ValueError("Invalid position")
 if not isinstance(uci,str):raise ValueError("Invalid move")
 played=chess.Move.from_uci(uci)
 if played not in board.legal_moves:raise ValueError("Illegal move")
 key=board_key(board)
 con=db();ensure(con)
 try:
  saved=con.execute("SELECT move_uci FROM repertoire_choices WHERE username=? AND position_key=?",(current_username(),key)).fetchone()
  if not saved:raise ValueError("Save a repertoire move first")
  chosen=chess.Move.from_uci(saved[0]);correct=chosen==played
  con.execute("INSERT INTO repertoire_reviews(username,position_key,move_uci,chosen_uci,correct,assisted,seconds,reviewed_at) VALUES(?,?,?,?,?,?,?,?)",
    (current_username(),key,chosen.uci(),played.uci(),int(correct),int(assisted),max(0,min(float(seconds),3600)),
     dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")))
  con.commit()
  return {"correct":correct,"yourSan":board.san(played),"savedSan":board.san(chosen),
    "assisted":assisted,"note":"This result checks recall of your saved repertoire preference, not chess move quality."}
 finally:con.close()

def save_takeaway(fen,note):
 """Save the learner's own words; do not infer mastery from note existence."""
 r=position(fen)
 if not r["observedGames"]:raise ValueError("Choose a position from your games")
 if not isinstance(note,str) or not 8<=len(note.strip())<=800:
  raise ValueError("Write a takeaway of 8 to 800 characters")
 con=db();ensure(con)
 try:
  con.execute("""INSERT INTO repertoire_takeaways VALUES(?,?,?,?)
    ON CONFLICT(username,position_key) DO UPDATE SET
    note=excluded.note,updated_at=excluded.updated_at""",
    (current_username(),r["positionKey"],note.strip(),dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")))
  con.commit()
  return {"saved":True,"takeaway":note.strip(),
    "note":"Saved your own explanation; this does not count as independent chess mastery."}
 finally:con.close()
