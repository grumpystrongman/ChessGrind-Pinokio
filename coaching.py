"""Chess Grind coaching: mistake tagging, practice grading, and book retrieval."""
import datetime as dt
import json
import re
import sqlite3
from collections import Counter
import chess
from chess_grind import db
from game_analysis import dashboard_data

TOPIC_TERMS={
    "forks and double attacks":"fork double attack two pieces knight fork",
    "pins":"pins pinned piece bishop rook queen",
    "checkmate patterns":"checkmate basic mating patterns",
    "forcing checks":"checks forcing moves king safety calculation",
    "missed captures":"captures tactical material winning exchanges",
    "piece safety":"undefended hanging pieces blunder avoid losing material",
    "calculation":"calculate variations candidate moves board visualization",
    "opening decisions":"opening development king safety control of center",
    "endgame technique":"king and pawn ending opposition endgame calculation",
}


def ensure(con):
    con.execute("""CREATE TABLE IF NOT EXISTS puzzle_attempts(
      username TEXT NOT NULL, game_id TEXT NOT NULL, ply INTEGER NOT NULL,
      attempts INTEGER NOT NULL DEFAULT 0, correct INTEGER NOT NULL DEFAULT 0,
      streak INTEGER NOT NULL DEFAULT 0, due TEXT,
      last_attempt TEXT, PRIMARY KEY(username,game_id,ply)
    )""")
    con.commit()

def label(m):
    from motifs import classify
    return classify(m)["topic"]

def _queue(con, username):
    ensure(con)
    data=dashboard_data(username)
    today=dt.date.today().isoformat()
    records={(r["game_id"],r["ply"]):dict(r) for r in con.execute(
      "SELECT * FROM puzzle_attempts WHERE username=?",(username.lower(),))}
    queue=[]
    for m in data["mistakes"]:
        r=records.get((m["gameId"],m["ply"]),{})
        due=r.get("due")
        if due and due>today:
            continue
        x=dict(m)
        x["topic"]=label(m)
        x["evidence"]=__import__("motifs").classify(m)["evidence"]
        x["attempts"]=r.get("attempts",0)
        x["correct"]=r.get("correct",0)
        x["streak"]=r.get("streak",0)
        queue.append(x)
    queue.sort(key=lambda m:(m["attempts"]>0, m.get("timeClass")!="rapid", -m["loss"],m["attempts"]))
    return queue,records,data

def lesson_search(con, topic, limit=3):
    # Rights-cleared local passages, ranked by pretrained dense semantic embeddings.
    phrase=TOPIC_TERMS.get(topic,topic)
    try:
        from semantic_index import status as vector_status, search as semantic_search
        if vector_status()['embedded']:
            hits=semantic_search('Chess instruction: '+phrase+' tactics how to improve',limit=limit)
            if hits:
                for hit in hits:
                    hit['relevance']=hit.get('similarity',0)
                    hit['retrieval']='semantic vector search'
                return hits
    except (ImportError,RuntimeError,ValueError,OSError) as ex:
        print('Semantic search unavailable:',ex)
    # Explicit fallback: keyword search when vectors are missing.
    tokens=[t for t in re.findall(r"[A-Za-z]+",phrase) if len(t)>2]
    if not tokens:return []
    query=" OR ".join(tokens)
    try:
        rows=con.execute("""SELECT books.title,books.author,books.url,chunks.page,
          chunks.body AS body, bm25(chunks_fts) AS relevance
          FROM chunks_fts JOIN chunks ON chunks.rowid=chunks_fts.rowid
          JOIN books ON books.id=chunks.book_id WHERE chunks_fts MATCH ?
          ORDER BY relevance LIMIT ?""",(query,max(40,limit*15))).fetchall()
    except sqlite3.OperationalError:
        return []
    from book_quality import dedup_passages
    return dedup_passages([dict(r) for r in rows],limit)

def training(username="player"):
    con=db();queue,records,data=_queue(con,username)
    all_topics=Counter(label(m) for m in data["mistakes"])
    # Train on every format without allowing the 120 Daily games to drown out Rapid.
    mode_weight={"rapid":3.0,"blitz":1.0,"daily":0.5,"bullet":0.25}
    weighted=Counter()
    for m in data["mistakes"]:
        weighted[label(m)]+=mode_weight.get(m.get("timeClass","rapid"),0.5)
    total=con.execute("""SELECT COALESCE(SUM(attempts),0),COALESCE(SUM(correct),0),
      COALESCE(SUM(CASE WHEN streak>=2 THEN 1 ELSE 0 END),0)
      FROM puzzle_attempts WHERE username=?""",(username.lower(),)).fetchone()
    topic=weighted.most_common(1)[0][0] if weighted else "piece safety"
    return {"queue":queue,"topics":[{"topic":name,"count":all_topics[name],"weighted":round(weight,1)}
      for name,weight in weighted.most_common()],
        "attempts":total[0],"correct":total[1],"mastered":total[2],
        "bookLessons":[], # no global quote without a board-specific context
        "topic":topic, "indexedPassages":data["passages"]}

