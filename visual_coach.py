"""Visually explain verified chess move consequences for the local trainer.

Only legal chess moves and board-derived threats are annotated. Forks are
direct attacks by one moved piece on two occupied valuable targets; pins and
skewers use actual alignment with an attacker, front piece, and back piece.
"""
from __future__ import annotations
import chess
import chess.engine

PIECES={chess.PAWN:"pawn", chess.KNIGHT:"knight",chess.BISHOP:"bishop",
        chess.ROOK:"rook",chess.QUEEN:"queen",chess.KING:"king"}
VALUES={chess.PAWN:1,chess.KNIGHT:3,chess.BISHOP:3,chess.ROOK:5,chess.QUEEN:9,chess.KING:20}

def square(sq):
    return chess.square_name(sq)

def line_squares(a,b):
    """Squares strictly after a on the geometric line through b."""
    af,ar=chess.square_file(a),chess.square_rank(a)
    bf,br=chess.square_file(b),chess.square_rank(b)
    df=bf-af;dr=br-ar
    if not (df==0 or dr==0 or abs(df)==abs(dr)):
        return []
    dx=(df>0)-(df<0);dy=(dr>0)-(dr<0)
    if not (dx or dy):return []
    result=[]
    f,r=af+dx,ar+dy
    while 0<=f<8 and 0<=r<8:
        result.append(chess.square(f,r));f+=dx;r+=dy
    return result

def _line_tactics(board,moved,color):
    piece=board.piece_at(moved)
    if not piece or piece.piece_type not in (chess.BISHOP,chess.ROOK,chess.QUEEN):
        return [],[]
    arrows=[];features=[]
    for target in board.attacks(moved):
        victim=board.piece_at(target)
        if victim is None or victim.color==color:
            continue
        # The forward ray must contain this exact target first; legal geometry
        # is already ensured by chess.Board.attacks(moved).
        ray=line_squares(moved,target)
        if not ray or target not in ray:continue
        passed=False
        for farther in ray[ray.index(target)+1:]:
            back=board.piece_at(farther)
            if back is None:continue
            if back.color==color:break
            if back.color!=victim.color:break
            # A pin: lower-value front piece lies between mover and king,
            # and the chess engine verifies it is pinned to the king.
            if back.piece_type==chess.KING and board.is_pinned(victim.color,target):
                typ="pin"
            elif VALUES[victim.piece_type]>VALUES[back.piece_type]:
                typ="skewer"
            else:
                break
            arrows.append({"from":square(moved),"to":square(farther),
                           "kind":typ,"label":typ.title()+" line"})
            features.append({"type":typ,"squares":[square(moved),square(target),square(farther)],
                "label":(PIECES[victim.piece_type].title()+" on "+square(target)+
                   " is in front of "+PIECES[back.piece_type]+" on "+square(farther)+".")})
            passed=True
            break
        if passed:continue
    # Do not duplicate arrows from one attack ray.
    used=set();unique=[]
    for a in arrows:
        key=(a["from"],a["to"],a["kind"])
        if key not in used:unique.append(a);used.add(key)
    return unique,features

