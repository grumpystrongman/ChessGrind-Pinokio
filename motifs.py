"""Explainable tactical motifs inferred from actual board geometry.

These labels are tactical clues, not Stockfish-proof tactical motifs. They
require a verified legal engine move and position. No fabricated chess claims.
"""
import chess

PIECE_NAMES={chess.PAWN:"pawn",chess.KNIGHT:"knight",chess.BISHOP:"bishop",
             chess.ROOK:"rook",chess.QUEEN:"queen",chess.KING:"king"}
VALUE={chess.PAWN:1,chess.KNIGHT:3,chess.BISHOP:3,
       chess.ROOK:5,chess.QUEEN:9,chess.KING:10}

def classify(record):
    try:
        board=chess.Board(record["fen"])
        selected=board.parse_san(record["best"])
        played=board.parse_san(record["move"])
    except (KeyError,ValueError):
        return {"topic":"calculation","evidence":"Compare candidate moves and forcing replies."}
    mover=board.turn
    piece=board.piece_at(selected.from_square)
    next_board=board.copy()
    next_board.push(selected)
    if next_board.is_checkmate():
        return {"topic":"checkmate patterns",
                "evidence":"The stronger continuation gives immediate checkmate."}
    # Identify double attacks by the same moved piece, including attacks on the king.
    attacking=next_board.piece_at(selected.to_square)
    if attacking and attacking.piece_type in (chess.KNIGHT,chess.PAWN,chess.BISHOP,chess.QUEEN,chess.ROOK):
        targets=[]
        for square,p in next_board.piece_map().items():
            if (p.color!=mover and p.piece_type!=chess.PAWN and
                    next_board.is_attacked_by(mover,square)):
                # Only count direct attack by the moved piece.
                if square in next_board.attacks(selected.to_square):
                    targets.append((square,p))
        if len(targets)>=2:
            detail=", ".join(PIECE_NAMES[p.piece_type]+" on "+chess.square_name(sq) for sq,p in targets[:3])
            return {"topic":"forks and double attacks",
                    "evidence":piece.symbol().upper()+" move "+record["best"]+" attacks "+detail+"."}
    # New absolute pins against the enemy king.
    pinned=[]
    for square,p in next_board.piece_map().items():
        if p.color!=mover and p.piece_type!=chess.KING:
            if next_board.is_pinned(p.color,square) and not board.is_pinned(p.color,square):
                pinned.append((square,p))
    if pinned:
        square,p=pinned[0]
        return {"topic":"pins","evidence":"The stronger move creates a pin on "+
                PIECE_NAMES[p.piece_type]+" at "+chess.square_name(square)+"."}
    # A missed forcing check or useful capture.
    if board.gives_check(selected):
        return {"topic":"forcing checks","evidence":"The stronger move gives check and forces a reply."}
    if board.is_capture(selected):
        victim=board.piece_at(selected.to_square)
        if board.is_en_passant(selected): victim=chess.Piece(chess.PAWN,not mover)
        if victim:
            return {"topic":"missed captures","evidence":"The stronger move captures a "+
                    PIECE_NAMES[victim.piece_type]+"."}
    # A hanging piece after the player's recorded choice.
    after=board.copy()
    after.push(played)
    own_piece=after.piece_at(played.to_square)
    if own_piece and own_piece.color==mover and own_piece.piece_type!=chess.PAWN:
        if after.is_attacked_by(not mover,played.to_square) and not after.is_attacked_by(mover,played.to_square):
            return {"topic":"piece safety","evidence":"Your move leaves the "+PIECE_NAMES[own_piece.piece_type]+
                " on "+chess.square_name(played.to_square)+" attacked without direct protection."}
    # Endgames and opening development require separate study habits.
    heavy=sum(1 for p in board.piece_map().values() if p.piece_type not in (chess.PAWN,chess.KING))
    if heavy<=3:
        return {"topic":"endgame technique","evidence":"Few non-pawn pieces remain; calculate king and pawn activity."}
    if board.fullmove_number<=8:
        return {"topic":"opening decisions","evidence":"Review development, king safety, and loose pieces in the opening."}
    return {"topic":"calculation","evidence":"No single verified motif explains this evaluation loss; calculate forcing continuations."}

if __name__=="__main__":
    import sys
    from game_analysis import dashboard_data
    from collections import Counter
    mistakes=dashboard_data()["mistakes"]
    print(Counter(classify(m)["topic"] for m in mistakes))
