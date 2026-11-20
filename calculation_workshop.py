"""Chess Grind Calculation Workshop and Blind Spot Detector.

Local Stockfish is the *only* tactical evaluator. The analyzer records a user's
candidate before showing the strongest engine lines. Moves and labels are
grounded in legal chess boards, not language-model speculation.
"""
import datetime as dt
import json
import math
import re
import sqlite3
from collections import Counter, defaultdict
import chess
import chess.engine
from chess_grind import db
from game_analysis import find_engine
from motifs import classify
from lesson_explainer import move_reasons,variation
from learning_lab import WEIGHT

def current_username():
    from account_settings import username
    return username() or "player"
MAX_DEPTH=11
def ensure(con):
    con.executescript("""CREATE TABLE IF NOT EXISTS workshop_trials(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL,game_id TEXT NOT NULL,ply INTEGER NOT NULL,
    fen TEXT NOT NULL,chosen_uci TEXT NOT NULL,
    suggested_reply TEXT NOT NULL DEFAULT '',
    best_uci TEXT NOT NULL,correct INTEGER NOT NULL,
    regret_cp INTEGER, assisted INTEGER NOT NULL DEFAULT 0,
    at TEXT NOT NULL
    );
    CREATE INDEX IF NOT EXISTS workshop_trials_user
    ON workshop_trials(username,at);
    """)
    con.commit()

def _games(con):
    from game_analysis import ensure_analysis
    ensure_analysis(con)
    rows=con.execute("SELECT data FROM game_analysis WHERE username=?",(current_username(),)).fetchall()
    return [json.loads(r[0]) for r in rows]

def _mistakes(con):
    for g in _games(con):
        for mistake in g.get("mistakes",[]):
            yield g,mistake

def _phase(fen):
    board=chess.Board(fen)
    total=sum(p.piece_type!=chess.PAWN and p.piece_type!=chess.KING for p in board.piece_map().values())
    return "Endgame" if total<=3 else "Opening" if board.fullmove_number<=10 else "Middlegame"

def _severity(loss):
    if loss>=250:return "Blunder"
    if loss>=120:return "Mistake"
    return "Inaccuracy"

def profile():
    con=db();ensure(con)
    try:
        by_topic=defaultdict(lambda:{"count":0,"weighted":0.,"loss":0,"games":set(),"phase":Counter()})
        by_phase=Counter()
        by_time=Counter()
        by_date=defaultdict(lambda:{"positions":0,"loss":0,"blunders":0})
        total=0;sample=[]
        for g,m in _mistakes(con):
            if not m.get("fen") or not m.get("best") or not m.get("move"):continue
            try:
                board=chess.Board(m["fen"]);board.parse_san(m["best"]);board.parse_san(m["move"])
            except (ValueError,KeyError):continue
            topic=classify(m)["topic"]
            phase=_phase(m["fen"]);tc=g.get("timeClass","rapid")
            loss=max(0,int(m.get("loss",0)));weight=WEIGHT.get(tc,.5)
            slot=by_topic[topic];slot["count"]+=1;slot["weighted"]+=weight
            slot["loss"]+=loss;slot["games"].add(g["id"]);slot["phase"][phase]+=1
            by_phase[phase]+=1;by_time[tc]+=1;total+=1
            day=dt.datetime.fromtimestamp(int(g.get("date",0)),dt.timezone.utc).strftime("%Y-%m") if g.get("date") else None
            if day:
                by_date[day]["positions"]+=1;by_date[day]["loss"]+=loss
                by_date[day]["blunders"]+=int(loss>=250)
            sample.append({"gameId":g["id"],"ply":m["ply"],"topic":topic,
              "opponent":g.get("opponent","Unknown"),"loss":loss,"severity":_severity(loss),
              "phase":phase,"timeClass":tc,"fen":m["fen"],
              "played":m["move"],"best":m["best"]})
        trials=[dict(r) for r in con.execute("""SELECT game_id,ply,correct,assisted,regret_cp
            FROM workshop_trials WHERE username=? ORDER BY id DESC""",(current_username(),))]
        independent=[x for x in trials if not x["assisted"]]
        tried={(x["game_id"],x["ply"]) for x in trials}
        topic_rows=[]
        for topic,data in sorted(by_topic.items(),key=lambda x:-x[1]["weighted"]):
            topic_rows.append({"topic":topic,"positions":data["count"],
              "weightedPriority":round(data["weighted"],1),
              "averageLossCp":round(data["loss"]/data["count"]),
              "games":len(data["games"]),
              "mostCommonPhase":data["phase"].most_common(1)[0][0],
              "workshopAccuracy":None})
        months=[{"month":key,"flagged":value["positions"],
            "averageLossCp":round(value["loss"]/value["positions"]),
            "blunders":value["blunders"]} for key,value in sorted(by_date.items())]
        # These are counts of *flagged moves*. Historical variation depends on
        # analyzed games per month, so never present count trends as a rate.
        recent=sorted(sample,key=lambda x:(x["gameId"],x["ply"]))
        for row in topic_rows:
            matching=[x for x in sample if x["topic"]==row["topic"]]
            row["dueCount"]=sum((x["gameId"],x["ply"]) not in tried for x in matching)
        return {"totalFlagged":total,"topics":topic_rows,
          "phases":[{"phase":p,"count":by_phase[p]} for p in ("Opening","Middlegame","Endgame")],
          "timeControls":[{"timeClass":key,"count":count} for key,count in by_time.most_common()],
          "monthly":months[-18:],
          "totalWorkshopTrials":len(trials),"independentTrials":len(independent),
          "independentAccuracy":round(100*sum(t["correct"] for t in independent)/len(independent)) if independent else None,
          "unseenAvailable":sum((x["gameId"],x["ply"]) not in tried for x in sample),
          "note":"Counts describe flagged decisions in analyzed games, not error rates per game, probability of future mistakes, or proof of improvement over time."}
    finally:con.close()

