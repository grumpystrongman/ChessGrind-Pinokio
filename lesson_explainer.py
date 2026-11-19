"""Teach the *reason* behind a strong chess move, using verified board geometry
and replayable Stockfish variations, rather than centipawn numbers alone.

This is a deterministic instructional layer: claims about captures, checks,
double attacks and loose pieces are checked against the actual legal position.
"""
import chess
from motifs import classify

PIECES={chess.PAWN:"pawn",chess.KNIGHT:"knight",chess.BISHOP:"bishop",
        chess.ROOK:"rook",chess.QUEEN:"queen",chess.KING:"king"}
VALUE={chess.PAWN:1,chess.KNIGHT:3,chess.BISHOP:3,chess.ROOK:5,chess.QUEEN:9,chess.KING:20}

def variation(board, moves, max_plies=6):
    """SAN, with conventional move numbers and no guessing about future play."""
    work=board.copy()
    result=[]
    for move in list(moves or [])[:max_plies]:
        if move not in work.legal_moves:break
        prefix=(str(work.fullmove_number)+".") if work.turn==chess.WHITE else (
            str(work.fullmove_number)+"..." if not result else "")
        result.append((prefix+" " if prefix else "")+work.san(move))
        work.push(move)
    return " ".join(result)

def _target_details(board, move):
    """Identify direct targets of the moved piece, not attacks by unrelated pieces."""
    after=board.copy()
    color=board.turn
    piece=board.piece_at(move.from_square)
    after.push(move)
    attacked=[]
    if piece and after.piece_at(move.to_square):
        for sq in after.attacks(move.to_square):
            victim=after.piece_at(sq)
            if victim and victim.color!=color and victim.piece_type!=chess.PAWN:
                attacked.append((VALUE[victim.piece_type],PIECES[victim.piece_type],
                                 chess.square_name(sq)))
    attacked.sort(reverse=True)
    return attacked

def move_reasons(board,move):
    """Explanations are restricted to facts verifiable from this exact board."""
    mover=board.piece_at(move.from_square)
    if not mover:return ["The candidate move should be reviewed on the chessboard."]
    piece=PIECES[mover.piece_type]
    to=chess.square_name(move.to_square)
    reasons=[]
    if board.is_castling(move):
        reasons.append("Castling usually moves your king toward safety and brings a rook closer to the center.")
    if board.is_capture(move):
        victim=board.piece_at(move.to_square)
        if board.is_en_passant(move):victim=chess.Piece(chess.PAWN,not board.turn)
        if victim:
            reasons.append("It captures the opponent's "+PIECES[victim.piece_type]+
                           ", changing the material on the board immediately.")
    if board.gives_check(move):
        reasons.append("It gives check. Your opponent must answer the check before carrying out another plan.")
    after=board.copy()
    after.push(move)
    if after.is_checkmate():
        reasons.insert(0,"It is checkmate: the enemy king has no legal escape.")
    threats=_target_details(board,move)
    if len(threats)>=2:
        first=", ".join(x[1]+" on "+x[2] for x in threats[:2])
        reasons.append("It attacks two valuable pieces at once ("+first+
                      "). One reply may not save both targets: this is a double attack.")
    elif len(threats)==1 and not board.gives_check(move):
        target=threats[0]
        reasons.append("From "+to+", your "+piece+" directly attacks their "+target[1]+
                       " on "+target[2]+". Check whether that piece can move or is defended.")
    if mover.piece_type==chess.PAWN:
        if board.fullmove_number<=12 and chess.square_file(move.from_square) in (5,6,7) and not board.is_castling(move):
            old_guarded={chess.square_name(sq) for sq in board.attacks(move.from_square)}
            new_guarded={chess.square_name(sq) for sq in after.attacks(move.to_square)}
            lost=sorted(old_guarded-new_guarded)
            if lost:
                reasons.append('This early kingside pawn move stops defending '+', '.join(lost[:2])+'. Consider whether your king needs that protection.')
        if chess.square_rank(move.to_square) in (3,4) and chess.square_file(move.to_square) in (3,4):
            reasons.append("This pawn occupies a central square, influencing where both sides can develop.")
        if move.promotion:
            reasons.append("The pawn promotes, gaining the power of a "+PIECES[move.promotion]+".")
    if mover.piece_type in (chess.KNIGHT,chess.BISHOP) and board.fullmove_number<=10:
        back=0 if board.turn==chess.WHITE else 7
        if chess.square_rank(move.from_square)==back and chess.square_rank(move.to_square)!=back:
            reasons.append("It develops a "+piece+" from its starting rank so it can influence more squares.")
    if mover.piece_type==chess.KING and not board.is_castling(move) and board.fullmove_number>=25:
        reasons.append("In many endgames, an active king can help support pawns; first check that this square is safe.")
    return reasons