def attack_map(board,move):
    """Threats arising from the moved piece after a legal move."""
    if move not in board.legal_moves:raise ValueError("Illegal annotation move")
    color=board.turn
    orig=square(move.from_square);dest=square(move.to_square)
    after=board.copy();after.push(move)
    mover=after.piece_at(move.to_square)
    if mover is None:return [],[],[],[]
    squares=[square(s) for s in after.attacks(move.to_square)]
    targets=[]
    for s in after.attacks(move.to_square):
        victim=after.piece_at(s)
        if victim and victim.color!=color:
            defended=after.is_attacked_by(victim.color,s)
            targets.append({"square":square(s),"piece":PIECES[victim.piece_type],
              "value":VALUES[victim.piece_type],"defended":defended})
    targets.sort(key=lambda x:-x["value"])
    arrows=[]
    features=[]
    if len([x for x in targets if x["value"]>=3])>=2:
        major=[x for x in targets if x["value"]>=3]
        for t in major[:3]:
            arrows.append({"from":dest,"to":t["square"],"kind":"fork","label":"Fork threat"})
        features.append({"type":"fork","squares":[dest]+[x["square"] for x in major[:3]],
           "label":(PIECES[mover.piece_type].title()+" on "+dest+" attacks "+
                    " and ".join(t["piece"]+" on "+t["square"] for t in major[:3])+".")})
    else:
        for t in targets[:4]:
            arrows.append({"from":dest,"to":t["square"],"kind":"attack",
                           "label":"Attacks "+t["piece"]})
    lines,line_features=_line_tactics(after,move.to_square,color)
    arrows.extend(lines);features.extend(line_features)
    # Discovered attacks: the moving piece vacated a square, opening a sliding
    # line from one of the mover's other pieces to an occupied enemy piece.
    discovered=[]
    for attacker,own_piece in after.piece_map().items():
        if own_piece.color!=color or own_piece.piece_type not in (chess.BISHOP,chess.ROOK,chess.QUEEN) or attacker==move.to_square:
            continue
        for threatened in after.attacks(attacker):
            v=after.piece_at(threatened)
            if v is None or v.color==color or v.piece_type==chess.PAWN:
                continue
            # A genuinely new attack from an UNMOVED piece, not a global
            # attack that existed in the old position.
            old_attacker=board.piece_at(attacker)
            if old_attacker is None or old_attacker.color!=color or old_attacker.piece_type!=own_piece.piece_type:
                continue
            if threatened not in board.attacks(attacker):
                discovered.append((attacker,threatened,v))
    if discovered:
        discovered.sort(key=lambda t:-VALUES[t[2].piece_type])
        attacker,target,v=discovered[0]
        arrows.append({"from":square(attacker),"to":square(target),"kind":"discovered",
                       "label":"Discovered attack"})
        features.append({"type":"discovered","squares":[square(move.from_square),square(attacker),square(target)],
            "label":("Moving away from "+orig+" opened a line from "+
                      PIECES[after.piece_at(attacker).piece_type]+" on "+square(attacker)+
                      " toward "+PIECES[v.piece_type]+" on "+square(target)+".")})
    # Alert only if the moved piece is attacked and genuinely lacks direct defense.
    danger=[]
    if mover.piece_type!=chess.KING and after.is_attacked_by(not color,move.to_square):
        if not after.is_attacked_by(color,move.to_square):
            danger.append({"square":dest,"type":"loose",
                           "label":PIECES[mover.piece_type].title()+" on "+dest+" is attacked and undefended."})
    return squares,targets,arrows,features+danger

def frame(board,move=None,role="best"):
    """A complete legal before/after snapshot; stores board squares only."""
    if move is None:
        return {"fen":board.fen(),"arrows":[],"targets":[],"controlled":[],"features":[],
                "move":None,"color":None}
    if move not in board.legal_moves:raise ValueError("Invalid move for training frame")
    before=board.copy()
    controls,targets,arrows,features=attack_map(board,move)
    after=board.copy()
    san=after.san(move)
    after.push(move)
    base=[{"from":square(move.from_square),"to":square(move.to_square),
           "kind":role,"label":san}]
    return {"fen":after.fen(),"move":san,"from":square(move.from_square),
            "to":square(move.to_square),"color":"White" if before.turn else "Black",
            "arrows":base+arrows,"targets":targets,"controlled":controls,"features":features}

def annotate(fen,best_san,chosen_san=None,best_pv=None,chosen_pv=None):
    """Returns the four teaching modes, with no arrows fabricated from SAN."""
    board=chess.Board(fen)
    best=board.parse_san(best_san)
    chosen=board.parse_san(chosen_san) if chosen_san else None
    best_frame=frame(board,best,"best")
    your_frame=frame(board,chosen,"alternative") if chosen else None
    start=frame(board)
    arrows=[{"from":square(best.from_square),"to":square(best.to_square),
            "kind":"best","label":"Best: "+best_san}]
    if chosen and chosen!=best:
        arrows.append({"from":square(chosen.from_square),"to":square(chosen.to_square),
               "kind":"alternative","label":"Your move: "+chosen_san})
    start["arrows"]=arrows
    reply_frame=None
    pv=list(best_pv or [])
    if len(pv)>1 and pv[0]==best:
        board_after=board.copy();board_after.push(best)
        reply=pv[1]
        if reply in board_after.legal_moves:
            reply_frame=frame(board_after,reply,"reply")
    return {"before":start,"best":best_frame,"your":your_frame,"reply":reply_frame,
            "theme":next((x["type"] for x in best_frame["features"]),None)}
