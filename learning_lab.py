"""Chess Grind learning lab: assess unaided decisions, teach and verify transfer."""
import chess,chess.engine,datetime as dt,json,secrets,re
from collections import Counter,defaultdict
from chess_grind import db
from motifs import classify
from visual_coach import annotate
from game_analysis import find_engine
from coaching import lesson_search
from move_grading import grade

THEMES={"calculation":"Compare checks, captures and threats for both players.",
"piece safety":"Before moving, scan attacked and undefended pieces.",
"opening decisions":"Develop pieces, contest the center and protect your king.",
"forks and double attacks":"Look for one move attacking two valuable pieces.",
"pins":"Trace rook, bishop and queen rays through valuable pieces.",
"forcing checks":"Find forcing checks and calculate the replies.",
"missed captures":"Check forcing exchanges and hanging pieces.",
"endgame technique":"Activate your king and calculate pawn races.",
"checkmate patterns":"List the king's escapes, blocks and captures."}
WEIGHT={"rapid":3,"blitz":1,"daily":0.6,"bullet":0.25}
def ensure(c):
 c.executescript("""CREATE TABLE IF NOT EXISTS lab_sessions(id TEXT PRIMARY KEY,username TEXT NOT NULL,topic TEXT NOT NULL,mode TEXT NOT NULL,ids TEXT NOT NULL,current INTEGER DEFAULT 0,created TEXT NOT NULL);
 CREATE TABLE IF NOT EXISTS lab_events(id INTEGER PRIMARY KEY AUTOINCREMENT,username TEXT,session_id TEXT,game_id TEXT,ply INTEGER,topic TEXT,stage TEXT,correct INTEGER,assisted INTEGER,seconds REAL,at TEXT,details TEXT);
 CREATE TABLE IF NOT EXISTS lab_mastery(username TEXT,game_id TEXT,ply INTEGER,topic TEXT,seen INTEGER DEFAULT 0,correct INTEGER DEFAULT 0,streak INTEGER DEFAULT 0,due TEXT,last_seen TEXT,PRIMARY KEY(username,game_id,ply));
 CREATE TABLE IF NOT EXISTS lab_notes(username TEXT,session_id TEXT,game_id TEXT,ply INTEGER,note TEXT,at TEXT,PRIMARY KEY(username,session_id,game_id,ply));""");c.commit()
def stamp():return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
def items(c,user="player"):
 ensure(c)
 progress={(r["game_id"],r["ply"]):dict(r) for r in c.execute("SELECT * FROM lab_mastery WHERE username=?",(user,))}
 out=[];today=dt.date.today().isoformat()
 for r in c.execute("SELECT data FROM game_analysis WHERE username=?",(user,)):
  g=json.loads(r[0])
  for m in g["mistakes"]:
   if not m.get("fen") or not m.get("best"):continue
   try:chess.Board(m["fen"]).parse_san(m["best"])
   except ValueError:continue
   x=dict(m);x.update(gameId=g["id"],opponent=g["opponent"],color=g["color"],timeClass=g.get("timeClass","rapid"))
   x["topic"]=classify(m)["topic"];p=progress.get((g["id"],m["ply"]),{})
   x["seen"]=p.get("seen",0);x["due"]=not p.get("due") or p["due"]<=today
   out.append(x)
 return out
def pick(c,topic=None,count=5):
 all_items=[m for m in items(c) if m["due"] and (not topic or m["topic"]==topic)]
 if not all_items:raise ValueError("No due exercises in that category. Try another theme.")
 # A due review should not be buried behind hundreds of new positions.
 old=[m for m in all_items if m["seen"]>0];new=[m for m in all_items if m["seen"]==0]
 old.sort(key=lambda m:(-WEIGHT.get(m["timeClass"],.5),-m["loss"]))
 new.sort(key=lambda m:(-WEIGHT.get(m["timeClass"],.5),-m["loss"]))
 ranked=[]
 while old or new:
  if old:ranked.append(old.pop(0))
  if new:ranked.append(new.pop(0))
 all_items=ranked
 chosen=[];seen=set()
 for m in all_items:
  if m["gameId"] not in seen:chosen.append(m);seen.add(m["gameId"])
  if len(chosen)>=count:break
 for m in all_items:
  if len(chosen)>=count:break
  if (m["gameId"],m["ply"]) not in {(x["gameId"],x["ply"]) for x in chosen}:chosen.append(m)
 return chosen
