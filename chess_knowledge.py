"""ChessGrind verified chess knowledge graph and local semantic evidence store.

The graph records where claims came from, not merely text similarity.
Exact positions use normalized FEN keys; explanation retrieval uses FTS5
and optional local FastEmbed embeddings. No downloaded model is required
for base search, and no external service is used.
"""
from __future__ import annotations

import hashlib
import json
import math
import re
import sqlite3
import struct
from datetime import datetime, timezone
from pathlib import Path

import chess
from chess_grind import db

SCHEMA_VERSION = 1
EMBED_MODEL = "sentence-transformers/all-MiniLM-L6-v2"

# Canonical vocabulary. The descriptions are teaching heuristics, not claims
# that a particular position contains a forced tactic.
CONCEPTS = {
    "calculation": ("Calculation", "List candidate moves and analyze the opponent's most forcing replies.", "calculation"),
    "piece safety": ("Piece safety", "Check loose pieces, attackers, defenders and forcing captures.", "piece-safety"),
    "forks and double attacks": ("Forks and double attacks", "One move may create multiple simultaneous threats; verify that the move works.", "tactics"),
    "pins": ("Pins", "An absolute pin restricts a piece because its king is behind it.", "tactics"),
    "forcing checks": ("Forcing checks", "Evaluate legal checks and the opponent's available evasions.", "calculation"),
    "missed captures": ("Captures", "Check captures and calculate the recaptures.", "tactics"),
    "endgame technique": ("Endgame technique", "King activity, pawn races and opposition are essential to many endings.", "endgames"),
    "opening decisions": ("Opening decisions", "Develop pieces, contest the center and keep the king safe.", "openings"),
    "checkmate patterns": ("Checkmate patterns", "To verify mate, the defending side must have no legal escape from check.", "tactics"),
    "pawn structure": ("Pawn structure", "Pawn weaknesses, passed pawns and pawn breaks create long-term plans.", "strategy"),
    "calculation errors": ("Calculation errors", "Calculate checks, captures and threats for both players.", "calculation"),
    "king safety": ("King safety", "Check the king's exposure, legal threats, and available defenses.", "defense"),
    "center": ("Central control", "The central squares e4, d4, e5 and d5 often influence piece activity.", "openings"),
    "passed pawns": ("Passed pawns", "A passed pawn has no opposing pawn ahead on its file or adjacent files.", "endgames"),
    "opposition": ("King opposition", "Opposition can force concessions in certain king-and-pawn endings.", "endgames"),
}
ACADEMY_TO_CONCEPT = {
    "fork": "forks and double attacks",
    "pin": "pins",
    "loose": "piece safety",
    "center": "center",
    "passed": "passed pawns",
    "opposition": "opposition",
}

def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")

def digest(*values):
    return hashlib.sha256("|".join(str(v) for v in values).encode("utf-8")).hexdigest()[:32]

def position_key(board: chess.Board):
    # Castling and side-to-move matter; clocks do not change legal chess.
    # En passant is relevant only when legal.
    return board.epd(en_passant="legal")

