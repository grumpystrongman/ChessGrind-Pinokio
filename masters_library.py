"""Masters Library: sourced PGN archive, legal historical chess, both-sided study.

PGN Mentor player archives are imported as *move scores only*, with no source
annotation/commentary copied. The app teaches board-verifiable decisions,
depth-limited local Stockfish analysis and explicitly labeled interpretations.
"""
from __future__ import annotations
import datetime as dt
import hashlib,io,json,math,re,secrets,sqlite3,threading
from pathlib import Path
import chess,chess.pgn,chess.engine
from chess_grind import db
from game_analysis import find_engine
from engine_grade import engine_gap
from eco_catalog import classify
from opening_coach import snapshot,_explain_move,changes
ROOT=Path(__file__).resolve().parent
RAW=ROOT/"data"/"masters"/"raw"
USER="player"
LOCK=threading.RLock()
PLAYERS={
 "Morphy":("Paul Morphy","Romantic era"),
 "Anderssen":("Adolf Anderssen","Romantic era"),
 "Steinitz":("Wilhelm Steinitz","Classical foundations"),
 "Lasker":("Emanuel Lasker","Classical foundations"),
 "Capablanca":("José Raúl Capablanca","Classical foundations"),
 "Alekhine":("Alexander Alekhine","Classical foundations"),
 "Botvinnik":("Mikhail Botvinnik","Soviet school"),
 "Tal":("Mikhail Tal","Soviet school"),
 "Fischer":("Bobby Fischer","Soviet school"),
 "Karpov":("Anatoly Karpov","Modern champions"),
 "Kasparov":("Garry Kasparov","Modern champions"),
 "PolgarJ":("Judit Polgár","Modern champions"),
 "Anand":("Viswanathan Anand","Modern champions"),
 "Carlsen":("Magnus Carlsen","Contemporary"),
 "Gaprindashvili":("Nona Gaprindashvili","Soviet school"),
 "Hou":("Hou Yifan","Contemporary"),
 "Kramnik":("Vladimir Kramnik","Modern champions"),
 "Petrosian":("Tigran Petrosian","Soviet school"),
 "Nimzowitsch":("Aron Nimzowitsch","Classical foundations"),
 "Spassky":("Boris Spassky","Soviet school"),
 "Ding":("Ding Liren","Contemporary"),
 "Gukesh":("Gukesh Dommaraju","Contemporary"),
 "Smyslov":("Vasily Smyslov","Soviet school"),
 "Euwe":("Max Euwe","Classical foundations"),
 "Bronstein":("David Bronstein","Soviet school"),
 "Rubinstein":("Akiba Rubinstein","Classical foundations"),
 "Reti":("Richard Réti","Classical foundations"),
 "Tarrasch":("Siegbert Tarrasch","Classical foundations"),
 "Keres":("Paul Keres","Soviet school"),
 "Caruana":("Fabiano Caruana","Contemporary"),
 "Nakamura":("Hikaru Nakamura","Contemporary"),
 "Kosteniuk":("Alexandra Kosteniuk","Contemporary"),
 "Chiburdanidze":("Maia Chiburdanidze","Soviet school"),
 "Stefanova":("Antoaneta Stefanova","Contemporary"),
 "Koneru":("Koneru Humpy","Contemporary"),
 "Staunton":("Howard Staunton","Romantic era"),
 "Reshevsky":("Samuel Reshevsky","Soviet school"),
 "Korchnoi":("Viktor Korchnoi","Soviet school"),
 "Chigorin":("Mikhail Chigorin","Classical foundations")
}
SOURCE="https://www.pgnmentor.com/files.html"