def session_start(topic=None,mode="guided",count=5):
 if topic and topic not in THEMES:raise ValueError("Unknown skill")
 if mode not in ("guided","micro","campaign","assessment"):raise ValueError("Unknown session mode")
 c=db();ensure(c);count=1 if mode=="micro" else max(1,min(int(count),12))
 selected=pick(c,topic,count);sid=secrets.token_urlsafe(18)
 ids=[{"gameId":m["gameId"],"ply":m["ply"]} for m in selected]
 c.execute("INSERT INTO lab_sessions VALUES(?,?,?,?,?,0,?)",(sid,"player",topic or "mixed",mode,json.dumps(ids),stamp()));c.commit()
 return {"sessionId":sid,"topic":topic or "mixed","mode":mode,"total":len(ids),"exercise":exercise(sid)}
def context(c,sid):
 r=c.execute("SELECT * FROM lab_sessions WHERE id=? AND username='player'",(sid,)).fetchone()
 if r is None:raise ValueError("Unknown learning session")
 r=dict(r);ids=json.loads(r["ids"])
 if r["current"]>=len(ids):return r,None
 key=ids[r["current"]]
 g=c.execute("SELECT data FROM game_analysis WHERE game_id=? AND username='player'",(key["gameId"],)).fetchone()
 if not g:raise ValueError("Game is no longer available")
 data=json.loads(g[0]);m=next((m for m in data["mistakes"] if m["ply"]==key["ply"]),None)
 if not m:raise ValueError("Position missing")
 m=dict(m);m.update(gameId=key["gameId"],topic=classify(m)["topic"],opponent=data["opponent"],color=data["color"])
 return r,m
def spot_question(m):
 b=chess.Board(m["fen"])
 own=[chess.square_name(s) for s,p in b.piece_map().items() if p.color==b.turn and p.piece_type!=chess.KING and b.is_attacked_by(not b.turn,s) and not b.is_attacked_by(b.turn,s)]
 if own:return {"kind":"loose","prompt":"Tap your attacked, undefended pieces.","targets":sorted(own)}
 takes=sorted({chess.square_name(mv.to_square) for mv in b.legal_moves if b.is_capture(mv) and not b.is_en_passant(mv)})
 if takes:return {"kind":"captures","prompt":"Tap all enemy squares you could legally capture now.","targets":takes}
 defended=sorted(chess.square_name(s) for s,p in b.piece_map().items() if p.color==b.turn and p.piece_type not in (chess.KING,chess.PAWN) and b.is_attacked_by(b.turn,s))
 return {"kind":"defenders","prompt":"Tap your protected knights, bishops, rooks and queens. If none, continue.","targets":defended}
def prediction_board(c,sid,m):
 b=chess.Board(m["fen"])
 b.push(b.parse_san(m["best"]))
 rows=c.execute("""SELECT details FROM lab_events WHERE session_id=? AND
   stage='predict' AND game_id=? AND ply=? ORDER BY id""",(sid,m["gameId"],m["ply"])).fetchall()
 for r in rows:
  try:
   move=chess.Move.from_uci(json.loads(r["details"]).get("uci",""))
   if move not in b.legal_moves:break
   b.push(move)
  except (ValueError,TypeError):break
 return b,len(rows)

def stage(c,sid,m):
 rows=[r["stage"] for r in c.execute("SELECT stage FROM lab_events WHERE session_id=? AND game_id=? AND ply=? ORDER BY id",(sid,m["gameId"],m["ply"]))]
 if "spot" not in rows:return "spot"
 if "move" not in rows:return "move"
 board,done=prediction_board(c,sid,m)
 if done<3 and not board.is_game_over():return "predict"
 if "learn" not in rows:return "learn"
 return "prove"

