"""ChessGrind expanded, reproducible chess-quality evaluation.

Uses original Academy and Endgame Laboratory positions only: NO personal
games, proprietary puzzles or player information. Tests legal Stockfish
variations and compares shallow/deeper choices with exact 3-4-piece Syzygy
outcomes where available. Agreement is a diagnostic, NOT chess perfection.
"""
from __future__ import annotations
import argparse
import json
import random
from pathlib import Path
import chess
from academy_curriculum import UNITS
from chess_quality_benchmark import POSITIONS
from endgame_lab import LESSONS
from verified_chess import syzygy_result,tablebase_status,verify

def cases(max_endgames,max_academy):
    chosen=[]
    for label,board in POSITIONS.items():
        chosen.append(("curated",label,board.fen()))
    academy=[]
    for unit in UNITS:
        for item in unit["checks"][:max_academy]:
            academy.append(("academy",unit["id"]+":"+item["id"],item["fen"]))
    chosen.extend(academy)
    eligible=[x for x in LESSONS if len(chess.Board(x["fen"]).piece_map())<=4]
    rng=random.Random(20261120)
    rng.shuffle(eligible)
    seen={chess.Board(x[2]).epd() for x in chosen}
    added=0
    for item in eligible:
        fen=item["fen"]
        key=chess.Board(fen).epd()
        if key in seen:continue
        chosen.append(("exact-endgame",item["id"],fen))
        seen.add(key);added+=1
        if added>=max_endgames:break
    return chosen

def validate_pv(board,report):
    for entry in report.get("candidates",[]):
        play=board.copy()
        for pv in entry["variation"]:
            action=chess.Move.from_uci(pv["uci"])
            if action not in play.legal_moves or play.san(action)!=pv["san"]:
                raise AssertionError("Invalid engine PV on "+board.fen()+": "+str(pv))
            play.push(action)

def run(max_endgames=24,max_academy=3):
    rows=[]
    for kind,ident,fen in cases(max_endgames,max_academy):
        board=chess.Board(fen)
        if not board.is_valid():raise AssertionError("Invalid source board "+ident)
        shallow=verify(fen,depth=8,multipv=3)
        deeper=verify(fen,depth=12,multipv=3)
        validate_pv(board,shallow)
        validate_pv(board,deeper)
        first=shallow.get("candidates",[])
        second=deeper.get("candidates",[])
        uci8=first[0]["firstUci"] if first else None
        uci12=second[0]["firstUci"] if second else None
        exact=syzygy_result(board,include_moves=True) if kind=="exact-endgame" else None
        result={"sourceType":kind,"sourceId":ident,
                "topAtDepth8":uci8,"topAtDepth12":uci12,
                "samePreferredMove":uci8==uci12,
                "pvCountAtDepth8":len(first),"pvCountAtDepth12":len(second)}
        if exact:
            wdl={row["uci"]:row["wdl"] for row in exact["moveDetails"]}
            strongest=max(wdl.values())
            result["tablebaseWdl"]=exact["wdl"]
            result["depth8PreservesBestWdl"]=wdl.get(uci8)==strongest
            result["depth12PreservesBestWdl"]=wdl.get(uci12)==strongest
            result["exactWdlPreservingMoves"]=sum(1 for value in wdl.values() if value==strongest)
        elif kind=="exact-endgame":
            raise AssertionError("Expected exact Syzygy tablebase: "+ident)
        rows.append(result)
    exact_rows=[row for row in rows if row["sourceType"]=="exact-endgame"]
    report={
      "testScope":"ChessGrind authored positions, depth-8 versus depth-12 Stockfish MultiPV",
      "notAProof":"Engine-depth agreement and preserving Syzygy WDL are NOT chess-perfect play.",
      "positions":len(rows),
      "bySource":{kind:sum(1 for row in rows if row["sourceType"]==kind)
                  for kind in ("curated","academy","exact-endgame")},
      "sameFirstMove":sum(row["samePreferredMove"] for row in rows),
      "legalPvVerification":"Every returned UCI/SAN continuation was checked against python-chess",
      "tablebaseComparison":{
         "positions":len(exact_rows),
         "depth8Preserving":sum(row["depth8PreservesBestWdl"] for row in exact_rows),
         "depth12Preserving":sum(row["depth12PreservesBestWdl"] for row in exact_rows),
         "installedCoverage":tablebase_status()},
      "engineDisagreements":[row for row in rows if not row["samePreferredMove"]][:30],
      "tablebaseRegressions":[row for row in exact_rows if not row["depth12PreservesBestWdl"]][:30],
      "cases":rows
    }
    return report

if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--full",action="store_true")
    parser.add_argument("--output",default="docs/CHESS_ACCURACY_SUITE_REPORT.json")
    a=parser.parse_args()
    result=run(max_endgames=80 if a.full else 24,max_academy=6 if a.full else 3)
    destination=Path(a.output)
    destination.parent.mkdir(parents=True,exist_ok=True)
    destination.write_text(json.dumps(result,indent=2),encoding="utf8")
    print("Chess accuracy suite: "+str(result["positions"])+" source positions, "+
          str(result["sameFirstMove"])+" agree at two depths; "+
          str(result["tablebaseComparison"]["depth12Preserving"])+"/"+
          str(result["tablebaseComparison"]["positions"])+
          " depth-12 first choices preserve exact WDL.")
