"""Engine-verified chess decisions and optional Syzygy exact endgame results.

All analysis is local, bounded, versioned and cached by full position key,
engine signature, depth and MultiPV. No 'perfect chess' claim.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import chess
import chess.engine

from chess_grind import db
from game_analysis import find_engine
from chess_knowledge import ensure,now,position_key

def syzygy_result(board):
    # Use only existing tablebase files; do not silently download huge sets.
    directory=os.getenv("CHESSGRIND_SYZYGY_DIR")
    if not directory:return None
    path=Path(directory)
    if not path.is_dir() or not list(path.glob("*.rtbw")):return None
    if len(board.piece_map())>7:return None
    try:
        import chess.syzygy
        with chess.syzygy.open_tablebase(str(path)) as tablebase:
            wdl=tablebase.probe_wdl(board)
            try:dtz=tablebase.probe_dtz(board)
            except chess.syzygy.MissingTableError:dtz=None
        return {"wdl":wdl,"dtz":dtz,"perspective":"side-to-move",
                "meaning":"Exact tablebase result subject to 50-move-rule context",
                "source":"local Syzygy files"}
    except (OSError,ValueError,chess.syzygy.MissingTableError):return None

def signature(path):
    p=Path(path)
    stat=p.stat()
    return hashlib.sha256((str(p.resolve())+":"+str(stat.st_size)+":"+
                          str(stat.st_mtime_ns)).encode()).hexdigest()[:20]

def _san_variation(board,pv,limit=8):
    trial=board.copy()
    labels=[]
    for move in (pv or [])[:limit]:
        if move not in trial.legal_moves:break
        labels.append({"uci":move.uci(),"san":trial.san(move)})
        trial.push(move)
    return labels

def verify(fen,played_uci=None,depth=12,multipv=3,force=False):
    board=chess.Board(fen)
    if not board.is_valid():raise ValueError("Invalid chessboard")
    depth=int(depth);multipv=int(multipv)
    if depth<6 or depth>20:raise ValueError("Depth must be 6 through 20")
    if multipv<1 or multipv>5:raise ValueError("MultiPV must be 1 through 5")
    played=None
    if played_uci:
        try:played=chess.Move.from_uci(played_uci)
        except ValueError:raise ValueError("Illegal UCI")
        if played not in board.legal_moves:raise ValueError("Played move is illegal")
    if board.is_game_over(claim_draw=True):
        return {"fen":board.fen(),"terminal":True,
                "result":board.result(claim_draw=True),"reason":"terminal chess rules",
                "tablebase":syzygy_result(board),"candidates":[]}
    engine=find_engine()
    if not engine:raise RuntimeError("Stockfish executable missing")
    key=position_key(board)
    ident=signature(engine)
    con=db()
    try:
        ensure(con)
        cached=None if force else con.execute("""SELECT analysis FROM kg_position_evaluations
                   WHERE position_key=? AND engine_id=? AND depth=? AND multipv=?""",
                   (key,ident,depth,multipv)).fetchone()
        if cached:
            result=json.loads(cached[0]);result["fromCache"]=True
        else:
            with chess.engine.SimpleEngine.popen_uci(engine,timeout=15) as instance:
                engine_info=instance.analyse(board,chess.engine.Limit(depth=depth),
                                              multipv=min(multipv,board.legal_moves.count()))
            if isinstance(engine_info,dict):engine_info=[engine_info]
            candidates=[]
            for entry in engine_info:
                pv=entry.get("pv") or []
                if not pv or pv[0] not in board.legal_moves:continue
                score=entry["score"].pov(board.turn)
                candidates.append({"firstUci":pv[0].uci(),"firstSan":board.san(pv[0]),
                    "cp":score.score(mate_score=30000),"mate":score.mate(),
                    "depth":entry.get("depth",depth),"variation":_san_variation(board,pv)})
            result={"fen":board.fen(),"positionKey":key,"terminal":False,
                   "source":"Stockfish bounded MultiPV","engineId":ident,
                   "depthRequested":depth,"multipvRequested":multipv,
                   "candidateMovesAreNotForced":True,
                   "candidates":candidates,"tablebase":syzygy_result(board),
                   "fromCache":False}
            with con:
                con.execute("""INSERT OR REPLACE INTO kg_position_evaluations
                   VALUES(?,?,?,?,?,?)""",
                   (key,ident,depth,multipv,json.dumps(result),now()))
        if played is not None:
            best=result["candidates"][0] if result["candidates"] else None
            matching=next((x for x in result["candidates"] if x["firstUci"]==played.uci()),None)
            if matching:
                actual=matching["cp"]
            else:
                with chess.engine.SimpleEngine.popen_uci(engine,timeout=15) as instance:
                    info=instance.analyse(board,chess.engine.Limit(depth=depth),
                                           root_moves=[played])
                actual=info["score"].pov(board.turn).score(mate_score=30000)
            loss=max(0,best["cp"]-actual) if best and best["cp"] is not None and actual is not None else None
            result["played"]={"uci":played.uci(),"san":board.san(played),
                 "engineScoreCp":actual,"lossCp":loss,
                 "classification":("best" if best and played.uci()==best["firstUci"] else
                    "strong" if loss is not None and loss<=45 else
                    "inaccuracy" if loss is not None and loss<=115 else
                    "mistake" if loss is not None and loss<=260 else
                    "blunder" if loss is not None else "unknown")}
        return result
    finally:con.close()