def exercise(sid):
 c=db();ensure(c);sess,m=context(c,sid)
 if not m:return {"completed":True,"position":sess["current"],"total":len(json.loads(sess["ids"]))}
 step=stage(c,sid,m);spot=spot_question(m)
 r={"sessionId":sid,"completed":False,"position":sess["current"],"total":len(json.loads(sess["ids"])),
 "stage":step,"fen":m["fen"],"color":m["color"],"topic":m["topic"],"gameId":m["gameId"],"ply":m["ply"],
 "opponent":m["opponent"],"prompt":spot["prompt"] if step=="spot" else "",
 "principle":THEMES.get(m["topic"],THEMES["calculation"])}
 # Return a previously submitted move only after that stage has been completed.
 # This lets the conversational coach retain the original position while
 # prediction mode displays later positions from the continuation.
 previous_move=c.execute("""SELECT details FROM lab_events WHERE session_id=?
   AND game_id=? AND ply=? AND stage='move' ORDER BY id DESC LIMIT 1""",
   (sid,m["gameId"],m["ply"])).fetchone()
 if previous_move:
  try:
   origin=chess.Board(m["fen"])
   uci=json.loads(previous_move["details"])["uci"]
   chosen=chess.Move.from_uci(uci)
   if chosen in origin.legal_moves:
    r["coachContext"]={"fen":m["fen"],"yourMove":origin.san(chosen),"bestMove":m["best"]}
  except (KeyError,ValueError,TypeError):pass
 if step=="predict":
  b,count=prediction_board(c,sid,m)
  r["fen"]=b.fen()
  r["predictionNumber"]=count+1
  r["predictionTotal"]=3
  r["predictingColor"]="White" if b.turn else "Black"
 if step=="prove":
  alt=transfer(c,m,sid);r["transferAvailable"]=bool(alt)
  if alt:r["fen"]=alt["fen"];r["color"]=alt["color"];r["opponent"]=alt["opponent"]
 return r
def transfer(c,m,sid=None):
 reserved=set()
 if sid:
  row=c.execute("SELECT ids FROM lab_sessions WHERE id=?",(sid,)).fetchone()
  if row:reserved={(x["gameId"],x["ply"]) for x in json.loads(row[0])}
 a=[x for x in items(c) if x["topic"]==m["topic"] and x["gameId"]!=m["gameId"] and x["seen"]==0
    and (x["gameId"],x["ply"]) not in reserved]
 a.sort(key=lambda x:-WEIGHT.get(x["timeClass"],.5))
 return a[0] if a else None
def legal_move(fen,uci):
 if not isinstance(uci,str) or not re.fullmatch(r"[a-h][1-8][a-h][1-8][qrbn]?",uci):raise ValueError("Select a starting and destination square")
 b=chess.Board(fen);mv=chess.Move.from_uci(uci)
 if mv not in b.legal_moves:raise ValueError("That move is illegal")
 return b,mv
def record(c,sid,m,stage_name,correct,assisted,seconds=0,detail=None):
 c.execute("INSERT INTO lab_events(username,session_id,game_id,ply,topic,stage,correct,assisted,seconds,at,details) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
 ("player",sid,m["gameId"],m["ply"],m["topic"],stage_name,int(bool(correct)),int(bool(assisted)),
 max(0,min(float(seconds or 0),3600)),stamp(),json.dumps(detail or {})))
 if stage_name in ("move","prove"):
  old=c.execute("SELECT * FROM lab_mastery WHERE username='player' AND game_id=? AND ply=?",(m["gameId"],m["ply"])).fetchone()
  old=dict(old) if old else {};streak=old.get("streak",0)+1 if correct and not assisted else 0
  due=(dt.date.today()+dt.timedelta(days=(2**min(streak,4)) if streak else 1)).isoformat()
  c.execute("""INSERT INTO lab_mastery VALUES(?,?,?,?,?,?,?, ?,?) ON CONFLICT(username,game_id,ply) DO UPDATE SET
  seen=lab_mastery.seen+1,correct=lab_mastery.correct+excluded.correct,
  streak=excluded.streak,due=excluded.due,last_seen=excluded.last_seen""",
  ("player",m["gameId"],m["ply"],m["topic"],1,int(correct and not assisted),streak,due,stamp()))
 c.commit()
