"""Opening curriculum with dual-color study, spaced review, and novel ECO transfer.

Lessons are derived from independently licensed ECO positions; evaluations use
Stockfish. Completion is not mastery: distinct records track factual knowledge,
unassisted repertoire recall, delayed retention and held-out transfer.
"""
from __future__ import annotations
import datetime as dt
import math
import sqlite3
import secrets
from collections import Counter
import chess,chess.engine
import eco_catalog as eco
from chess_grind import db
from game_analysis import find_engine
from engine_grade import engine_gap
from opening_coach import snapshot,_explain_move,changes
from opening_theory_cards import theory,FAMILIES
from opening_repertoire import USER

def ensure(con):
 con.executescript("""CREATE TABLE IF NOT EXISTS opening_course_progress(
 username TEXT NOT NULL, color TEXT NOT NULL, opening_id INTEGER NOT NULL,
 review_due TEXT NOT NULL, interval_days INTEGER NOT NULL DEFAULT 0,
 ease REAL NOT NULL DEFAULT 2.5, repetitions INTEGER NOT NULL DEFAULT 0,
 knowledge_passes INTEGER NOT NULL DEFAULT 0, last_grade INTEGER,
 last_review TEXT, PRIMARY KEY(username,color,opening_id));
 CREATE TABLE IF NOT EXISTS opening_course_attempts(
 id INTEGER PRIMARY KEY AUTOINCREMENT,username TEXT NOT NULL,
 color TEXT NOT NULL,opening_id INTEGER NOT NULL,
 role TEXT NOT NULL,position_key TEXT NOT NULL,uci TEXT NOT NULL,
 accepted INTEGER NOT NULL, assisted INTEGER NOT NULL,
 regret_cp INTEGER, created_at TEXT NOT NULL);
 CREATE INDEX IF NOT EXISTS opening_course_attempt_index
 ON opening_course_attempts(username,color,opening_id,role);
 CREATE TABLE IF NOT EXISTS opening_course_rounds(
 round_id TEXT PRIMARY KEY, username TEXT NOT NULL, color TEXT NOT NULL,
 opening_id INTEGER NOT NULL, role TEXT NOT NULL, position_key TEXT NOT NULL,
 tries INTEGER NOT NULL DEFAULT 0, finished INTEGER NOT NULL DEFAULT 0,created_at TEXT NOT NULL);
 CREATE TABLE IF NOT EXISTS opening_course_transfer_reservations(
 username TEXT NOT NULL, color TEXT NOT NULL,opening_id INTEGER NOT NULL,
 position_key TEXT NOT NULL, fen TEXT NOT NULL, target_uci TEXT NOT NULL,
 PRIMARY KEY(username,color,opening_id));
 """)
 con.commit()

def now():
 return dt.datetime.now(dt.timezone.utc)

def _iso(day=None):
 return (day or now()).isoformat(timespec="seconds")

def _key(fen):
 return " ".join(fen.split()[:4])

def _color(v):
 if v not in ("White","Black"):raise ValueError("Choose White or Black")
 return v

def _entry(i):
 r=eco.get(i)
 return r

def _my_decisions(r,color):
 turn=chess.WHITE if color=="White" else chess.BLACK
 result=[]
 for i,step in enumerate(r["steps"]):
  board=chess.Board(step["before"])
  if board.turn!=turn:continue
  move=chess.Move.from_uci(step["uci"])
  result.append({"index":i,"fen":board.fen(),"uci":move.uci(),"san":board.san(move),
   "step":i+1,"key":_key(board.fen())})
 return result

def _plan(r,color):
 decisions=_my_decisions(r,color)
 side="White" if color=="White" else "Black"
 opponents=[s for s in r["steps"] if chess.Board(s["before"]).turn!=(color=="White")]
 opening_name=r["name"]
 first_decisions=[d["san"] for d in decisions[:3]]
 opp=[s["san"] for s in opponents[:3]]
 goal=("You move first. Establish a central presence, develop pieces, and be ready to meet Black's specific response."
   if color=="White" else
   "You respond to White's first move. Challenge the center without neglecting development and king safety.")
 return {"opening":opening_name,"eco":r["eco"],"color":color,
    "goal":goal,"yourMoves":first_decisions,"opponentMoves":opp,
    "question":"After the opponent's latest move, what central squares, undefended pieces and developing moves changed?",
    "remember":"Understand what each of your moves accomplishes, and what your opponent may do next. Do not memorize moves without the plan."}