def positions(topic=None,phase=None,limit=60):
    if topic is not None and (not isinstance(topic,str) or len(topic)>80):raise ValueError("Invalid topic")
    if phase is not None and phase not in ("Opening","Middlegame","Endgame"):raise ValueError("Invalid phase")
    limit=max(1,min(int(limit),100))
    con=db();ensure(con)
    try:
        attempted={(r["game_id"],r["ply"]) for r in con.execute(
          "SELECT game_id,ply FROM workshop_trials WHERE username=?",(current_username(),))}
        entries=[]
        for g,m in _mistakes(con):
            if not m.get("fen") or not m.get("best") or not m.get("move"):continue
            try:
                board=chess.Board(m["fen"]);board.parse_san(m["best"]);board.parse_san(m["move"])
            except ValueError:continue
            name=classify(m)["topic"];stage=_phase(m["fen"])
            if topic and name!=topic:continue
            if phase and stage!=phase:continue
            entries.append({"gameId":g["id"],"ply":m["ply"],"topic":name,
              "fen":m["fen"],"phase":stage,"timeClass":g.get("timeClass","rapid"),
              "opponent":g.get("opponent","Unknown"),"lossCp":m["loss"],
              "attempted":(g["id"],m["ply"]) in attempted,
              "severity":_severity(m["loss"])})
        entries.sort(key=lambda x:(x["attempted"],-WEIGHT.get(x["timeClass"],.5),
             -min(x["lossCp"],800),x["gameId"],x["ply"]))
        selected=[];games=set()
        for e in entries:
            if e["gameId"] not in games:selected.append(e);games.add(e["gameId"])
            if len(selected)>=limit:break
        if len(selected)<limit:
            keys={(x["gameId"],x["ply"]) for x in selected}
            selected.extend(e for e in entries if (e["gameId"],e["ply"]) not in keys)
        return {"positions":selected[:limit],"count":len(entries),
          "note":"Previously answered positions are labeled. An unseen position has not been submitted through this Workshop; it may still have appeared elsewhere in Chess Grind."}
    finally:con.close()

def get_position(game_id,ply):
    if not isinstance(game_id,str) or not 5<=len(game_id)<=160:raise ValueError("Invalid game ID")
    if not isinstance(ply,int) or not 0<=ply<=400:raise ValueError("Invalid move number")
    con=db()
    try:
        row=con.execute("SELECT data FROM game_analysis WHERE username=? AND game_id=?",(current_username(),game_id)).fetchone()
        if not row:raise ValueError("Analyzed game not found")
        g=json.loads(row[0])
        m=next((x for x in g.get("mistakes",[]) if x["ply"]==ply),None)
        if not m:raise ValueError("Position is not available")
        board=chess.Board(m["fen"]);board.parse_san(m["best"]);board.parse_san(m["move"])
        return g,m
    finally:con.close()

def _move(board,uci):
    if not isinstance(uci,str) or not re.fullmatch("[a-h][1-8][a-h][1-8][qrbn]?",uci):
        raise ValueError("Choose a piece and a destination square")
    move=chess.Move.from_uci(uci)
    if move not in board.legal_moves:raise ValueError("That move is not legal on this board")
    return move

def _format_score(info,root_color):
    value=info["score"].pov(root_color)
    cp=value.score(mate_score=20000)
    return {"cp":cp,"display":"Mate "+str(value.mate()) if value.is_mate() else
       ("+" if cp>=0 else "")+format(cp/100,".2f"),"mate":value.mate()}

def _branch(board,move,pv,score,kind,root_color):
    start=board.copy();line=[move]
    after=board.copy();after.push(move)
    for following in pv[1:7]:
        if following not in after.legal_moves:break
        line.append(following);after.push(following)
    steps=[{"index":0,"fen":board.fen(),"san":None,"uci":None}]
    replay=board.copy()
    for index,m in enumerate(line,1):
        san=replay.san(m);replay.push(m)
        steps.append({"index":index,"fen":replay.fen(),"san":san,"uci":m.uci()})
    return {"type":kind,"move":start.san(move),"uci":move.uci(),
      "score":score,"line":variation(start,line,max_plies=7),
      "steps":steps,"reasons":move_reasons(start,move)[:3]}