def advance(c,sid,sess):
 c.execute("UPDATE lab_sessions SET current=? WHERE id=?",(sess["current"]+1,sid));c.commit()
def act(sid,action,payload):
 if not isinstance(payload,dict):raise ValueError("Expected an object")
 c=db();ensure(c);sess,m=context(c,sid)
 if not m:raise ValueError("Session completed")
 st=stage(c,sid,m)
 if action!=st:raise ValueError("Complete the previous step first")
 seconds=payload.get("seconds",0)
 if st=="spot":
  target=set(spot_question(m)["targets"]);picked=payload.get("squares",[])
  if not isinstance(picked,list) or len(picked)>32 or any(not isinstance(s,str) or not re.fullmatch(r"[a-h][1-8]",s) for s in picked):raise ValueError("Invalid squares")
  picked=set(picked);correct=picked==target
  assisted=payload.get("assisted") is True
  record(c,sid,m,st,correct,assisted,seconds,
         {"picked":sorted(picked),"expected":sorted(target),"assisted":assisted})
  return {"correct":correct,"targets":sorted(target),"missed":sorted(target-picked),
          "extra":sorted(picked-target),"spotKind":spot_question(m)["kind"],
          "next":exercise(sid)}
 if st=="move":
  b,mv=legal_move(m["fen"],payload.get("uci"))
  result=grade(m["fen"],mv,m["best"],depth=11);assisted=bool(payload.get("assisted",False))
  record(c,sid,m,st,result["accepted"],assisted,seconds,{"uci":mv.uci()})
  return {"correct":result["accepted"],"message":result["explanation"],
          "yourSan":result["played_san"],"best":result["best_san"],
          "lesson":result["lesson"],"visual":result["visual"],
          "next":exercise(sid)}
 if st=="predict":
  b,count=prediction_board(c,sid,m)
  _,mv=legal_move(b.fen(),payload.get("uci"));path=find_engine()
  if not path:raise RuntimeError("Stockfish unavailable")
  with chess.engine.SimpleEngine.popen_uci(path,timeout=25) as eng:
   info=eng.analyse(b,chess.engine.Limit(depth=11))
  best=b.san(info["pv"][0]);result=grade(b.fen(),mv,best,depth=11)
  record(c,sid,m,st,result["accepted"],payload.get("assisted") is True,seconds,
         {"uci":mv.uci(),"step":count+1,"assisted":payload.get("assisted") is True})
  return {"correct":result["accepted"],"yourSan":result["played_san"],
          "expected":result["best_san"],"best":result["best_san"],
          "message":("You found a strong continuation." if result["accepted"] else
                     "The opponent has a stronger response. Review the concrete variation below."),
          "lesson":result["lesson"],"visual":result["visual"],
          "next":exercise(sid)}
 if st=="learn":
  previous=c.execute("SELECT details FROM lab_events WHERE session_id=? AND stage='move' AND game_id=? AND ply=? ORDER BY id DESC LIMIT 1",(sid,m["gameId"],m["ply"])).fetchone()
  b=chess.Board(m["fen"]);uci=json.loads(previous[0])["uci"] if previous else b.parse_san(m["best"]).uci()
  _,mv=legal_move(m["fen"],uci);result=grade(m["fen"],mv,m["best"],depth=11)
  from contextual_reading import position_reading,position_concepts
  # Don't recycle the same passage throughout a learner's recent exercises.
  recent=c.execute("""SELECT details FROM lab_events
      WHERE username='player' AND stage='learn' ORDER BY id DESC LIMIT 20""").fetchall()
  previously_shown=set()
  for r in recent:
   try:
    prior=json.loads(r["details"])
    previously_shown.update(prior.get("source_chunks",[]))
    previously_shown.update(prior.get("source_quotes",[]))
   except (ValueError,TypeError):pass
  sources=position_reading(m["fen"],result["best_san"],result["played_san"],
         limit=2,exclude_books=previously_shown,con=c)
  record(c,sid,m,st,True,True,seconds,
         {"revealed":True,"source_chunks":[x["chunkId"] for x in sources],
          "source_quotes":[x["quoteHash"] for x in sources]})
  grounded=position_concepts(m["fen"],result["best_san"],result["played_san"])
  return {"lesson":result["lesson"],"visual":result["visual"],"best":result["best_san"],
          "bookContext":grounded,
          "sources":[{"title":x["title"],"url":x["url"],"body":x["body"],
                      "reason":x["reason"],"concepts":x["concepts"]} for x in sources],
          "next":exercise(sid)}
 if st=="prove":
  alt=transfer(c,m,sid)
  if alt is None:
   record(c,sid,m,st,False,True,seconds,{"no_transfer":True});advance(c,sid,sess)
   return {"correct":None,"message":"No different unseen position was available.","next":exercise(sid)}
  _,mv=legal_move(alt["fen"],payload.get("uci"));result=grade(alt["fen"],mv,alt["best"],depth=11)
  record(c,sid,alt,st,result["accepted"],False,seconds,{"uci":mv.uci(),"sourceGame":m["gameId"]})
  advance(c,sid,sess)
  return {"correct":result["accepted"],"message":result["explanation"],"visual":result["visual"],"lesson":result["lesson"],"next":exercise(sid)}
 raise ValueError("Invalid stage")
