"""Mechanical geometry audit for every Chess Vision Academy item.

Proves selected geometric relationships, NOT optimal Stockfish play.
No personal games or private records are accessed.
"""
from __future__ import annotations
import chess
from academy_curriculum import UNITS

def has_enemy_pawn_ahead(board,square):
    pawn=board.piece_at(square)
    if not pawn or pawn.piece_type!=chess.PAWN:return False
    for sq,p in board.piece_map().items():
        if p.piece_type!=chess.PAWN or p.color==pawn.color:continue
        if abs(chess.square_file(sq)-chess.square_file(square))>1:continue
        if p.color!=chess.WHITE and chess.square_rank(sq)<chess.square_rank(square):continue
        if p.color!=chess.BLACK and chess.square_rank(sq)>chess.square_rank(square):continue
        # Use the advancing side's orientation, not the attacking pawn's.
        if pawn.color==chess.WHITE and chess.square_rank(sq)>chess.square_rank(square):return True
        if pawn.color==chess.BLACK and chess.square_rank(sq)<chess.square_rank(square):return True
    return False

def check(unit,item):
    board=chess.Board(item["fen"])
    if not board.is_valid():return "invalid FEN"
    if board.is_game_over(claim_draw=True):return "terminal teaching position"
    target=chess.parse_square(item["answer"])
    origin=item.get("origin")
    kind=unit["kind"]
    if origin:
        move=chess.Move.from_uci(origin+item["answer"])
        if move not in board.legal_moves:return "illegal authored candidate"
        moving=board.piece_at(move.from_square)
        board.push(move)
    if kind=="fork":
        targets=item.get("targets") or []
        if len(targets)<2:return "missing fork targets"
        piece=board.piece_at(target)
        if not piece:return "no attacking piece on answer square"
        for sq in targets[:2]:
            square=chess.parse_square(sq)
            enemy=board.piece_at(square)
            if not enemy or enemy.color==piece.color or square not in board.attacks(target):
                return "two enemy targets are not attacked by moving piece"
    elif kind=="pin":
        piece=board.piece_at(chess.parse_square(item["targets"][0]))
        if not piece or not board.is_pinned(piece.color,chess.parse_square(item["targets"][0])):
            return "claimed absolute pin not present"
    elif kind=="loose":
        piece=board.piece_at(target)
        if not piece or piece.color==board.turn:return "no enemy target"
        if not board.is_attacked_by(board.turn,target):return "target not attacked"
        if board.is_attacked_by(not board.turn,target):return "target defended"
    elif kind=="center":
        if not origin or moving.piece_type!=chess.PAWN:return "not a pawn move"
        if item["answer"] not in ("d4","e4","d5","e5"):return "not a central square"
    elif kind=="passed":
        piece=board.piece_at(target)
        if not piece or piece.piece_type!=chess.PAWN or piece.color!=board.turn:
            return "not current side's pawn"
        if has_enemy_pawn_ahead(board,target):return "claimed passed pawn is blocked"
    elif kind=="opposition":
        kings=[x for x,p in board.piece_map().items() if p.piece_type==chess.KING]
        if len(kings)!=2 or board.piece_at(target):return "answer not a vacant middle square"
        if any(chess.square_distance(king,target)!=1 for king in kings):
            return "not one square between kings"
        if not (chess.square_rank(kings[0])==chess.square_rank(kings[1]) or
                chess.square_file(kings[0])==chess.square_file(kings[1])):
            return "kings not on same line"
    else:return "unsupported topic "+str(kind)
    return None

def audit():
    faults=[];by_topic={};total=0
    for unit in UNITS:
        candidates=[unit["demo"],*unit["checks"]]
        errors=0
        for n,item in enumerate(candidates):
            total+=1
            try:reason=check(unit,item)
            except (ValueError,TypeError,KeyError,AttributeError) as exc:
                reason=type(exc).__name__+" "+str(exc)[:100]
            if reason:
                errors+=1
                faults.append({"topic":unit["id"],"id":item.get("id","demo-"+str(n)),
                               "reason":reason})
        by_topic[unit["id"]]={"examples":len(candidates),"failures":errors}
    return {"total":total,"passed":total-len(faults),
            "byTopic":by_topic,"failures":faults}

if __name__=="__main__":
    outcome=audit()
    print("Academy geometry: "+str(outcome["passed"])+"/"+str(outcome["total"])+" passed")
    print(outcome["byTopic"])
    if outcome["failures"]:
        print(outcome["failures"][:15])
        raise SystemExit(1)