def catalog(color="White",q="",limit=80):
 _color(color)
 base=eco.search(q,max(1,min(int(limit),80)))
 return {"color":color,"total":base["total"],"matching":base["matching"],
   "openings":base["openings"],"source":base["source"],
   "note":"ECO names identify a cataloged position. The same opening can be reached by transposition. Both White and Black have equal lesson and assessment access."}

def lesson(opening_id,color="White"):
 _color(color)
 r=_entry(opening_id)
 decisions=_my_decisions(r,color)
 if not decisions:raise ValueError("This ECO entry has no move by that color. Select a longer named variation.")
 steps=r["steps"]
 plan=_plan(r,color)
 explained=[]
 for d in decisions[:6]:
  b=chess.Board(d["fen"]);m=chess.Move.from_uci(d["uci"])
  following=steps[d["index"]+1]["san"] if d["index"]+1<len(steps) else None
  features=snapshot(b)
  effects=changes(b,m)
  explained.append({"san":d["san"],"uci":m.uci(),"fen":d["fen"],"afterFen":steps[d["index"]]["fen"],
    "ply":d["step"],"plan":" ".join(_explain_move(b,m)+effects),
    "opponentReply":following,
    "prompt":"Why play "+d["san"]+" in this position, and what would you prepare against "+
       (following or "the opponent's next move")+"?",
    "features":features})
 con=db();ensure(con)
 try:
  progress=_progress(con,int(opening_id),color)
 finally:con.close()
 return {"id":r["id"],"eco":r["eco"],"name":r["name"],"pgn":r["pgn"],
   "color":color,"source":eco.SOURCE,"plan":plan,"steps":steps[:30],
   "decisions":explained,"progress":progress,"theory":theory(r["name"],color),
   "lesson":"Read the board → understand every response → reconstruct the plan → recall after delay → prove transfer on a held-out line.",
   "warning":"A named ECO sequence is descriptive, not necessarily an engine-perfect repertoire. Mastery checks are distinct; this lesson is not proof of real-match mastery."}

def _progress(con,opening_id,color):
 row=con.execute("""SELECT * FROM opening_course_progress WHERE
 username=? AND color=? AND opening_id=?""",(USER,color,opening_id)).fetchone()
 x=dict(row) if row else None
 attempts=con.execute("""SELECT role,accepted,assisted,created_at FROM opening_course_attempts
 WHERE username=? AND color=? AND opening_id=? ORDER BY id""",(USER,color,opening_id)).fetchall()
 kinds=Counter(a["role"] for a in attempts)
 correct_transfer=sum(a["accepted"] and not a["assisted"] for a in attempts if a["role"]=="transfer")
 transfer_attempts=sum(a["role"]=="transfer" for a in attempts)
 successful_days={a["created_at"][:10] for a in attempts if
   a["role"]=="recall" and a["accepted"] and not a["assisted"]}
 delayed_recall=len(successful_days)>=2
 due=not x or x["review_due"]<=_iso()
 # Mastery requires distinct-day recall, a knowledge check AND distinct-position transfer.
 stage=("transfer-demonstrated" if correct_transfer and delayed_recall and x and x["knowledge_passes"]>=1
        else "transfer-practiced" if correct_transfer else "reviewing" if x and x["repetitions"] else "learning")
 return {"stage":stage,"due":due,"nextDue":x["review_due"] if x else None,
    "intervalDays":x["interval_days"] if x else 0,
    "repetitions":x["repetitions"] if x else 0,
    "knowledgePasses":x["knowledge_passes"] if x else 0,
     "delayedIndependentRecall":delayed_recall,
    "transferAttempts":transfer_attempts,"independentTransferPasses":correct_transfer,
    "totalAttempts":len(attempts),"measuredAgainst":"same-opening ECO variation, not a completely unrelated opening"}

def progress(opening_id,color="White"):
 _color(color);_entry(opening_id)
 con=db();ensure(con)
 try:return _progress(con,int(opening_id),color)
 finally:con.close()