def positional(fen):
 b=chess.Board(fen)
 if not b.is_valid():raise ValueError("Invalid chess position")
 files=defaultdict(lambda:{True:[],False:[]})
 for sq,p in b.piece_map().items():
  if p.piece_type==chess.PAWN:files[chess.square_file(sq)][p.color].append(sq)
 feats=[]
 def add(kind,sq,side,label):feats.append({"type":kind,"square":chess.square_name(sq),"side":side,"label":label})
 for sq,p in b.piece_map().items():
  if p.piece_type!=chess.PAWN:continue
  f=chess.square_file(sq);r=chess.square_rank(sq);side="White" if p.color else "Black"
  if len(files[f][p.color])>1:add("doubled pawns",sq,side,"Multiple friendly pawns share this file.")
  if not any(files[k][p.color] for k in (f-1,f+1) if 0<=k<8):add("isolated pawn",sq,side,"No adjacent-file friendly pawns can support this pawn.")
  if not any((chess.square_rank(e)>r if p.color else chess.square_rank(e)<r) for k in (f-1,f,f+1) if 0<=k<8 for e in files[k][not p.color]):
   add("passed pawn",sq,side,"No opposing pawn on this or adjacent files lies ahead.")
 for f in range(8):
  a=len(files[f][True]);z=len(files[f][False]);sq=chess.square(f,0)
  if not a and not z:add("open file",sq,"Both","This file has no pawns.")
  elif not a or not z:add("half-open file",sq,"One side","Only one side has pawns on this file.")
 for sq,p in b.piece_map().items():
  if p.piece_type==chess.KNIGHT and 2<=chess.square_file(sq)<=5:
   advanced=chess.square_rank(sq)>=3 if p.color else chess.square_rank(sq)<=4
   support=any(q.color==p.color and q.piece_type==chess.PAWN and sq in b.attacks(s) for s,q in b.piece_map().items())
   challenge=any(q.color!=p.color and q.piece_type==chess.PAWN and sq in b.attacks(s) for s,q in b.piece_map().items())
   if advanced and support and not challenge:add("knight outpost",sq,"White" if p.color else "Black","Supported central knight not currently attacked by enemy pawns.")
 # Pawn chains: this pawn supports a friendly pawn diagonally forward.
 for sq,p in b.piece_map().items():
  if p.piece_type==chess.PAWN:
   for target in b.attacks(sq):
    defended=b.piece_at(target)
    if defended and defended.color==p.color and defended.piece_type==chess.PAWN:
     add("pawn chain",target,"White" if p.color else "Black",
         "This pawn is supported by a friendly pawn on "+chess.square_name(sq)+".")
 # Restricted bishops are factual mobility observations, not a verdict.
 for sq,p in b.piece_map().items():
  if p.piece_type not in (chess.BISHOP,chess.ROOK):continue
  mobility=sum(1 for k in b.attacks(sq) if not b.piece_at(k) or b.piece_at(k).color!=p.color)
  if p.piece_type==chess.BISHOP and mobility<=3:
   add("restricted bishop",sq,"White" if p.color else "Black",
       "This bishop has "+str(mobility)+" currently available destination squares; check blocking friendly pawns.")
  if p.piece_type==chess.ROOK and not files[chess.square_file(sq)][True] and not files[chess.square_file(sq)][False]:
   add("rook on open file",sq,"White" if p.color else "Black",
       "This rook is on a file with no pawns.")
 # Basic geometric king opposition: when kings face one empty square
 # between them, the player to move normally must yield in pure K+P endings.
 wk,bk=b.king(True),b.king(False)
 if wk is not None and bk is not None:
  dx=abs(chess.square_file(wk)-chess.square_file(bk))
  dy=abs(chess.square_rank(wk)-chess.square_rank(bk))
  if (dx==2 and dy==0) or (dy==2 and dx==0):
   for side,square in (("White",wk),("Black",bk)):
    add("king opposition",square,side,
        "The kings face each other with one intervening square. Turn-to-move and pawn tempo determine who must yield.")
 for color in (True,False):
  king=b.king(color)
  if king is None:continue
  shields=sum(1 for s in b.attacks(king) if b.piece_at(s) and b.piece_at(s).color==color and b.piece_at(s).piece_type==chess.PAWN)
  if not shields and any(p.piece_type==chess.QUEEN for p in b.piece_map().values()):
   add("king exposure",king,"White" if color else "Black","No adjacent friendly pawn shelter; examine forcing checks.")
 return {"fen":fen,"features":feats[:80],"note":"Geometric strategic clues, not a complete engine evaluation."}