def submit_answer(payload, username="player"):
    con=db(); ensure(con)
    try:
        game_id=str(payload["gameId"]);ply=int(payload["ply"])
        frm=str(payload["from"]);to=str(payload["to"])
        promo=str(payload.get("promotion","")).lower()
    except (KeyError,ValueError,TypeError):
        return 400,{"error":"Missing or invalid move data"}
    raw=con.execute("""SELECT data FROM game_analysis WHERE username=? AND game_id=?""",
      (username.lower(),game_id)).fetchone()
    if raw is None:
        return 404,{"error":"Game not found"}
    game=json.loads(raw[0])
    mistake=next((m for m in game["mistakes"] if m["ply"]==ply),None)
    if mistake is None:
        return 404,{"error":"Practice position not found"}
    try:
        board=chess.Board(mistake["fen"])
        best=board.parse_san(mistake["best"])
        uci=frm+to+promo
        chosen=chess.Move.from_uci(uci)
    except (ValueError,TypeError):
        return 400,{"error":"Invalid square or promotion"}
    if chosen not in board.legal_moves:
        return 422,{"error":"That move is not legal in this position. Try another square."}
    # Re-evaluate alternate legal moves; equivalent moves should receive full credit.
    from move_grading import grade
    try:
        verdict=grade(mistake['fen'],chosen,mistake['best'])
    except (RuntimeError,ValueError,chess.engine.EngineError,TimeoutError) as error:
        return 503,{'error':'Engine grading unavailable: '+str(error)}
    success=verdict['accepted']
    now=dt.date.today()
    previous=con.execute("""SELECT attempts,correct,streak FROM puzzle_attempts
      WHERE username=? AND game_id=? AND ply=?""",(username.lower(),game_id,ply)).fetchone()
    streak=(previous["streak"] if previous else 0)+1 if success else 0
    days=min(30,2**min(streak,4)) if success else 0
    con.execute("""INSERT INTO puzzle_attempts
      (username,game_id,ply,attempts,correct,streak,due,last_attempt)
      VALUES(?,?,?,?,?,?,?,?)
      ON CONFLICT(username,game_id,ply) DO UPDATE SET
       attempts=excluded.attempts+0+puzzle_attempts.attempts,
       correct=excluded.correct+puzzle_attempts.correct,
       streak=excluded.streak,due=excluded.due,last_attempt=excluded.last_attempt""",
      (username.lower(),game_id,ply,1,int(success),streak,
       (now+dt.timedelta(days=days)).isoformat(),now.isoformat()))
    con.commit()
    return 200,{"correct":success,"played":board.san(chosen),
      "best":verdict["best_san"],
      "topic":label(mistake),"difference_cp":verdict["difference_cp"],
      "lesson":verdict["lesson"],"visual":verdict["visual"],
      "message":verdict["explanation"]+(" Review scheduled." if success else ""),
      "streak":streak}

if __name__=="__main__":
    x=training()
    print(json.dumps({k:v for k,v in x.items() if k!="queue"},indent=2))
    print("queued",len(x["queue"]))

def record_reveal(payload,username="player"):
    """A revealed answer is a missed attempt; it remains due for review."""
    con=db();ensure(con)
    try:
        game_id=str(payload["gameId"]);ply=int(payload["ply"])
    except (KeyError,TypeError,ValueError):
        return 400,{"error":"Missing game position"}
    row=con.execute("""SELECT data FROM game_analysis WHERE username=? AND game_id=?""",
                    (username.lower(),game_id)).fetchone()
    if not row:
        con.close()
        return 404,{"error":"Practice position not found"}
    mistake=next((m for m in json.loads(row[0])["mistakes"] if m["ply"]==ply),None)
    if mistake is None:
        con.close()
        return 404,{"error":"Practice position not found"}
    day=dt.date.today().isoformat()
    con.execute("""INSERT INTO puzzle_attempts
      (username,game_id,ply,attempts,correct,streak,due,last_attempt)
      VALUES(?,?,?,1,0,0,?,?)
      ON CONFLICT(username,game_id,ply) DO UPDATE SET
        attempts=puzzle_attempts.attempts+1,streak=0,
        due=excluded.due,last_attempt=excluded.last_attempt""",
      (username.lower(),game_id,ply,day,day))
    con.commit()
    con.close()
    try:
        from move_grading import grade
        board=chess.Board(mistake["fen"])
        original=board.parse_san(mistake["best"])
        verdict=grade(mistake["fen"],original,mistake["best"])
        lesson=verdict["lesson"]
        visual=verdict["visual"]
        best=verdict["best_san"]
    except (RuntimeError,ValueError,chess.engine.EngineError,TimeoutError):
        from lesson_explainer import explain
        best=mistake["best"]
        lesson=explain(mistake["fen"],None,best)
        from visual_coach import annotate
        visual=annotate(mistake["fen"],best)
    return 200,{"message":"Answer revealed and recorded as a missed attempt; this position stays due.",
        "best":best,"lesson":lesson,"visual":visual}
