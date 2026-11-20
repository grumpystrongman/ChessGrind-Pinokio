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

def tablebase_dir():
    """Use the player's explicit folder or ChessGrind's compact bundled set."""
    setting=os.getenv("CHESSGRIND_SYZYGY_DIR") or os.getenv("CHESSGRIND_SYZYGY_PATH")
    return Path(setting) if setting else Path(__file__).resolve().parent / "engine" / "syzygy"

def tablebase_status():
    directory=tablebase_dir()
    if not directory.is_dir():
        return {"installed":False,"maxCompletePieces":0,"files":0,
                "pairs":0,"threeFourComplete":False,"directory":str(directory)}
    import chess.syzygy
    present={p.name for p in directory.iterdir() if p.suffix in (".rtbw",".rtbz")}
    names=set(chess.syzygy.tablenames(piece_count=4))
    pairs=sum(all(name+ext in present for ext in (".rtbw",".rtbz")) for name in names)
    complete=pairs==len(names)
    return {"installed":bool(present),"maxCompletePieces":4 if complete else 0,
            "files":len(present),"pairs":pairs,"threeFourComplete":complete,
            "directory":str(directory),
            "note":"Exact results require material covered by installed WDL/DTZ files. Five-plus-piece sets are not part of this installer."}

def syzygy_result(board,include_moves=True):
    """Return exact covered WDL/DTZ, not distance-to-mate or universal proof."""
    import chess.syzygy
    folder=tablebase_dir()
    if not folder.is_dir() or not list(folder.glob("*.rtbw")) or len(board.piece_map())>7:
        return None
    if board.castling_rights:return None
    try:
        with chess.syzygy.open_tablebase(str(folder)) as tb:
            wdl=tb.probe_wdl(board)
            try:dtz=tb.probe_dtz(board)
            except (chess.syzygy.MissingTableError,ValueError):dtz=None
            label={2:"win",1:"cursed win (50-move rule)",0:"draw",
                   -1:"blessed loss (50-move rule)",-2:"loss"}[wdl]
            moves=[]
            if include_moves and not board.is_game_over(claim_draw=True):
                for move in board.legal_moves:
                    next_board=board.copy(stack=False)
                    notation=board.san(move)
                    next_board.push(move)
                    if next_board.is_checkmate():
                        after_wdl=2;zero=1
                    elif next_board.is_game_over(claim_draw=True) and next_board.outcome(claim_draw=True).winner is None:
                        after_wdl=0;zero=0
                    else:
                        after_wdl=-tb.probe_wdl(next_board)
                        try:zero=-tb.probe_dtz(next_board)
                        except (chess.syzygy.MissingTableError,ValueError):zero=None
                    moves.append({"uci":move.uci(),"san":notation,"wdl":after_wdl,
                                  "dtzAfterMoveFromMoverPerspective":zero})
                def order(row):
                    distance=abs(row["dtzAfterMoveFromMoverPerspective"]) if row["dtzAfterMoveFromMoverPerspective"] is not None else 99999
                    # Prefer a quicker zeroing conversion in a win, but
                    # delay an unavoidable loss when all WDL outcomes lose.
                    return (-row["wdl"],distance if row["wdl"]>=0 else -distance,row["san"])
                moves.sort(key=order)
        best=max((row["wdl"] for row in moves),default=None)
        return {"wdl":wdl,"wdlMeaning":label,"dtz":dtz,"exact":True,
                "perspective":"side-to-move","pieceCount":len(board.piece_map()),
                "availableMoveCount":len(moves),
                "bestMoves":[row for row in moves if row["wdl"]==best][:12],
                "moveDetails":moves,
                "source":"local Syzygy WDL and DTZ",
                "meaning":"Exact WDL/DTZ for covered material with fifty-move-rule caveats; DTZ is not distance to mate."}
    except (OSError,ValueError,KeyError,chess.syzygy.MissingTableError):
        return None

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
    # Unlike opening/teaching retrieval, engine scores can change with
    # the fifty-move counter. Do not reuse a cached score across clock states.
    # FEN alone cannot reconstruct repetition history; callers must treat
    # analyses as bounded evaluations rather than definitive draw claims.
    key=position_key(board)+" | halfmove="+str(board.halfmove_clock)
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
                   "drawHistoryCaveat":"Repetition history is not encoded in FEN; engine output is not a proof of the 50-move or repetition result.",
                   "candidates":candidates,"tablebase":syzygy_result(board),
                   "fromCache":False}
            with con:
                con.execute("""INSERT OR REPLACE INTO kg_position_evaluations
                   VALUES(?,?,?,?,?,?)""",
                   (key,ident,depth,multipv,json.dumps(result),now()))
        # Newly installed tablebases apply even to older cached Stockfish results.
        result["tablebase"]=syzygy_result(board)
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