def ensure(con):
 con.executescript("""CREATE TABLE IF NOT EXISTS master_games(
 id TEXT PRIMARY KEY, white TEXT NOT NULL,black TEXT NOT NULL,
 event TEXT NOT NULL,site TEXT NOT NULL,date TEXT NOT NULL,year INTEGER,
 result TEXT NOT NULL,eco TEXT,opening TEXT,plies INTEGER NOT NULL,
 winner TEXT NOT NULL,era TEXT NOT NULL,source_player TEXT NOT NULL,
 source_url TEXT NOT NULL, featured INTEGER NOT NULL DEFAULT 0,
 feature_reason TEXT,pgn TEXT NOT NULL);
 CREATE INDEX IF NOT EXISTS master_games_w ON master_games(white);
 CREATE INDEX IF NOT EXISTS master_games_b ON master_games(black);
 CREATE INDEX IF NOT EXISTS master_games_year ON master_games(year);
 CREATE INDEX IF NOT EXISTS master_games_feature ON master_games(featured,year);
 CREATE TABLE IF NOT EXISTS master_game_analyses(
 game_id TEXT PRIMARY KEY, analysis_json TEXT NOT NULL, created_at TEXT NOT NULL);
 CREATE TABLE IF NOT EXISTS master_chat(
 id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT NOT NULL,
 game_id TEXT NOT NULL, thread_id TEXT NOT NULL, ply INTEGER NOT NULL,
 role_side TEXT NOT NULL, question TEXT NOT NULL, answer TEXT NOT NULL,
 created_at TEXT NOT NULL);
 CREATE INDEX IF NOT EXISTS master_chat_index ON master_chat(username,game_id,thread_id,id);
 CREATE TABLE IF NOT EXISTS master_predictions(
 id INTEGER PRIMARY KEY AUTOINCREMENT,username TEXT NOT NULL,
 game_id TEXT NOT NULL,ply INTEGER NOT NULL,uci TEXT NOT NULL,
 same_as_master INTEGER NOT NULL,created_at TEXT NOT NULL);
 """)
 con.commit()

def _id(headers,ucis):
 stable="|".join(str(headers.get(k,"")) for k in ("White","Black","Date","Event"))+"|"+" ".join(ucis)
 return hashlib.sha256(stable.encode("utf8")).hexdigest()[:24]

def _era(year):
 if not year:return "Historical"
 if year<1880:return "Romantic era"
 if year<1935:return "Classical foundations"
 if year<1975:return "Soviet school"
 if year<2005:return "Modern champions"
 return "Contemporary"

def _winner(result):
 return {"1-0":"White","0-1":"Black","1/2-1/2":"Draw"}.get(result,"Unrecorded")

def _sanitize(s,n=120):
 return str(s or "").strip()[:n]

def _headers_scan(path):
 result=[]
 with path.open("r",encoding="utf-8-sig",errors="replace") as fp:
  while True:
   start=fp.tell()
   try:h=chess.pgn.read_headers(fp)
   except (ValueError,UnicodeError):continue
   if h is None:break
   if h.get("Result") not in ("1-0","0-1","1/2-1/2"):continue
   white=_sanitize(h.get("White"));black=_sanitize(h.get("Black"))
   year=h.get("Date","")[:4]
   year=int(year) if year.isdigit() else None
   event=h.get("Event","")
   notable=bool(re.search(r"World|Champ|Candidates|Match|Immortal|Opera|Linares|Wijk|Hastings|Moscow|New York 1924",event,re.I))
   result.append({"offset":start,"year":year,"white":white,"black":black,"result":h["Result"],
       "notable":notable,"event":event})
 return result

def _select(items,max_items=165):
 if len(items)<=max_items:return items
 chosen=set()
 # Across a player's full career, not merely the first few years.
 def add_group(rows,cap):
  if not rows:return
  if len(rows)<=cap:
   for r in rows:chosen.add(r["offset"])
   return
  for i in range(cap):
   r=rows[round((len(rows)-1)*(i+.5)/cap)]
   chosen.add(r["offset"])
 add_group([r for r in items if r["notable"]],45)
 add_group([r for r in items if r["result"]!="1/2-1/2"],70)
 add_group(items,max_items-len(chosen))
 ordered=[r for r in items if r["offset"] in chosen]
 return ordered[:max_items]