def ensure(con):
    con.executescript("""
    CREATE TABLE IF NOT EXISTS kg_nodes(
      id TEXT PRIMARY KEY,kind TEXT NOT NULL,title TEXT NOT NULL,
      description TEXT NOT NULL,source_kind TEXT NOT NULL,
      source_id TEXT NOT NULL,rights TEXT NOT NULL DEFAULT 'user_or_original',
      metadata TEXT NOT NULL DEFAULT '{}',updated_at TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS kg_edges(
      source TEXT NOT NULL,relation TEXT NOT NULL,target TEXT NOT NULL,
      provenance TEXT NOT NULL,PRIMARY KEY(source,relation,target,provenance));
    CREATE INDEX IF NOT EXISTS kg_edges_target ON kg_edges(target,relation);
    CREATE TABLE IF NOT EXISTS kg_positions(
      position_key TEXT PRIMARY KEY,fen TEXT NOT NULL,
      in_check INTEGER NOT NULL,legal_moves INTEGER NOT NULL,
      is_game_over INTEGER NOT NULL,exact_status TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS kg_examples(
      id TEXT PRIMARY KEY,position_key TEXT NOT NULL,concept_id TEXT,
      source_kind TEXT NOT NULL,source_id TEXT NOT NULL,
      text TEXT NOT NULL,move_uci TEXT,answer_square TEXT,
      verified INTEGER NOT NULL,verification TEXT NOT NULL,
      metadata TEXT NOT NULL DEFAULT '{}',
      FOREIGN KEY(position_key) REFERENCES kg_positions(position_key));
    CREATE INDEX IF NOT EXISTS kg_examples_position ON kg_examples(position_key);
    CREATE INDEX IF NOT EXISTS kg_examples_concept ON kg_examples(concept_id);
    CREATE VIRTUAL TABLE IF NOT EXISTS kg_examples_fts USING fts5(
      id UNINDEXED,text,content='kg_examples',content_rowid='rowid');
    CREATE TRIGGER IF NOT EXISTS kg_example_ai AFTER INSERT ON kg_examples BEGIN
      INSERT INTO kg_examples_fts(rowid,id,text) VALUES(new.rowid,new.id,new.text);
    END;
    CREATE TRIGGER IF NOT EXISTS kg_example_ad AFTER DELETE ON kg_examples BEGIN
      INSERT INTO kg_examples_fts(kg_examples_fts,rowid,id,text)
      VALUES('delete',old.rowid,old.id,old.text);
    END;
    CREATE TRIGGER IF NOT EXISTS kg_example_au AFTER UPDATE ON kg_examples BEGIN
      INSERT INTO kg_examples_fts(kg_examples_fts,rowid,id,text)
      VALUES('delete',old.rowid,old.id,old.text);
      INSERT INTO kg_examples_fts(rowid,id,text) VALUES(new.rowid,new.id,new.text);
    END;
    CREATE TABLE IF NOT EXISTS kg_vectors(
      example_id TEXT NOT NULL,model TEXT NOT NULL,dimensions INTEGER NOT NULL,
      vector BLOB NOT NULL,PRIMARY KEY(example_id,model));
    CREATE TABLE IF NOT EXISTS kg_position_evaluations(
      position_key TEXT NOT NULL,engine_id TEXT NOT NULL,depth INTEGER NOT NULL,
      multipv INTEGER NOT NULL,analysis TEXT NOT NULL,created_at TEXT NOT NULL,
      PRIMARY KEY(position_key,engine_id,depth,multipv));
    CREATE TABLE IF NOT EXISTS kg_player_events(
      event_id TEXT PRIMARY KEY,game_id TEXT NOT NULL,ply INTEGER NOT NULL,
      position_key TEXT NOT NULL,concept_id TEXT,grade TEXT,
      move_uci TEXT NOT NULL,loss_cp INTEGER,created_at TEXT NOT NULL);
    CREATE INDEX IF NOT EXISTS kg_player_concept ON kg_player_events(concept_id,created_at);
    CREATE TABLE IF NOT EXISTS kg_coach_quality(
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      persona TEXT NOT NULL,event TEXT NOT NULL,outcome TEXT NOT NULL,
      reason_codes TEXT NOT NULL,created_at TEXT NOT NULL);
    CREATE INDEX IF NOT EXISTS kg_coach_quality_time ON kg_coach_quality(created_at);
    """)
    con.commit()

def put_node(con,ident,kind,title,description,source_kind,source_id,rights="original",meta=None):
    con.execute("""INSERT INTO kg_nodes VALUES(?,?,?,?,?,?,?,?,?)
        ON CONFLICT(id) DO UPDATE SET
          title=excluded.title,description=excluded.description,
          metadata=excluded.metadata,updated_at=excluded.updated_at""",
        (ident,kind,title,description,source_kind,source_id,rights,
         json.dumps(meta or {},ensure_ascii=False),now()))

def link(con,source,relation,target,provenance):
    con.execute("INSERT OR IGNORE INTO kg_edges VALUES(?,?,?,?)",
                (source,relation,target,provenance))

def put_position(con,board):
    key=position_key(board)
    con.execute("""INSERT OR IGNORE INTO kg_positions VALUES(?,?,?,?,?,?)""",
                (key,board.fen(),int(board.is_check()),
                 board.legal_moves.count(),int(board.is_game_over(claim_draw=True)),
                 board.outcome(claim_draw=True).termination.name if board.outcome(claim_draw=True) else "ongoing"))
    return key

