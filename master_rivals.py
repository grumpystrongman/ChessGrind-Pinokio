"""Master-inspired ChessGrind challengers.

Uses moves actually recorded in the local licensed/source-attributed historical
PGN archive when the current position occurs in a master's games; otherwise
Stockfish plays using deliberately *approximate* style settings.
Neither historical play nor Elo accuracy is implied outside those examples.
"""
from __future__ import annotations
import collections,io,random,hashlib,json
from pathlib import Path
from functools import lru_cache
import chess,chess.pgn
from chess_grind import db
from masters_library import PLAYERS,ensure,overview
from masters_curriculum import profile

STYLES={
 "Tal":"active","Alekhine":"active","Kasparov":"active","PolgarJ":"active",
 "Morphy":"active","Anderssen":"active","Fischer":"active","Nakamura":"active",
 "Karpov":"solid","Petrosian":"solid","Capablanca":"solid","Smyslov":"solid",
 "Kramnik":"solid","Carlsen":"solid","Botvinnik":"solid","Rubinstein":"solid"}
PROFILES=Path(__file__).resolve().parent/"data"/"master_style_profiles.json"
def evidence():
    if not PROFILES.exists():return {}
    try:return json.loads(PROFILES.read_text("utf8"))
    except (OSError,ValueError):return {}
STRENGTH={key:18 for key in PLAYERS}
STRENGTH.update({"Carlsen":20,"Kasparov":20,"Karpov":19,"Fischer":20,"Capablanca":19,"Tal":19,
                 "Nakamura":20,"Anand":20,"Gukesh":20,"Ding":20,"PolgarJ":20,"Hou":19})
def roster():
    items=overview()["masters"]
    observed=evidence()
    result=[]
    for m in items:
        key=m["key"]
        if key not in PLAYERS:continue
        try:
            meta=profile(key)
        except (ValueError,KeyError):meta={}
        result.append({"id":key,"name":PLAYERS[key][0],"era":PLAYERS[key][1],
            "recordedGames":m["games"],"style":STYLES.get(key,"balanced"),
            "skill":STRENGTH.get(key,18),
            "knownFor":meta.get("knownFor","Study their recorded decisions and compare candidate moves."),
            "recordedStyle":observed.get(key,{}),
            "avatar":"/icons/masters/"+key+".svg",
            "description":"Master-inspired Stockfish using source-recorded openings when available; not a recreation of a human mind."})
    return {"masters":result,"source":"PGN Mentor public historical game-score collection",
            "accuracy":"Historical opening moves are real archive moves; other moves are Stockfish approximations. Skills are not certified Elo."}
def valid_master(master_id):
    return isinstance(master_id,str) and master_id in PLAYERS

@lru_cache(maxsize=48)
def _opening_map(master_id):
    if not valid_master(master_id):raise ValueError("Unknown historical master")
    con=db()
    try:
        ensure(con)
        records=con.execute("SELECT white,black,pgn FROM master_games WHERE source_player=? LIMIT 250",
                            (master_id,)).fetchall()
    finally:con.close()
    opening=collections.defaultdict(collections.Counter)
    surname=PLAYERS[master_id][0].split()[-1].casefold()
    for row in records:
        white=surname in row["white"].casefold()
        black=surname in row["black"].casefold()
        if not white and not black:continue
        g=chess.pgn.read_game(io.StringIO(row["pgn"]))
        if not g or g.errors:continue
        board=g.board()
        for ply,m in enumerate(g.mainline_moves()):
            if ply>=28:break
            if board.turn==white and white!=black:
                opening[board.epd()][m.uci()]+=1
            if m not in board.legal_moves:break
            board.push(m)
    return dict(opening)

def source_move(board,master_id):
    """Prefer a recorded historical opening move; only in the exact same position."""
    if not valid_master(master_id):return None
    if board.fullmove_number>15:return None
    counts=_opening_map(master_id).get(board.epd())
    if not counts:return None
    legal=[(chess.Move.from_uci(move),n) for move,n in counts.items()
           if chess.Move.from_uci(move) in board.legal_moves]
    if not legal:return None
    # Stable weighted choice for repeatable opening analysis, not a stochastic LLM.
    seed=int(hashlib.sha256((master_id+board.epd()).encode()).hexdigest()[:12],16)
    rng=random.Random(seed)
    return rng.choices([x[0] for x in legal],weights=[x[1] for x in legal],k=1)[0]