def dashboard():
 con=db();ensure(con)
 try:
  result={}
  for color in ("White","Black"):
   rows=con.execute("""SELECT opening_id FROM opening_course_progress
    WHERE username=? AND color=?""",(USER,color)).fetchall()
   stats=[_progress(con,r["opening_id"],color) for r in rows]
   result[color]={"studying":len(rows),"due":sum(x["due"] for x in stats),
    "transferDemonstrated":sum(x["stage"]=="transfer-demonstrated" for x in stats),
    "progress":[{"openingId":r["opening_id"],**state} for r,state in zip(rows,stats)]}
  return {"colors":result,"catalog":eco.total(),"source":eco.SOURCE,
    "guidance":"Balanced White and Black training. Repertoire recall, factual explanations, delayed review and new-variation transfer are measured separately."}
 finally:con.close()

def _round(con,opening_id,color,role,fen):
 token=secrets.token_hex(14)
 con.execute("INSERT INTO opening_course_rounds VALUES(?,?,?,?,?,?,0,0,?)",
             (token,USER,color,int(opening_id),role,_key(fen),_iso()))
 con.commit()
 return token

def _get_round(con,token,opening_id,color,role,fen):
 import re
 if not isinstance(token,str) or not re.fullmatch("[a-f0-9]{28}",token):
  raise ValueError("Invalid study question")
 row=con.execute("SELECT * FROM opening_course_rounds WHERE round_id=? AND username=? AND opening_id=? AND color=? AND role=? AND position_key=?",
  (token,USER,int(opening_id),color,role,_key(fen))).fetchone()
 if row is None:raise ValueError("Study question does not match this position")
 if row["finished"]:raise ValueError("This question is completed. Begin a new one.")
 return row

def review_question(opening_id,color="White"):
 _color(color)
 entry=_entry(opening_id)
 choices=_my_decisions(entry,color)
 if not choices:raise ValueError("No candidate by this side in the chosen line")
 con=db();ensure(con)
 try:
  attempted=con.execute("""SELECT position_key FROM opening_course_attempts
  WHERE username=? AND color=? AND opening_id=? AND role='recall'""",
  (USER,color,int(opening_id))).fetchall()
  used={r[0] for r in attempted}
 finally:con.close()
 choice=next((d for d in choices if d["key"] not in used),choices[len(used)%len(choices)])
 b=chess.Board(choice["fen"])
 con=db();ensure(con)
 try:token=_round(con,opening_id,color,"recall",b.fen())
 finally:con.close()
 return {"roundId":token,"maxAttempts":3,"id":entry["id"],"eco":entry["eco"],"name":entry["name"],
   "color":color,"fen":b.fen(),"prompt":"Play the move in your studied "+entry["name"]+
   " line for "+color+". Name the purpose before playing.",
   "role":"recall","side":color,
   "note":"Tests exact line recall; not independent transfer and not necessarily objectively optimal."}

def _engine_score(board,selected):
 path=find_engine()
 if not path:raise RuntimeError("Stockfish is required for independently graded transfer tests")
 with chess.engine.SimpleEngine.popen_uci(path,timeout=40) as eng:
  eng.configure({"Threads":1,"Hash":32})
  search=chess.engine.Limit(depth=11)
  best=eng.analyse(board,search)
  if not best.get("pv"):raise RuntimeError("No engine recommendation")
  target=best["pv"][0]
  other=best if selected==target else eng.analyse(board,search,root_moves=[selected])
  if not other.get("pv"):raise RuntimeError("Move evaluation unavailable")
  best_cp=best["score"].pov(board.turn).score(mate_score=20000)
  cp=other["score"].pov(board.turn).score(mate_score=20000)
  gap=engine_gap(best["score"].pov(board.turn),other["score"].pov(board.turn))
  return {"gapCp":gap,"accepted":gap<=65,"bestUci":target.uci(),
    "bestSan":board.san(target),"yourSan":board.san(selected),
    "reasons":_explain_move(board,target),
    "reply":(lambda info: board.variation_san(info[:min(4,len(info))]))(best["pv"])}

def _write_attempt(con,opening_id,color,role,fen,uci,accepted,assisted,gap):
 con.execute("""INSERT INTO opening_course_attempts
 (username,color,opening_id,role,position_key,uci,accepted,assisted,regret_cp,created_at)
 VALUES(?,?,?,?,?,?,?,?,?,?)""",
 (USER,color,int(opening_id),role,_key(fen),uci,int(accepted),int(assisted),gap,_iso()))