def put_example(con,source_kind,source_id,fen,concept,text,move=None,
                answer_square=None,metadata=None):
    board=chess.Board(fen)
    if not board.is_valid():
        raise ValueError("Invalid board for knowledge example: "+source_id)
    key=put_position(con,board)
    move_uci=None
    if move:
        action=chess.Move.from_uci(move)
        if action not in board.legal_moves:
            raise ValueError("Illegal example move: "+source_id)
        move_uci=action.uci()
    if answer_square and answer_square not in chess.SQUARE_NAMES:
        raise ValueError("Invalid square: "+source_id)
    if concept is not None and concept not in CONCEPTS:
        raise ValueError("Unknown concept: "+str(concept))
    ident="ex:"+digest(source_kind,source_id,key,move_uci,answer_square)
    con.execute("""INSERT INTO kg_examples
       (id,position_key,concept_id,source_kind,source_id,text,
        move_uci,answer_square,verified,verification,metadata)
       VALUES(?,?,?,?,?,?,?,?,?,?,?)
       ON CONFLICT(id) DO UPDATE SET
        text=excluded.text,metadata=excluded.metadata,
        move_uci=excluded.move_uci,answer_square=excluded.answer_square""",
        (ident,key,concept,source_kind,source_id,text,move_uci,answer_square,1,
         "Legal board and move validated; teaching interpretation not engine-proved",
         json.dumps(metadata or {},ensure_ascii=False)))
    put_node(con,ident,"example",source_id,text[:420],source_kind,source_id,
             meta={"positionKey":key,"verification":"board-legal, not engine-proven"})
    position_node="position:"+digest(key)
    put_node(con,position_node,"position",key,board.fen(),"board","normalized-fen",
             meta={"epd":key})
    link(con,ident,"occurs_at",position_node,source_kind+":"+source_id)
    if concept:link(con,ident,"illustrates","concept:"+concept,source_kind+":"+source_id)
    return ident

def seed_concepts(con):
    for slug,(title,description,category) in CONCEPTS.items():
        put_node(con,"concept:"+slug,"concept",title,description,"original","chessgrind",
                 meta={"category":category})
    relationships=[
       ("piece safety","supports","calculation"),
       ("forks and double attacks","is_a","calculation"),
       ("pins","is_a","calculation"),
       ("forcing checks","is_a","calculation"),
       ("missed captures","is_a","calculation"),
       ("king safety","requires","piece safety"),
       ("checkmate patterns","requires","king safety"),
       ("opposition","is_a","endgame technique"),
       ("passed pawns","is_a","endgame technique"),
       ("center","is_a","opening decisions"),
       ("pawn structure","supports","endgame technique"),
       ("calculation errors","addressed_by","calculation")
    ]
    for source,relation,target in relationships:
        link(con,"concept:"+source,relation,"concept:"+target,"original-training-ontology")
    con.commit()

def ingest_academy(con):
    from academy_curriculum import UNITS
    from academy_curriculum import VALID_ANSWERS
    count=0
    for unit in UNITS:
        concept=ACADEMY_TO_CONCEPT.get(unit["kind"])
        if not concept:continue
        for item in [unit["demo"],*unit["checks"]]:
            fen=item["fen"]
            board=chess.Board(fen)
            answers=VALID_ANSWERS.get(item.get("id"),[item["answer"]])
            answer=item["answer"]
            source_id=item.get("id",unit["id"]+":demo")
            # A square-selection exercise is not necessarily a best move.
            # Preserve that distinction; verify the specific move where possible.
            mover=item.get("origin")
            move=None
            if mover:
                candidates=[m for m in board.legal_moves if
                    chess.square_name(m.from_square)==mover and
                    chess.square_name(m.to_square)==answer]
                if candidates:move=candidates[0].uci()
            evidence=(item["prompt"]+" "+item["why"]+" Principle: "+unit["principle"])
            put_example(con,"academy",source_id,fen,concept,evidence,move,answer,
                        {"lesson":unit["title"],"acceptedSquares":answers,
                         "verificationScope":"geometry and legal actions only"})
            count+=1
    return count

def ingest_personal_analyses(con,limit=1200):
    from game_analysis import ensure_analysis
    ensure_analysis(con)
    count=0
    for record in con.execute("SELECT game_id,data FROM game_analysis ORDER BY analyzed_at DESC LIMIT 120").fetchall():
        try:game=json.loads(record["data"])
        except (TypeError,ValueError):continue
        for m in game.get("mistakes",[])[:60]:
            if count>=limit:return count
            try:
                board=chess.Board(m["fen"])
                played=board.parse_san(m["move"])
                best=board.parse_san(m["best"])
            except (KeyError,ValueError):continue
            from motifs import classify
            motif=classify(m)
            concept=motif["topic"] if motif["topic"] in CONCEPTS else "calculation"
            source_id=record["game_id"]+":"+str(m.get("ply"))
            text=("Your recorded game: "+m["move"]+". Verified Stockfish alternative: "+
                  m["best"]+". "+motif["evidence"]+" Depth-limited loss: "+
                  str(m.get("loss","unknown"))+" centipawns.")
            ident=put_example(con,"personal_analysis",source_id,m["fen"],concept,
                       text,best.uci(),metadata={"playedUci":played.uci(),
                                                 "lossCp":m.get("loss"),"gameId":record["game_id"]})
            put_node(con,"game:"+record["game_id"],"game",
                     "Locally analyzed personal game","Private source game analysis",
                     "personal_analysis",record["game_id"],rights="private")
            link(con,ident,"from_game","game:"+record["game_id"],"analysis")
            count+=1
    return count