def skills():
 c=db();ensure(c);rows=c.execute("SELECT * FROM lab_events WHERE username='player'").fetchall()
 result=[]
 for topic in THEMES:
  a=[r for r in rows if r["topic"]==topic and r["stage"] in ("spot","move","predict","prove") and not r["assisted"]]
  proof=[r for r in a if r["stage"]=="prove"]
  result.append({"topic":topic,"attempts":len(a),"correct":sum(r["correct"] for r in a),
   "accuracy":round(100*sum(r["correct"] for r in a)/len(a)) if a else None,
   "transferAccuracy":round(100*sum(r["correct"] for r in proof)/len(proof)) if proof else None,
   "transferAttempts":len(proof),
   "averageSeconds":round(sum(r["seconds"] for r in a)/len(a),1) if a else None})
 mastered=c.execute("SELECT COUNT(*) FROM lab_mastery WHERE streak>=2").fetchone()[0]
 return {"skills":result,"mastered":mastered,"assessments":sum(r["attempts"] for r in result),
 "method":"Unaided skill, elapsed seconds and separate unseen-position transfer checks."}
def campaigns():
 c=db();all_items=items(c);weights=Counter()
 for m in all_items:weights[m["topic"]]+=WEIGHT.get(m["timeClass"],.5)
 score={r["topic"]:r for r in skills()["skills"]}
 return [{"topic":topic,"priority":round(weight,1),"available":sum(x["topic"]==topic and x["due"] for x in all_items),
   "accuracy":score[topic]["accuracy"],"title":topic.title(),"description":THEMES.get(topic,"Review your games."),
   "goal":80} for topic,weight in weights.most_common()]