def _update_schedule(con,opening_id,color,grade,knowledge=False):
 entry=con.execute("""SELECT * FROM opening_course_progress
 WHERE username=? AND color=? AND opening_id=?""",(USER,color,int(opening_id))).fetchone()
 old=dict(entry) if entry else None
 quality=int(grade);previous=old["repetitions"] if old else 0
 ease=old["ease"] if old else 2.5
 if quality<3:repetitions=0;days=1
 elif old and old["review_due"]>_iso() and previous>0:
  # Repeated same-day answers do not advance the review clock.
  repetitions=previous
  days=max(1,old["interval_days"])
 else:
  repetitions=previous+1
  days=1 if repetitions==1 else 3 if repetitions==2 else max(4,round((old["interval_days"] or 3)*ease))
 ease=max(1.3,min(3.0,ease+(0.1-(5-quality)*(0.08+(5-quality)*0.02))))
 due=(old["review_due"] if old and quality>=3 and
      old["review_due"]>_iso() and previous>0 else
      _iso(now()+dt.timedelta(days=days)))
 passes=(old["knowledge_passes"] if old else 0)+(1 if knowledge else 0)
 con.execute("""INSERT INTO opening_course_progress
 (username,color,opening_id,review_due,interval_days,ease,repetitions,knowledge_passes,last_grade,last_review)
 VALUES(?,?,?,?,?,?,?,?,?,?)
 ON CONFLICT(username,color,opening_id) DO UPDATE SET
 review_due=excluded.review_due,interval_days=excluded.interval_days,ease=excluded.ease,
 repetitions=excluded.repetitions,knowledge_passes=excluded.knowledge_passes,
 last_grade=excluded.last_grade,last_review=excluded.last_review""",
 (USER,color,int(opening_id),due,days,ease,repetitions,passes,quality,_iso()))
 return {"due":due,"intervalDays":days,"repetitions":repetitions}