def ingest_master_positions(con,max_games=150):
    # Opt-in rights-aware corpus already imported locally by ChessGrind.
    from masters_library import ensure as ensure_masters
    import chess.pgn
    import io
    ensure_masters(con)
    count=0
    records=con.execute("""SELECT id,pgn,white,black,source_url FROM master_games
                          ORDER BY featured DESC,year DESC LIMIT ?""",(max_games,)).fetchall()
    for r in records:
        game=chess.pgn.read_game(io.StringIO(r["pgn"]))
        if game is None or game.errors:continue
        board=game.board()
        for ply,m in enumerate(game.mainline_moves()):
            if ply>=20:break
            if m not in board.legal_moves:break
            # Sample only early positions; actual recorded moves, not 'best'.
            if ply in (0,1,2,3,5,7,9,11,15,19):
                notation=board.san(m)
                ident=put_example(con,"master_game",r["id"]+":"+str(ply),
                    board.fen(),"opening decisions",
                    "Recorded historical game "+r["white"]+" against "+r["black"]+
                    ": "+notation+". This is a historical choice, not an engine recommendation.",
                    move=m.uci(),metadata={"gameId":r["id"],"ply":ply,
                                           "sourceUrl":r["source_url"],"historicalOnly":True})
                put_node(con,"master:"+r["id"],"historical-game",
                         r["white"]+" vs "+r["black"],
                         "Imported source-attributed PGN game score",
                         "master_archive",r["id"],rights="imported-game-score",
                         meta={"sourceUrl":r["source_url"]})
                link(con,ident,"from_game","master:"+r["id"],"archive")
                count+=1
            board.push(m)
    return count

def build(include_masters=True,max_master_games=150):
    con=db()
    try:
        ensure(con)
        with con:
            seed_concepts(con)
            counts={"concepts":len(CONCEPTS),
                    "academy":ingest_academy(con),
                    "personalAnalyses":ingest_personal_analyses(con)}
            counts["masterExamples"]=ingest_master_positions(con,max_master_games) if include_masters else 0
        return {**counts,**status(con)}
    finally:con.close()

def record_player_move(game_id,ply,fen,move_uci,grade):
    board=chess.Board(fen)
    move=chess.Move.from_uci(move_uci)
    if not board.is_valid() or move not in board.legal_moves:
        raise ValueError("Cannot record an illegal game decision")
    label=grade.get("category","")
    topic=grade.get("topic")
    mapping={"safety":"piece safety","opening":"opening decisions",
             "endgame":"endgame technique","calculation":"calculation"}
    concept=mapping.get(topic,topic if topic in CONCEPTS else None)
    con=db()
    try:
        ensure(con)
        with con:
            key=put_position(con,board)
            event_id=digest(game_id,ply,move_uci)
            con.execute("""INSERT OR IGNORE INTO kg_player_events
                VALUES(?,?,?,?,?,?,?,?,?)""",
                (event_id,game_id,int(ply),key,concept,label,move_uci,
                 int(grade.get("lossCp") or 0),now()))
            # The position and verified personal decision become graph nodes.
            event_node="player-event:"+event_id
            put_node(con,event_node,"player-decision",board.san(move),
                     "Recorded "+label+" at depth "+str(grade.get("depth","?"))+
                     ", evaluation loss "+str(grade.get("lossCp",0))+"cp.",
                     "local_sparring",game_id,meta={"ply":ply,"move":move_uci})
            if concept:link(con,event_node,"practices","concept:"+concept,"game:"+game_id)
        return event_id
    finally:con.close()

