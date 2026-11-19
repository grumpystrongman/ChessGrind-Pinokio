"""Chess Grind ECO catalog — offline Lichess chess-openings, CC0-1.0.

Classification matches normalized FEN (board, side, castling, en passant)
so recognized transpositions have the same opening identity. Opening names
can be assigned to the deepest known prior match, explicitly labeled as
inherited/last-known rather than exact current classification.
"""
from __future__ import annotations
import csv,io,functools,re
from collections import defaultdict
from pathlib import Path
import chess,chess.pgn
ROOT=Path(__file__).resolve().parent/"data"/"eco"
SOURCE="https://github.com/lichess-org/chess-openings"
LICENSE="CC0-1.0"

def key(board):
    return " ".join(board.fen().split(" ")[:4])

@functools.lru_cache(maxsize=1)
def database():
    records=[];bypos=defaultdict(list)
    for volume in "abcde":
        path=ROOT/(volume+".tsv")
        if not path.is_file():continue
        with path.open(encoding="utf-8",newline="") as stream:
            for item in csv.DictReader(stream,delimiter="\t"):
                if not re.fullmatch(r"[A-E]\d\d",item.get("eco","")):continue
                game=chess.pgn.read_game(io.StringIO(item["pgn"]+" *"))
                if not game or game.errors:continue
                board=game.board();steps=[];valid=True
                for move in game.mainline_moves():
                    if move not in board.legal_moves:valid=False;break
                    before=board.fen();san=board.san(move);board.push(move)
                    steps.append({"uci":move.uci(),"san":san,"before":before,
                                  "fen":board.fen(),"key":key(board)})
                if not valid or not steps:continue
                entry={"id":len(records),"eco":item["eco"],"name":item["name"],
                    "pgn":item["pgn"],"plies":len(steps),"steps":steps,"source":SOURCE}
                records.append(entry);bypos[key(board)].append(entry)
    return records,bypos

def total():
    return len(database()[0])

def _choose(found):
    # Prefer specific longer line, stable tie-breaking.
    return sorted(found,key=lambda r:(-r["plies"],r["name"],r["eco"]))[0]

def classify(fen=None,moves=None):
    """Exact position classification; optional last-seen classification through moves."""
    board=chess.Board(fen) if fen else chess.Board()
    if not board.is_valid():raise ValueError("Invalid chess position")
    _,bypos=database()
    current=bypos.get(key(board))
    if current:
        entry=_choose(current)
        return {"eco":entry["eco"],"name":entry["name"],
            "exact":True,"matchedPlies":entry["plies"],"source":SOURCE}
    if moves:
        work=chess.Board();last=None
        for i,uci in enumerate(moves):
            try:
                move=chess.Move.from_uci(uci) if isinstance(uci,str) else uci
                if move not in work.legal_moves:break
            except ValueError:break
            work.push(move)
            found=bypos.get(key(work))
            if found:
                r=_choose(found)
                last={"eco":r["eco"],"name":r["name"],"exact":i==len(moves)-1,
                    "matchedPlies":i+1,"source":SOURCE}
        return last
    return None

def search(query="",limit=40):
    if not isinstance(query,str) or len(query)>90:raise ValueError("Invalid opening search")
    q=query.strip().casefold();rows=[r for r in database()[0]
        if not q or q in r["eco"].casefold() or q in r["name"].casefold()]
    rows.sort(key=lambda r:(
        0 if q and r["name"].casefold()==q else
        1 if q and r["name"].casefold().startswith(q) else
        2 if q and q in r["name"].casefold() else
        3 if q and r["eco"].casefold()==q else 4,
        r["eco"],r["name"]))
    return {"total":total(),"matching":len(rows),
        "openings":[{"id":r["id"],"eco":r["eco"],"name":r["name"],"plies":r["plies"],
                     "pgn":r["pgn"]} for r in rows[:max(1,min(int(limit),80))]],
        "source":SOURCE,"license":LICENSE}

def get(identifier):
    i=int(identifier)
    entries=database()[0]
    if i<0 or i>=len(entries):raise ValueError("Opening not found")
    return entries[i]

def trace(moves):
    """Every matched named opening encountered during a real game."""
    _,lookup=database()
    b=chess.Board();result=[]
    for i,u in enumerate(moves):
        m=chess.Move.from_uci(u) if isinstance(u,str) else u
        if m not in b.legal_moves:break
        san=b.san(m);b.push(m)
        matches=lookup.get(key(b))
        if matches:
            r=_choose(matches)
            result.append({"ply":i+1,"san":san,"eco":r["eco"],
               "name":r["name"],"fen":b.fen(),"exact":True})
    return result