def import_archive(per_player=160,only=None):
 con=db();ensure(con)
 stats={"files":0,"imported":0,"invalid":0,"skipped":0}
 try:
  for filename,(player,era) in PLAYERS.items():
   if only is not None and filename not in only:continue
   path=RAW/(filename+".pgn")
   if not path.exists():stats["skipped"]+=1;continue
   stats["files"]+=1
   entries=_select(_headers_scan(path),max_items=per_player)
   with path.open("r",encoding="utf-8-sig",errors="replace") as f:
    for record in entries:
     try:
      f.seek(record["offset"]);game=chess.pgn.read_game(f)
      if not game or game.errors:stats["invalid"]+=1;continue
      board=game.board();ucis=[]
      for mv in game.mainline_moves():
       if mv not in board.legal_moves:break
       ucis.append(mv.uci());board.push(mv)
      if not 12<=len(ucis)<=340:stats["invalid"]+=1;continue
      h=game.headers
      canonical=_id(h,ucis)
      # Writing only original factual move scores, not existing PGN commentary.
      clean=game.accept(chess.pgn.StringExporter(headers=True,variations=False,comments=False))
      featured=int(record["notable"] or (
       record["year"] is not None and record["year"]<1900 and len(ucis)>35))
      reason="Championship or historically notable event" if record["notable"] else (
       "Early historical chess example" if featured else None)
      eco=h.get("ECO")
      opening=None
      try:
       if len(ucis)>4:
        b=chess.Board()
        for m in ucis[:min(18,len(ucis))]:b.push_uci(m)
        match=classify(b.fen(),moves=ucis[:min(18,len(ucis))])
        if match:
         eco=match["eco"];opening=match["name"]
      except (ValueError,IndexError):pass
      prior_changes=con.total_changes
      con.execute("""INSERT OR IGNORE INTO master_games
      (id,white,black,event,site,date,year,result,eco,opening,plies,winner,era,
       source_player,source_url,featured,feature_reason,pgn)
       VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
       (canonical,_sanitize(h.get("White")), _sanitize(h.get("Black")),
        _sanitize(h.get("Event"),200),_sanitize(h.get("Site"),140),_sanitize(h.get("Date"),30),
        record["year"],h.get("Result"),eco,opening,len(ucis),_winner(h.get("Result")),
        _era(record["year"]),filename,
        "https://www.pgnmentor.com/players/"+filename+".zip",
        featured,reason,clean))
      stats["imported"]+=con.total_changes-prior_changes
     except (UnicodeError,ValueError,TypeError,sqlite3.Error):
      stats["invalid"]+=1
   con.commit()
  stats["stored"]=con.execute("SELECT count(*) FROM master_games").fetchone()[0]
  stats["players"]=con.execute("SELECT count(DISTINCT source_player) FROM master_games").fetchone()[0]
  return stats
 finally:con.close()

def overview():
 con=db();ensure(con)
 try:
  rows=con.execute("""SELECT source_player,COUNT(*) n FROM master_games
   GROUP BY source_player ORDER BY source_player""").fetchall()
  eras=con.execute("""SELECT era,COUNT(*) n FROM master_games
   GROUP BY era ORDER BY MIN(year)""").fetchall()
  return {"total":sum(x["n"] for x in rows),
     "masters":[{"key":next((key for key,v in PLAYERS.items()
          if key==r["source_player"] or v[0]==r["source_player"]),r["source_player"]),
        "name":next((v[0] for key,v in PLAYERS.items()
          if key==r["source_player"] or v[0]==r["source_player"]),r["source_player"]),
        "era":next((v[1] for key,v in PLAYERS.items()
          if key==r["source_player"] or v[0]==r["source_player"]),"Historical"),
        "games":r["n"]} for r in rows],
    "eras":[{"name":r["era"],"games":r["n"]} for r in eras],
    "source":SOURCE,
    "note":"Curated examples from verified legal PGN move scores. The archive is not exhaustive; featured tags indicate event metadata, not verified historical fame. Commentary is newly generated, not copied."}
 finally:con.close()

def search(q="",player="",era="",outcome="",limit=40,offset=0):
 if any(len(str(v))>120 for v in (q,player,era,outcome)):raise ValueError("Search too long")
 if not isinstance(limit,int) or not isinstance(offset,int):raise ValueError("Invalid paging")
 clauses=["1=1"];args=[]
 if q:
  clauses.append("(white LIKE ? OR black LIKE ? OR event LIKE ? OR opening LIKE ? OR date LIKE ?)")
  args+=["%"+q+"%"]*5
 if player:
  clauses.append("(source_player=? OR white LIKE ? OR black LIKE ?)")
  args.extend([player,"%"+player+"%","%"+player+"%"])
 if era:clauses.append("era=?");args.append(era)
 if outcome in ("White","Black","Draw"):clauses.append("winner=?");args.append(outcome)
 where=" AND ".join(clauses)
 con=db();ensure(con)
 try:
  n=con.execute("SELECT COUNT(*) FROM master_games WHERE "+where,args).fetchone()[0]
  rows=con.execute("""SELECT id,white,black,event,site,date,year,result,eco,opening,
   plies,winner,era,source_player,featured,feature_reason FROM master_games WHERE """+
   where+" ORDER BY featured DESC,year ASC,white ASC LIMIT ? OFFSET ?",
   args+[max(1,min(limit,80)),max(0,offset)]).fetchall()
  return {"total":n,"games":[dict(r) for r in rows],"offset":offset,"source":SOURCE}
 finally:con.close()

def _record(game_id,con):
 if not isinstance(game_id,str) or not re.fullmatch("[a-f0-9]{24}",game_id):
  raise ValueError("Invalid historical game ID")
 row=con.execute("SELECT * FROM master_games WHERE id=?",(game_id,)).fetchone()
 if not row:raise ValueError("Master game not found")
 return dict(row)

def _replay(rec):
 game=chess.pgn.read_game(io.StringIO(rec["pgn"]))
 if not game or game.errors:raise RuntimeError("Stored PGN cannot be replayed legally")
 b=game.board()
 frames=[{"ply":0,"fen":b.fen(),"san":None,"uci":None,"side":None}]
 for i,m in enumerate(game.mainline_moves()):
  if m not in b.legal_moves:raise RuntimeError("Illegal historical move at ply "+str(i+1))
  side="White" if b.turn else "Black"
  before=b.fen();san=b.san(m);capture=b.is_capture(m);check=b.gives_check(m)
  observed_changes=changes(b,m)
  move_reasons=_explain_move(b,m)
  b.push(m)
  frames.append({"ply":i+1,"fen":b.fen(),"beforeFen":before,"san":san,
    "observedChanges":observed_changes,"moveFacts":move_reasons,
    "uci":m.uci(),"side":side,"capture":capture,"check":check,
    "piece":chess.piece_name(chess.Piece.from_symbol(
       chess.Board(before).piece_at(m.from_square).symbol()).piece_type)})
 return frames

def detail(game_id):
 con=db();ensure(con)
 try:
  rec=_record(game_id,con)
  row=con.execute("SELECT analysis_json FROM master_game_analyses WHERE game_id=?",(game_id,)).fetchone()
  assessment=json.loads(row[0]) if row else None
 finally:con.close()
 frames=_replay(rec)
 from masters_curriculum import profile,walkthrough
 from opening_theory_cards import theory
 family=theory(rec.get("opening") or "", "White")
 strategies={"White":family["white"],"Black":family["black"],
   "pawnStructure":family["structure"],"calculation":family["calculation"],
   "pitfall":family["pitfall"],"scope":family["status"]}
 return {"game":{k:v for k,v in rec.items() if k!="pgn"},
    "strategies":strategies,
    "playerProfiles":{"White":_master_player_profile(rec["white"]),
      "Black":_master_player_profile(rec["black"])},
    "chapters":walkthrough(rec,frames,assessment),
    "moves":frames,"assessment":assessment,
    "outcomeExplanation":_outcome(rec,assessment),
    "sourceNote":"PGN score is historical game data. Player intentions cannot be established solely from moves. Chess Grind's explanations are interpretations supported by board geometry and limited-depth Stockfish."}

def _master_player_profile(name):
 from masters_curriculum import profile
 # Match surnames carefully, preferring first token of known family names.
 for key,(full_name,era) in PLAYERS.items():
  surname=full_name.split()[-1].casefold()
  if (surname and surname in name.casefold()) or key.casefold()==name.casefold():
   return {**profile(key),"name":full_name,"era":era}
 return {"name":name,"era":"Historical",
   "knownFor":"Strong historical opposition","studyFocus":
     "Study this player's choices and compare the opponent's best available resources.",
   "scope":"No curated style claim available for this player."}

def _outcome(rec,assessment):
 result=rec["result"]
 basics={"1-0":"White won. The recorded result does not by itself identify a single losing move.",
         "0-1":"Black won. The recorded result does not by itself identify a single losing move.",
         "1/2-1/2":"The game was drawn. A drawn result may arise from agreement, repetition, stalemate or another rule; the PGN result alone need not specify which."}
 if not assessment or not assessment.get("turningPoints"):
  return basics.get(result,"Game result not recorded.")
 major=assessment["turningPoints"][:3]
 labels=[f"move {math.ceil(x['ply']/2)} ({x['side']} played {x['playedSan']})" for x in major]
 return basics.get(result,"")+" Engine-flagged moments worth investigating: "+", ".join(labels)+". These may be significant but do not prove unique historical causation."

def _limit_score(info,side):
 pov=info["score"].pov(side)
 m=pov.mate()
 if m is not None:return {"cp":pov.score(mate_score=20000),"mate":m}
 return {"cp":pov.score(),"mate":None}

def _engine_check(b,engine,depth=10,played=None):
 before=engine.analyse(b,chess.engine.Limit(depth=depth))
 if not before.get("pv"):return None
 best=before["pv"][0];white=b.turn
 best_score=_limit_score(before,white)
 played_result=before if played==best else (
    engine.analyse(b,chess.engine.Limit(depth=depth),root_moves=[played])
    if played is not None else None)
 chosen_score=_limit_score(played_result,white) if played_result else None
 delta=engine_gap(before["score"].pov(white),played_result["score"].pov(white)) if played_result else 0
 pv=b.variation_san(before["pv"][:min(len(before["pv"]),6)])
 return {"bestUci":best.uci(),"bestSan":b.san(best),
   "playedUci":played.uci() if played else None,
   "playedSan":b.san(played) if played else None,
   "playedLine":(b.variation_san(played_result["pv"][:min(len(played_result["pv"]),6)])
                 if played_result and played_result.get("pv") else None),
   "bestScore":best_score,"playedScore":chosen_score,
   "lossCp":delta,"bestLine":pv}

def analyze(game_id):
 """Sample strategic timeline plus focused biggest engine-decision mistakes; cached.

 This is an analysis of candidate positions, not a complete proof that every
 move has been optimally assessed. Every stored line remains replayable/legal.
 """
 with LOCK:
  con=db();ensure(con)
  try:
   rec=_record(game_id,con)
   cached=con.execute("SELECT analysis_json FROM master_game_analyses WHERE game_id=?",(game_id,)).fetchone()
   if cached:
    prior=json.loads(cached[0])
    if "outcomeTeaching" in prior:return prior
    con.execute("DELETE FROM master_game_analyses WHERE game_id=?",(game_id,))
    con.commit()
   frames=_replay(rec)
   if not find_engine():raise RuntimeError("Stockfish required for master-game evaluation")
   # Sample from entire game, rather than focusing only on opening tactics.
   total=len(frames)-1
   targets={i for i in range(1,total+1,max(3,total//15))}
   targets.update([round(total*t) for t in (.18,.35,.52,.7,.87)])
   targets.update(range(max(1,total-3),total+1))
   targets=sorted(p for p in targets if 1<=p<=total)
   # Limited-depth, deliberately bounded. Never call it an exhaustive blunder audit.
   observations=[]
   with chess.engine.SimpleEngine.popen_uci(find_engine(),timeout=50) as engine:
    engine.configure({"Threads":1,"Hash":48})
    for ply in targets:
     f=frames[ply]
     b=chess.Board(frames[ply-1]["fen"])
     move=chess.Move.from_uci(f["uci"])
     decision=_engine_check(b,engine,depth=9,played=move)
     if decision is None:continue
     observation={"ply":ply,"side":f["side"],"fen":b.fen(),**decision}
     observations.append(observation)
   biggest=sorted((x for x in observations if x["lossCp"]>=90),
     key=lambda x:-x["lossCp"])[:8]
   # Stable chronological timeline + top moments, with no winner-only analysis.
   white_items=[x for x in observations if x["side"]=="White"]
   black_items=[x for x in observations if x["side"]=="Black"]
   final_board=chess.Board(frames[-1]["fen"])
   winner=rec["winner"]
   ending=("The final recorded position is checkmate, verified from the legal board."
           if final_board.is_checkmate() else
           "The PGN records the result, but the final board alone does not prove whether play ended by resignation, agreement, clock or another mechanism.")
   findings={}
   for side,items in (("White",white_items),("Black",black_items)):
    harmed=[x for x in items if x["lossCp"]>=90]
    worst=max(harmed,key=lambda x:x["lossCp"]) if harmed else None
    findings[side]={"sampled":len(items),"flagged":len(harmed),
      "largestLoss":({"ply":worst["ply"],"played":worst["playedSan"],
       "best":worst["bestSan"],"gapCp":worst["lossCp"],
       "line":worst["bestLine"]} if worst else None)}
   parts=[ending]
   for side in ("White","Black"):
    f=findings[side]
    if f["largestLoss"]:
     t=f["largestLoss"]
     parts.append(side+" has "+str(f["flagged"])+" flagged sampled decisions; "+
       "the largest examined gap follows "+t["played"]+" on move "+
       str((t["ply"]+1)//2)+", where Stockfish preferred "+t["best"]+
       " (about "+f"{t['gapCp']/100:.2f}"+ " pawns of depth-9 evaluation difference).")
    else:
     parts.append("No major loss for "+side+" was found at the sampled positions. "+
       "This is not a clean bill of health for unexamined moves.")
   parts.append("This comparison helps explain where both sides gained or lost opportunities. "+
     "It does not establish the single historical cause of "+("the draw." if winner=="Draw" else winner+"'s win."))
   result={"gameId":game_id,"sideFindings":findings,
     "outcomeTeaching":" ".join(parts),"finalBoardCheckmate":final_board.is_checkmate(),
     "sampledDecisions":len(observations),
     "totalMoves":total,"turningPoints":biggest,
     "timeline":observations,
     "whiteMoments":sum(x["side"]=="White" for x in observations),
     "blackMoments":sum(x["side"]=="Black" for x in observations),
     "method":"Stockfish depth 9 sampled checkpoints, not every move. The highest evaluation losses are candidates for discussion, not necessarily the unique causes of the recorded result.",
     "outcome":rec["result"]}
   con.execute("""INSERT INTO master_game_analyses(game_id,analysis_json,created_at)
   VALUES(?,?,?)""",(game_id,json.dumps(result),dt.datetime.now(dt.timezone.utc).isoformat()))
   con.commit()
   return result
  finally:con.close()

def predict(game_id,ply,uci):
 con=db();ensure(con)
 try:
  rec=_record(game_id,con);frames=_replay(rec)
  if not isinstance(ply,int) or not 0<=ply<len(frames)-1:raise ValueError("Choose a position before the master moved")
  b=chess.Board(frames[ply]["fen"])
  if not isinstance(uci,str):raise ValueError("Choose a legal chess move")
  mv=chess.Move.from_uci(uci)
  if mv not in b.legal_moves:raise ValueError("Move is illegal")
  master_move=frames[ply+1]
  same=mv.uci()==master_move["uci"]
  con.execute("""INSERT INTO master_predictions(username,game_id,ply,uci,same_as_master,created_at)
   VALUES(?,?,?,?,?,?)""",(USER,game_id,ply,uci,int(same),
    dt.datetime.now(dt.timezone.utc).isoformat()))
  con.commit()
  return {"sameAsMaster":same,"yourMove":b.san(mv),
    "masterMove":master_move["san"],"masterSide":master_move["side"],
    "note":"Matching the master's recorded move measures imitation, not whether your alternative is objectively good. Check the engine and the opponent's response."}
 finally:con.close()