def mastery(limit=8):
    con=db()
    try:
        ensure(con)
        rows=con.execute("""SELECT concept_id,count(*) count,
            sum(CASE WHEN grade IN ('mistake','blunder') THEN 1 ELSE 0 END) errors,
            sum(CASE WHEN grade IN ('best','strong') THEN 1 ELSE 0 END) successes
            FROM kg_player_events WHERE concept_id IS NOT NULL
            GROUP BY concept_id ORDER BY errors DESC,count DESC LIMIT ?""",
            (min(30,max(1,int(limit))),)).fetchall()
        return [dict(x) for x in rows]
    finally:con.close()

def record_coach_quality(persona,event,outcome,reason_codes=None):
    # Intentionally store NO generated text, messages, names or account IDs.
    # Only a persona's identifier, request type and validation outcome.
    if outcome not in ("accepted","corrected","fallback"):
        raise ValueError("Invalid coaching audit outcome")
    con=db()
    try:
        ensure(con)
        with con:
            con.execute("INSERT INTO kg_coach_quality(persona,event,outcome,reason_codes,created_at) VALUES(?,?,?,?,?)",
                (str(persona)[:80],str(event)[:40],outcome,
                 json.dumps([str(x)[:60] for x in (reason_codes or [])][:6]),now()))
        return True
    finally:con.close()

def quality_summary():
    con=db()
    try:
        ensure(con)
        counts=[dict(r) for r in con.execute("""SELECT outcome,count(*) responses
           FROM kg_coach_quality GROUP BY outcome ORDER BY outcome""")]
        total=sum(x["responses"] for x in counts)
        return {"responses":total,"outcomes":counts,
                "coverage":"selected rule-checkable claims only; not proof of complete chess correctness",
                "private":"No player chat text is stored in the audit table."}
    finally:con.close()

def status(con=None):
    owner=con is None
    if owner:con=db()
    try:
        ensure(con)
        return {"nodes":con.execute("SELECT count(*) FROM kg_nodes").fetchone()[0],
                "edges":con.execute("SELECT count(*) FROM kg_edges").fetchone()[0],
                "examples":con.execute("SELECT count(*) FROM kg_examples").fetchone()[0],
                "positions":con.execute("SELECT count(*) FROM kg_positions").fetchone()[0],
                "vectors":con.execute("SELECT count(*) FROM kg_vectors WHERE model=?",(EMBED_MODEL,)).fetchone()[0],
                "enginePositions":con.execute("SELECT count(*) FROM kg_position_evaluations").fetchone()[0]}
    finally:
        if owner:con.close()

def _fts(query,limit=15):
    tokens=re.findall(r"[a-zA-Z0-9]+",query.lower())[:12]
    if not tokens:return []
    con=db()
    try:
        ensure(con)
        rows=con.execute("""SELECT x.*,bm25(kg_examples_fts) score
          FROM kg_examples_fts f JOIN kg_examples x ON x.rowid=f.rowid
          WHERE kg_examples_fts MATCH ? ORDER BY score LIMIT ?""",
          (" OR ".join(tokens),min(50,limit))).fetchall()
        return [dict(x) for x in rows]
    except sqlite3.OperationalError:return []
    finally:con.close()

def exact(fen,limit=12):
    board=chess.Board(fen)
    key=position_key(board)
    con=db()
    try:
        ensure(con)
        return [dict(r) for r in con.execute(
            "SELECT * FROM kg_examples WHERE position_key=? LIMIT ?",(key,min(limit,40)))]
    finally:con.close()

def concepts_for_position(board):
    # Board geometry only; never claim a tactical sequence is winning.
    concepts=[]
    if board.is_check():concepts.append("king safety")
    pieces=sum(x.piece_type not in (chess.KING,chess.PAWN) for x in board.piece_map().values())
    if pieces<=4:concepts.append("endgame technique")
    elif board.fullmove_number<=12:concepts.append("opening decisions")
    if any(x.piece_type==chess.PAWN and chess.square_name(s) in ("e4","d4","e5","d5")
           for s,x in board.piece_map().items()):concepts.append("center")
    return list(dict.fromkeys(concepts))