def _engine_choice(board,chosen,recorded,depth=MAX_DEPTH):
    path=find_engine()
    if not path:raise RuntimeError("Stockfish is required for Calculation Workshop.")
    root_color=board.turn
    with chess.engine.SimpleEngine.popen_uci(path,timeout=40) as engine:
        engine.configure({"Threads":1,"Hash":64})
        limit=chess.engine.Limit(depth=max(7,min(int(depth),12)))
        # One multipv search avoids repeated full engine launches for each line.
        multi=engine.analyse(board,limit,multipv=min(3,board.legal_moves.count()))
        if isinstance(multi,dict):multi=[multi]
        valid=[x for x in multi if x.get("pv")]
        if not valid:raise RuntimeError("Stockfish produced no legal continuation")
        top=valid[0];top_move=top["pv"][0]
        indexed={r["pv"][0]:r for r in valid}
        for move in (chosen,recorded):
            if move not in indexed:
                indexed[move]=engine.analyse(board,limit,root_moves=[move])
                if not indexed[move].get("pv"):
                    raise RuntimeError("Stockfish could not analyze candidate move")
        top_score=_format_score(top,root_color)
        branches=[]
        for move,kind in ((top_move,"top"),(chosen,"candidate"),(recorded,"played-in-game")):
            if any(x["uci"]==move.uci() for x in branches):continue
            info=indexed[move]
            pv=info.get("pv",[])
            if not pv or pv[0]!=move:pv=[move]+[x for x in pv if x!=move]
            branches.append(_branch(board,move,pv,_format_score(info,root_color),kind,root_color))
    picked=next(b for b in branches if b["uci"]==chosen.uci())
    regret=max(0,top_score["cp"]-picked["score"]["cp"])
    return branches,regret,regret<=65

def preview(game_id,ply,chosen_uci):
    # No grading or engine hints are revealed before the learner predicts.
    g,m=get_position(game_id,ply)
    board=chess.Board(m["fen"])
    move=_move(board,chosen_uci)
    san=board.san(move)
    board.push(move)
    return {"afterFen":board.fen(),"san":san,
            "side":"White" if board.turn else "Black",
            "note":"Now predict the opponent's strongest reply, or skip prediction."}

def submit(game_id,ply,chosen_uci,predicted_reply="",assisted=False):
    if not isinstance(assisted,bool):raise ValueError("Invalid assistance flag")
    g,m=get_position(game_id,ply)
    board=chess.Board(m["fen"])
    chosen=_move(board,chosen_uci)
    predicted_reply=str(predicted_reply or "").strip()
    # Prediction is a legal *opponent* move after the user's choice.
    after=board.copy();after.push(chosen)
    prediction=None
    if predicted_reply:
        predicted=_move(after,predicted_reply)
        prediction=after.san(predicted)
    branches,regret,correct=_engine_choice(board,chosen,board.parse_san(m["move"]))
    candidate=next(b for b in branches if b["uci"]==chosen.uci())
    best=branches[0]
    engine_reply=candidate["steps"][2]["san"] if len(candidate["steps"])>2 else None
    reply_match=(prediction==engine_reply) if prediction and engine_reply else None
    con=db();ensure(con)
    con.execute("""INSERT INTO workshop_trials(username,game_id,ply,fen,chosen_uci,
        suggested_reply,best_uci,correct,regret_cp,assisted,at) VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
        (current_username(),game_id,ply,board.fen(),chosen.uci(),predicted_reply,best["uci"],
         int(correct),regret,int(assisted),
         dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")))
    con.commit();con.close()
    message=("You found a strong candidate." if correct else
        "A stronger continuation exists. Compare what happens after your move with what follows the preferred move.")
    if prediction:
        message+=(" You anticipated the engine's leading reply in your candidate line." if reply_match else
            " Your predicted reply differs from this depth-limited engine continuation.")
    return {"position":{"gameId":game_id,"ply":ply,"fen":m["fen"],
                        "side":"White" if board.turn else "Black",
                        "topic":classify(m)["topic"],"opponent":g["opponent"]},
       "chosenSan":board.san(chosen),"bestSan":best["move"],
       "recordedGameSan":m["move"],"predictedReply":prediction,
       "engineReply":engine_reply,"predictionMatches":reply_match,
       "regretCp":regret,"accepted":correct,"assisted":assisted,
       "message":message,"branches":branches,
       "limitation":"Stockfish is depth-limited; its lines are verified continuations, not forced proof. Evaluation is in pawns from the perspective of the side to move at the starting board. Scores are approximate."}