def submit(opening_id,color,role,fen,uci,assisted=False,explain_choice=None,round_id=None):
 _color(color);entry=_entry(opening_id)
 if role not in ("recall","transfer"):raise ValueError("Unsupported assessment role")
 if not isinstance(assisted,bool):raise ValueError("Invalid assistance flag")
 if not isinstance(fen,str) or len(fen)>150:raise ValueError("Invalid position")
 board=chess.Board(fen)
 if not board.is_valid() or ("White" if board.turn else "Black")!=color:
  raise ValueError("This position must be your side to move")
 if not isinstance(uci,str):raise ValueError("Select a legal move")
 try:move=chess.Move.from_uci(uci)
 except ValueError:raise ValueError("Select a legal move")
 if move not in board.legal_moves:raise ValueError("Illegal move")
 con=db();ensure(con)
 try:
  active=_get_round(con,round_id,opening_id,color,role,board.fen()) if round_id else None
  attempts=(active["tries"]+1) if active else 1
  if role=="recall":
   candidates=_my_decisions(entry,color)
   correct=next((d for d in candidates if d["key"]==_key(board.fen())),None)
   if correct is None:raise ValueError("Not a studied recall position")
   accepted=move.uci()==correct["uci"]
   _write_attempt(con,opening_id,color,role,board.fen(),move.uci(),
     accepted and (active is None or attempts==1),assisted,None)
   if active is None:
    result={"accepted":accepted,"yourSan":board.san(move),"studiedSan":correct["san"],
      "interpretation":"Studied line recalled." if accepted else "Legal alternative; not this recorded move."}
    _update_schedule(con,opening_id,color,4 if accepted and not assisted else 2)
   else:
    finished=bool(accepted or attempts>=3)
    con.execute("UPDATE opening_course_rounds SET tries=?,finished=? WHERE round_id=?",
      (attempts,int(finished),round_id))
    result={"accepted":bool(accepted and not assisted),
      "yourSan":board.san(move),"attemptNumber":attempts,
      "remaining":max(0,3-attempts),"finished":finished,
      "retry":not finished,"revealed":bool(not accepted and finished)}
    if finished:
     # Only an independent first-try answer advances recall retention.
     _update_schedule(con,opening_id,color,4 if accepted and not assisted and attempts==1 else 2)
     result["studiedSan"]=correct["san"]
     result["studiedUci"]=correct["uci"]
     if accepted:
      result["interpretation"]="Yes, you found the studied continuation. "+(
       "First-try independent recall." if attempts==1 else
       "You found it after a retry; keep practicing the reason behind the move.")
     else:
      # Historic ECO move and engine-best can differ. Reveal both honestly.
      evaln=_engine_score(board,move)
      result.update({"bestSan":evaln["bestSan"],"bestUci":evaln["bestUci"],
        "reply":evaln["reply"],"reasons":evaln["reasons"]})
      result["interpretation"]=("Three attempts completed. The studied move is "+
        correct["san"]+"; Stockfish's stronger continuation is "+
        evaln["bestSan"]+". Those can be different moves.")
    else:
     result["interpretation"]=("Not quite — try again. Check the center, threats and "+
        "piece development. "+str(3-attempts)+" attempt(s) remain. No solution revealed.")
  else:
   reserved=con.execute("""SELECT position_key,fen,target_uci FROM opening_course_transfer_reservations
     WHERE username=? AND color=? AND opening_id=?""",(USER,color,int(opening_id))).fetchone()
   if reserved is None or reserved["position_key"]!=_key(board.fen()):
    raise ValueError("No matching held-out transfer position assigned")
   already=con.execute("""SELECT 1 FROM opening_course_attempts
    WHERE username=? AND color=? AND opening_id=? AND role='transfer' AND position_key=?""",
     (USER,color,int(opening_id),_key(board.fen()))).fetchone()
   if already and active is None:raise ValueError("This board has already been tested as transfer")
   score=_engine_score(board,move)
   accepted=bool(score["accepted"] and not assisted)
   _write_attempt(con,opening_id,color,role,board.fen(),move.uci(),
     accepted and (active is None or attempts==1),assisted,score["gapCp"])
   if active is None:
    result={**score,"accepted":accepted,
      "expectedTheorySan":board.san(chess.Move.from_uci(reserved["target_uci"])),
      "interpretation":"Engine-competitive move." if accepted else "Not competitive at the current search depth."}
    finished=True
   else:
    finished=bool(accepted or attempts>=3)
    con.execute("UPDATE opening_course_rounds SET tries=?,finished=? WHERE round_id=?",
      (attempts,int(finished),round_id))
    result={"accepted":accepted,"yourSan":score["yourSan"],
      "attemptNumber":attempts,"remaining":max(0,3-attempts),
      "finished":finished,"retry":not finished,
      "revealed":bool(not accepted and finished)}
    if finished:
     result.update(score)
     result["accepted"]=accepted
     result["expectedTheorySan"]=board.san(chess.Move.from_uci(reserved["target_uci"]))
     result["interpretation"]=("Great, this alternative is competitive with Stockfish." if accepted else
       "Three attempts completed. Stockfish prefers "+score["bestSan"]+
       ". Review its continuation, then practice a new position.")
    else:
     result["interpretation"]=("Not quite — try another legal move. Look at the "+
       "opponent's threats, center, and king safety. "+
       str(3-attempts)+" attempt(s) remain. The solution is hidden.")
   if finished:
    con.execute("DELETE FROM opening_course_transfer_reservations WHERE username=? AND color=? AND opening_id=?",
      (USER,color,int(opening_id)))
  con.commit()
  result["progress"]=_progress(con,int(opening_id),color)
  return result
 finally:con.close()

def knowledge(opening_id,color,answer):
 """Legacy SAN recall endpoint: NEVER unlocks conceptual-knowledge credit."""
 _color(color);entry=_entry(opening_id)
 choices=_my_decisions(entry,color)
 if not choices:raise ValueError("No available decision")
 question=choices[0]
 if not isinstance(answer,str):raise ValueError("Invalid answer")
 correct=answer.strip().lower()==question["san"].lower()
 con=db();ensure(con)
 try:
  current=con.execute("""SELECT 1 FROM opening_course_progress
    WHERE username=? AND color=? AND opening_id=?""",(USER,color,int(opening_id))).fetchone()
  if not current:
   con.execute("""INSERT INTO opening_course_progress
    (username,color,opening_id,review_due,interval_days,ease,repetitions,knowledge_passes)
    VALUES(?,?,?,?,?,?,?,?)""",(USER,color,int(opening_id),_iso(),0,2.5,0,0))
  _write_attempt(con,opening_id,color,"syntax",question["fen"],answer,correct,False,None)
  con.commit()
  return {"correct":correct,"answer":question["san"],
    "reason":"This is only SAN/move-order recall and does not count toward conceptual mastery.",
    "progress":_progress(con,int(opening_id),color)}
 finally:con.close()

