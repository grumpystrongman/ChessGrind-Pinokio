"""Public-position baseline for ChessGrind evidence quality.

Reports where shallow and deeper Stockfish preferences agree. This is a
regression/instability diagnostic, NOT a certification of perfect play.
"""
from __future__ import annotations
import json,os
from pathlib import Path
import chess
from verified_chess import verify

POSITIONS = {}
POSITIONS["starting-position"]=chess.Board()
b=chess.Board()
for san in ("f3","e5","g4"):b.push_san(san)
POSITIONS["fools-mate-threat"]=b
b=chess.Board()
for san in ("e4","e5","Qh5","Nc6","Bc4","Nf6"):b.push_san(san)
POSITIONS["scholars-mate-threat"]=b
b=chess.Board()
for san in ("e4","e5","Nf3","Nc6","Bc4","Bc5","c3","Nf6"):b.push_san(san)
POSITIONS["italian-opening"]=b
POSITIONS["rook-endgame"]=chess.Board("8/8/8/8/8/5k2/8/4K2R w - - 0 1")
POSITIONS["pawn-endgame"]=chess.Board("8/5k2/8/3P4/3K4/8/8/8 w - - 0 1")
def benchmark():
    stats=[]
    for name,board in POSITIONS.items():
        assert board.is_valid(),(name,board.fen())
        reports=[verify(board.fen(),depth=depth,multipv=3) for depth in (8,12)]
        for report in reports:
            for candidate in report["candidates"]:
                position=board.copy()
                for pv in candidate["variation"]:
                    mv=chess.Move.from_uci(pv["uci"])
                    assert mv in position.legal_moves,(name,report["depthRequested"],candidate)
                    assert position.san(mv)==pv["san"],(name,pv)
                    position.push(mv)
        p=[x["candidates"][0]["firstUci"] if x["candidates"] else None for x in reports]
        row={"position":name,"bestDepth8":p[0],"bestDepth12":p[1],
             "sameFirstMove":p[0]==p[1],
             "depth8Candidates":len(reports[0]["candidates"]),
             "depth12Candidates":len(reports[1]["candidates"]),
             "terminal":reports[0]["terminal"]}
        stats.append(row)
        print(name,":",p,"agreement:",p[0]==p[1],flush=True)
    return {"scope":"Six curated public positions at depths 8 and 12",
            "notProof":"Depth agreement and legal PVs do not prove optimal chess decisions.",
            "sameBest":sum(x["sameFirstMove"] for x in stats),
            "positions":len(stats),"cases":stats}
if __name__=="__main__":
    summary=benchmark()
    destination=Path(__file__).resolve().parent/"docs"/"CHESS_QUALITY_BASELINE.json"
    destination.write_text(json.dumps(summary,indent=2),encoding="utf8")
    print("QUALITY_BASELINE",summary["sameBest"],"of",summary["positions"],flush=True)