def _weakness(board,chosen):
    if not chosen:return None
    after=board.copy()
    color=board.turn
    mover=board.piece_at(chosen.from_square)
    after.push(chosen)
    if not mover:return None
    destination=chosen.to_square
    if (mover.piece_type!=chess.KING and
        after.is_attacked_by(not color,destination) and
        not after.is_attacked_by(color,destination)):
        return "After your move, the "+PIECES[mover.piece_type]+" on "+chess.square_name(destination)+(
            " is attacked and has no direct defender. Check whether it can be captured." )
    return None

HABITS={
    "forks and double attacks":"After every candidate move, scan whether one piece attacks two enemy targets. Also check if your opponent can do this to you.",
    "pins":"Look along bishop, rook, and queen lines. Ask which piece cannot move because something more valuable stands behind it.",
    "checkmate patterns":"Start with checks, then list all legal king escapes, blocks, and captures. Do not stop at the first check.",
    "forcing checks":"Calculate your checks first, but only play one when the forced response helps your position.",
    "missed captures":"List every available capture, then count attackers and defenders before deciding whether the exchange helps you.",
    "piece safety":"Before you release a piece, imagine it already sits on the new square. What could your opponent capture immediately?",
    "opening decisions":"Develop pieces, fight for the center, protect the king, and avoid leaving pieces undefended.",
    "endgame technique":"Count pawn moves to promotion, activate your king when safe, and calculate forcing checks and captures.",
    "calculation":"Find two candidate moves. For each, calculate your opponent's most forcing reply before you choose."
}

def explain(fen,chosen_san,best_san,best_pv=None,chosen_pv=None,accepted=False,difference_cp=None):
    board=chess.Board(fen)
    best=board.parse_san(best_san)
    chosen=board.parse_san(chosen_san) if chosen_san else None
    # A motif is an inference; disclose it as a study theme rather than a proof of the variation.
    data=classify({"fen":fen,"best":best_san,"move":chosen_san or best_san})
    topic=data["topic"]
    reasons=move_reasons(board,best)
    label=("Your move is a good alternative." if accepted and chosen and chosen!=best else
           "You found a strong move." if accepted else
           "Here's the idea you missed." if chosen else
           "Why this move works")
    headline=label+" Study theme: "+topic+"."
    if chosen and chosen==best:
        comparison="You chose "+chosen_san+", the engine's selected move. This earned full credit."
    elif accepted:
        comparison=("You chose "+chosen_san+" instead of "+best_san+
                    ". Stockfish evaluated both as sufficiently strong at the analysis depth; "+
                    "you receive full credit. There is often more than one good move in chess.")
    elif chosen:
        comparison=("You played "+chosen_san+". A stronger candidate is "+best_san+
                    ". Rather than memorizing that move, compare the opponent's best replies.")
    else:
        comparison="The recommended move is "+best_san+". Focus on its purpose and the reply it allows."
    weakness=_weakness(board,chosen) if chosen and not accepted else None
    why=" ".join(reasons) if reasons else (
        "The immediate move alone does not prove a simple fork, check, or capture. "+
        "Compare the engine continuations below: the position after the opponent's best reply "+
        "is the important part of this lesson.")
    if weakness and not accepted:why+=' '+weakness
    if chosen and chosen!=best:
        chosen_facts=move_reasons(board,chosen)
        if accepted and chosen_facts:
            why+=' Your alternative also has a sound purpose: '+ ' '.join(chosen_facts)
        elif not accepted and chosen_facts:
            why+=' Your move does have an idea: '+' '.join(chosen_facts)+ ' However, compare its consequences to the stronger continuation.'
    if not accepted and chosen and chosen!=best:
        replies=list(chosen_pv or [])
        if len(replies)>=2:
            after_chosen=board.copy();after_chosen.push(chosen)
            counter=replies[1]
            if counter in after_chosen.legal_moves:
                response=after_chosen.san(counter)
                counter_facts=move_reasons(after_chosen,counter)
                why+=' After '+board.san(chosen)+', the engine suggests your opponent can play '+response+'.'
                if counter_facts:
                    facts=' '.join(counter_facts).replace('Your opponent must answer the check', 'You must answer the check')
                    facts=facts.replace("your king needs that protection", "their king needs that protection")
                    why+=' '+facts
    pv_best=variation(board,best_pv or [best],6)
    pv_played=variation(board,chosen_pv or ([chosen] if chosen else []),6)
    if pv_best and len(list(best_pv or []))>1:
        why+=" The engine expects the following reply sequence, not necessarily what a human opponent will play."
    return {
        "headline":headline,
        "principle":why,
        "comparison":comparison,
        "bestLine":pv_best,
        "yourLine":pv_played if chosen and chosen!=best else "",
        "habit":HABITS.get(topic,HABITS["calculation"]),
        "topic":topic,
        "caution":"Variations are Stockfish predictions at limited depth; the positional lesson is based on verifiable board features.",
        "differenceCp":difference_cp,
    }