def transfer_question(opening_id,color):
 """Hold out a DISTINCT, previously untested sibling variation and lock it in SQLite.

    Excludes positions from the displayed ECO example, previously answered
    course assessments, and any already reserved transfer board. A transfer
    is label-specific: not an unseen random chess position.
 """
 _color(color);entry=_entry(opening_id)
 ownkeys={d["key"] for d in _my_decisions(entry,color)}
 con=db();ensure(con)
 try:
  existing=con.execute("""SELECT position_key,fen FROM opening_course_transfer_reservations
  WHERE username=? AND color=? AND opening_id=?""",(USER,color,int(opening_id))).fetchone()
  if existing:
   token=_round(con,opening_id,color,"transfer",existing["fen"])
   return {"roundId":token,"maxAttempts":3,"fen":existing["fen"],"color":color,"openingId":int(opening_id),
      "role":"transfer","prompt":"An unrehearsed branch in the same opening family. Choose the strongest continuation without help.",
      "disclosure":"This position is held out from this course's worked example, but may resemble positions seen elsewhere."}
  attempted={row[0] for row in con.execute("""SELECT position_key FROM opening_course_attempts
   WHERE username=?""",(USER,))}
  reserved={row[0] for row in con.execute("""SELECT position_key FROM opening_course_transfer_reservations
   WHERE username=?""",(USER,))}
  candidates=[]
  for sibling in eco.database()[0]:
   if sibling["id"]==entry["id"] or sibling["eco"][:2]!=entry["eco"][:2]:continue
   for d in _my_decisions(sibling,color):
    if d["key"] in ownkeys or d["key"] in attempted or d["key"] in reserved:continue
    if d["step"]<3:continue
    if d["fen"]==entry["steps"][-1]["fen"]:continue
    candidates.append((sibling["id"],d))
  # More developed test position first, but deterministic across sessions.
  candidates.sort(key=lambda x:(-x[1]["step"],x[0]))
  if not candidates:
   return {"fen":None,"role":"transfer","reason":"No independent same-family variation is currently available for this ECO entry. This is not a transfer pass."}
  sibling,chosen=candidates[0]
  con.execute("""INSERT INTO opening_course_transfer_reservations
  VALUES(?,?,?,?,?,?)""",(USER,color,int(opening_id),chosen["key"],chosen["fen"],chosen["uci"]))
  con.commit()
  return {"roundId":_round(con,opening_id,color,"transfer",chosen["fen"]),
    "maxAttempts":3,"fen":chosen["fen"],"color":color,"openingId":int(opening_id),
    "role":"transfer","prompt":"Unrehearsed variation from the same ECO family. Choose the best move for "+
     color+" without hints or seeing the line.",
    "disclosure":"New to this training assessment, not guaranteed never seen in other games. The sibling line and solution remain hidden until submission."}
 finally:con.close()

def _concept_parts(opening_id,color):
 """Deterministic side-specific conceptual question, no client-visible key."""
 _color(color);entry=_entry(opening_id)
 main=theory(entry["name"],color)
 target=main["yourPlan"]
 distractors=[]
 # Other opening families are plausible alternatives, unlike easy nonsense.
 for i in range(len(FAMILIES)):
  f=FAMILIES[(int(opening_id)+i)%len(FAMILIES)]
  if f[0]==main["family"]:continue
  alternate=f[1] if color=="White" else f[2]
  if alternate==target or alternate in distractors:continue
  distractors.append(alternate)
  if len(distractors)==3:break
 choices=[target]+distractors
 offset=int(opening_id)%len(choices)
 choices=choices[offset:]+choices[:offset]
 correct=choices.index(target)
 return entry,main,choices,correct

def concept_question(opening_id,color="White"):
 entry,main,choices,correct=_concept_parts(opening_id,color)
 con=db();ensure(con)
 try:token=_round(con,opening_id,color,"concept",_my_decisions(entry,color)[0]["fen"])
 finally:con.close()
 return {"roundId":token,"maxAttempts":3,"id":entry["id"],"color":color,
  "prompt":"Which strategic plan best describes how "+color+
  " should generally approach this named opening family?",
  "options":[{"id":i,"text":item} for i,item in enumerate(choices)],
  "family":main["family"],
  "warning":"This is recognition of a typical family-level plan, not proof of a concrete best move or full strategic understanding. Check the board before applying it."}