def board_question(fen,question,candidate=None):
 if not isinstance(fen,str) or len(fen)>150:raise ValueError("Invalid board")
 b=chess.Board(fen)
 if not b.is_valid():raise ValueError("Invalid position")
 q=" ".join(str(question or "").split())[:500]
 if len(q)<3:raise ValueError("Ask a specific question")
 pos=positional(fen);s=pos["features"]
 if any(w in q.lower() for w in ("pawn","structure","file")):
  s=[x for x in s if "pawn" in x["type"] or "file" in x["type"]]
 elif "king" in q.lower():s=[x for x in s if "king" in x["type"]]
 elif "knight" in q.lower():s=[x for x in s if "knight" in x["type"]]
 elif "bishop" in q.lower():s=[x for x in s if "bishop" in x["type"]]
 elif "rook" in q.lower():s=[x for x in s if "rook" in x["type"] or "file" in x["type"]]
 elif "weak square" in q.lower():s=[x for x in s if x["type"] in ("knight outpost","isolated pawn","king exposure")]
 path=find_engine()
 if not path:raise RuntimeError("Stockfish unavailable")
 with chess.engine.SimpleEngine.popen_uci(path,timeout=25) as eng:info=eng.analyse(b,chess.engine.Limit(depth=11))
 pv=info.get("pv",[]);best=b.san(pv[0]) if pv else None
 visual=annotate(fen,best,best_pv=pv) if best else None
 comparison=None
 if candidate:
  if not isinstance(candidate,str) or len(candidate)>15:raise ValueError("Move notation is invalid")
  try:mv=b.parse_san(candidate.strip())
  except ValueError:raise ValueError("Enter a legal move in chess notation, such as Nf3 or exd5")
  assessed=grade(fen,mv,best,depth=11)
  comparison=assessed["lesson"]
  visual=assessed["visual"]
 answer="For this exact position, Stockfish's leading move at depth 11 is "+str(best)+"."
 if comparison:
  answer += ("\n\nYour candidate "+candidate+": "+comparison["comparison"]+
             "\n\nWhy: "+comparison["principle"]+
             "\n\nBest continuation: "+comparison["bestLine"])
  if comparison["yourLine"]:
   answer += "\nYour continuation: "+comparison["yourLine"]
 if s:answer+="\n\nVerified board features:\n"+"\n".join("- "+x["label"]+" ("+x["square"]+")" for x in s[:6])
 else:answer+="\n\nI cannot verify a feature matching your question; examine forcing checks and captures."
 return {"question":q,"answer":answer,"best":best,"features":s[:14],"visual":visual,
   "comparison":comparison,
  "note":"Position-grounded geometry and limited-depth Stockfish, not an unrestricted language model."}
def lesson(topic):
 if topic not in THEMES:raise ValueError("Unknown skill topic")
 c=db()
 examples=[m for m in items(c) if m["topic"]==topic]
 examples.sort(key=lambda m:-WEIGHT.get(m["timeClass"],0.5))
 example=None
 refs=[]
 if examples:
  m=examples[0]
  from contextual_reading import position_reading
  refs=position_reading(m["fen"],m["best"],m["move"],limit=2,con=c)
  example={"fen":m["fen"],"color":m["color"],"opponent":m["opponent"],
    "best":m["best"],"played":m["move"],
    "visual":annotate(m["fen"],m["best"],m["move"])}
 return {"topic":topic,"principle":THEMES[topic],
  "sources":[{"title":r["title"],"url":r["url"],"passage":r["body"],
              "reason":r["reason"],"concepts":r["concepts"]} for r in refs],
  "example":example}
def save_note(sid,note):
 note=" ".join(str(note or "").split())
 if not 5<=len(note)<=1000:raise ValueError("Write a 5–1000 character takeaway")
 c=db();ensure(c);sess,m=context(c,sid)
 if not m:raise ValueError("Session completed")
 c.execute("""INSERT INTO lab_notes VALUES(?,?,?,?,?,?) ON CONFLICT(username,session_id,game_id,ply)
 DO UPDATE SET note=excluded.note,at=excluded.at""",
 ("player",sid,m["gameId"],m["ply"],note,stamp()));c.commit()
 return {"saved":True}