def retrieve(fen,query="",limit=5,use_vectors=True):
    board=chess.Board(fen)
    if not board.is_valid():raise ValueError("Invalid chess position")
    con=db()
    try:
        ensure(con)
        exact_rows=[dict(x) for x in con.execute(
            "SELECT * FROM kg_examples WHERE position_key=? LIMIT 12",(position_key(board),))]
        concepts=concepts_for_position(board)
        sources={}
        for row in exact_rows:sources[row["id"]]=(2.0,"exact-position",row)
        for row in _fts(query+" "+" ".join(concepts),max(20,limit*5)):
            sources.setdefault(row["id"],(.4,"full-text",row))
        if use_vectors:
            try:
                for row in vector_search(query+" "+" ".join(concepts),limit=15):
                    sources.setdefault(row["id"],(.3+row["similarity"],"semantic",row))
            except (ImportError,OSError,RuntimeError,ValueError):
                # The graph and full-text search remain available offline.
                pass
        # Diversify evidence: avoid filling the context with near-identical
        # Academy variants or 10 historical examples from one opening.
        ranked=sorted(sources.values(),key=lambda t:(-t[0],t[2]["id"]))
        ordered=[];by_source={};seen_text=set()
        for item in ranked:
            kind=item[2]["source_kind"]
            normalized=re.sub(r"\s+"," ",item[2]["text"].lower())[:180]
            if normalized in seen_text or by_source.get(kind,0)>=2:continue
            ordered.append(item);seen_text.add(normalized)
            by_source[kind]=by_source.get(kind,0)+1
            if len(ordered)>=min(limit,12):break
        results=[]
        for score,match,row in ordered:
            row=dict(row)
            # Surface original provenance and make uncertainties explicit.
            row["match"]=match
            row["metadata"]=json.loads(row.get("metadata") or "{}")
            row["trust"]="verified-legal-position; historical move or teaching note not necessarily optimal"
            results.append(row)
        return {"fen":board.fen(),"positionKey":position_key(board),
                "concepts":concepts,"examples":results,
                "note":"Exact position matching is authoritative for identity; semantic matches are analogies, not proof."}
    finally:con.close()

def vector_build(batch_size=48,limit=None):
    # Existing FastEmbed package already shipped in ChessGrind, no Qdrant
    # server required. Vectors stored in the same SQLite DB.
    from semantic_index import model,pack
    con=db()
    try:
        ensure(con)
        sql="""SELECT id,text FROM kg_examples WHERE id NOT IN
            (SELECT example_id FROM kg_vectors WHERE model=?) ORDER BY id"""
        params=[EMBED_MODEL]
        if limit is not None:
            sql+=" LIMIT ?";params.append(int(limit))
        rows=con.execute(sql,params).fetchall()
        embedding=model()
        built=0
        for offset in range(0,len(rows),batch_size):
            chunk=rows[offset:offset+batch_size]
            vecs=list(embedding.embed([x["text"] for x in chunk],batch_size=batch_size))
            with con:
                for row,vec in zip(chunk,vecs):
                    payload=pack(vec)
                    con.execute("INSERT OR REPLACE INTO kg_vectors VALUES(?,?,?,?)",
                        (row["id"],EMBED_MODEL,len(payload)//4,payload))
                    built+=1
        return {"embeddedNow":built,"vectors":status(con)["vectors"],"model":EMBED_MODEL}
    finally:con.close()

def vector_search(query,limit=8):
    if not query.strip():return []
    from semantic_index import model,pack,unpack
    con=db()
    try:
        ensure(con)
        rows=con.execute("SELECT example_id,dimensions,vector FROM kg_vectors WHERE model=?",
                          (EMBED_MODEL,)).fetchall()
        if not rows:return []
        query_blob=pack(next(iter(model().query_embed(query))))
        q=unpack(query_blob,len(query_blob)//4)
        similarities=[]
        for row in rows:
            if row["dimensions"]!=len(q):continue
            value=unpack(row["vector"],row["dimensions"])
            cosine=sum(a*b for a,b in zip(q,value))
            similarities.append((cosine,row["example_id"]))
        result=[]
        for score,key in sorted(similarities,reverse=True)[:limit]:
            record=con.execute("SELECT * FROM kg_examples WHERE id=?",(key,)).fetchone()
            if record:
                hit=dict(record);hit["similarity"]=round(score,4);result.append(hit)
        return result
    finally:con.close()

if __name__=="__main__":
    import argparse
    parser=argparse.ArgumentParser()
    parser.add_argument("action",choices=["build","status","search","vectors"])
    parser.add_argument("--fen",default=chess.STARTING_FEN)
    parser.add_argument("--query",default="How do I avoid hanging pieces?")
    parser.add_argument("--master-games",type=int,default=150)
    parser.add_argument("--vector-limit",type=int)
    args=parser.parse_args()
    if args.action=="build":result=build(max_master_games=args.master_games)
    elif args.action=="status":result=status()
    elif args.action=="vectors":result=vector_build(limit=args.vector_limit)
    else:result=retrieve(args.fen,args.query)
    print(json.dumps(result,ensure_ascii=False,indent=2))