def concept_grade(opening_id,color,choice,assisted=False,round_id=None):
 entry,main,choices,correct=_concept_parts(opening_id,color)
 if round_id is not None:
  fen=_my_decisions(entry,color)[0]["fen"]
  con=db();ensure(con)
  try:
   active=_get_round(con,round_id,opening_id,color,"concept",fen)
   attempts=active["tries"]+1
   passed=choice==correct
   finished=bool(passed or attempts>=3)
   con.execute("UPDATE opening_course_rounds SET tries=?,finished=? WHERE round_id=?",
     (attempts,int(finished),round_id))
   con.commit()
   if not finished:
    return {"correct":False,"retry":True,"finished":False,
      "attemptNumber":attempts,"remaining":3-attempts,
      "interpretation":"Not quite — try again. Think about the center, pawn breaks and the opponent's reply.",
      "progress":_progress(con,int(opening_id),color)}
  finally:con.close()
  # A second/third answer is useful practice but does not certify independent
  # first-try conceptual knowledge.
  result=concept_grade(opening_id,color,choice,assisted=(assisted or attempts>1))
  result.update({"finished":True,"retry":False,"attemptNumber":attempts,
    "remaining":max(0,3-attempts),"revealed":not passed})
  return result
 if isinstance(choice,bool) or not isinstance(choice,int) or not 0<=choice<len(choices):
  raise ValueError("Choose a valid plan")
 if not isinstance(assisted,bool):raise ValueError("Invalid assistance")
 passed=choice==correct
 con=db();ensure(con)
 try:
  # A repeated answer cannot multiply knowledge credits.
  existing=con.execute("""SELECT 1 FROM opening_course_attempts
  WHERE username=? AND color=? AND opening_id=? AND role='concept'
  AND accepted=1 AND assisted=0 LIMIT 1""",(USER,color,int(opening_id))).fetchone()
  fen=_my_decisions(entry,color)[0]["fen"]
  _write_attempt(con,opening_id,color,"concept",fen,str(choice),passed,assisted,None)
  current=con.execute("""SELECT 1 FROM opening_course_progress
  WHERE username=? AND color=? AND opening_id=?""",(USER,color,int(opening_id))).fetchone()
  if not current:
   con.execute("""INSERT INTO opening_course_progress
     (username,color,opening_id,review_due,interval_days,ease,repetitions,knowledge_passes)
     VALUES(?,?,?,?,?,?,?,?)""",
     (USER,color,int(opening_id),_iso(),0,2.5,0,0))
  if passed and not assisted and not existing:
   con.execute("""UPDATE opening_course_progress
    SET knowledge_passes=knowledge_passes+1
    WHERE username=? AND color=? AND opening_id=?""",(USER,color,int(opening_id)))
  con.commit()
  return {"correct":passed,"assisted":assisted,
    "correctPlan":choices[correct],"yourChoice":choices[choice],
    "why":"The named-family framework identifies this as a typical plan for "+color+
       ". It may not be best in every subvariation. Verify concrete moves on the board.",
    "progress":_progress(con,int(opening_id),color)}
 finally:con.close()

def personal_openings(color="White"):
 """Identify the deepest named ECO reached in each imported game.

 Only return entries that contain at least one actual decision by this side,
 so an unfinished White move is never mislabeled as a Black lesson.
 """
 from opening_repertoire import _data
 _color(color)
 entries=eco.database()[0]
 ids={(r["eco"],r["name"]):r["id"] for r in entries}
 con=db()
 try:
  games=[g for g in _data(con) if g["color"]==color]
 finally:con.close()
 count=Counter();names={}
 for g in games:
  trace=eco.trace([step["uci"] for step in g["steps"]])
  usable=[]
  for t in trace:
   identifier=ids.get((t["eco"],t["name"]))
   if identifier is None:continue
   record=entries[identifier]
   if _my_decisions(record,color):usable.append((identifier,t))
  if not usable:continue
  opening_id,name=usable[-1]
  count[opening_id]+=1
  names[opening_id]=name
 return {"color":color,"analyzedGames":len(games),
   "namedGames":sum(count.values()),
   "top":[{"id":i,"eco":names[i]["eco"],"name":names[i]["name"],
           "games":n} for i,n in count.most_common(10)],
   "note":"Counts describe the deepest named ECO position reached in the imported PGN. These names are descriptive; they do not endorse the moves or cover unclassified games."}
