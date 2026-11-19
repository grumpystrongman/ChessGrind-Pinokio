"""Board-grounded Opening Coach: decision lesson, legal engine variations, memory prompts.

Uses stored imported game positions; saves nothing until learner explicitly chooses.
No claims of ECO opening identity or forced winning lines without verification.
"""
from __future__ import annotations
from collections import Counter
import chess
import chess.engine
from opening_repertoire import position,board_key,_data,USER
from chess_grind import db
from game_analysis import find_engine
from lesson_explainer import variation,move_reasons

CENTRAL={chess.D4,chess.E4,chess.D5,chess.E5}
def snapshot(board):
    """Observable board features, not unqualified strategic verdicts."""
    result={}
    for white,label in ((True,"White"),(False,"Black")):
        back=0 if white else 7
        initial={chess.B1,chess.G1,chess.C1,chess.F1} if white else {chess.B8,chess.G8,chess.C8,chess.F8}
        undeveloped=sum(bool(board.piece_at(sq) and board.piece_at(sq).color==white
            and board.piece_at(sq).piece_type in (chess.KNIGHT,chess.BISHOP)) for sq in initial)
        center_pawns=[chess.square_name(sq) for sq in CENTRAL if (p:=board.piece_at(sq))
            and p.color==white and p.piece_type==chess.PAWN]
        king=board.king(white)
        castled=king in ((chess.G1,chess.C1) if white else (chess.G8,chess.C8))
        result[label]={"undevelopedMinorPieces":undeveloped,
             "centralPawns":sorted(center_pawns),"kingOnCastledSquare":castled,
             "kingSquare":chess.square_name(king) if king is not None else None}
    return result

def _stage(board,features):
    ply=board.ply()
    if ply<=2:return "Choose a central foothold and prepare your development."
    side="White" if board.turn else "Black"
    if features[side]["undevelopedMinorPieces"]>=3:
        return "Most of your knights and bishops remain on their original squares. Look for a developing move that also influences the center."
    if board.has_castling_rights(board.turn) and not features[side]["kingOnCastledSquare"]:
        return "Your minor pieces have begun developing. Consider king safety, castling access, and whether a central break is timely."
    return "Now assess the opponent's threats and choose a plan; avoid assuming a memorized sequence still applies."

def _explain_move(board,move):
    """Exactly verifiable move motifs from current board."""
    piece=board.piece_at(move.from_square)
    san=board.san(move)
    reasons=[]
    if board.is_castling(move):
        reasons.append("This move castles your king and activates a rook.")
    if piece.piece_type==chess.PAWN:
        if chess.square_file(move.to_square) in (3,4):
            reasons.append("This pawn advance contests a central file and changes which squares your pawn controls.")
        if move.to_square in CENTRAL:
            reasons.append("Your pawn occupies one of the four central squares.")
        if board.is_capture(move):
            reasons.append("This pawn captures a piece and changes the pawn structure.")
    if piece.piece_type in (chess.KNIGHT,chess.BISHOP):
        start=(chess.square_rank(move.from_square)==(0 if board.turn else 7))
        if start:reasons.append("This develops a knight or bishop from its original rank.")
    after=board.copy();after.push(move)
    if piece.piece_type==chess.PAWN:
        center_attacks=sorted(chess.square_name(sq) for sq in
            after.attacks(move.to_square) if sq in CENTRAL)
        if center_attacks:
            reasons.append("Your pawn on "+chess.square_name(move.to_square)+
                " controls central square(s) "+", ".join(center_attacks)+
                ". That influences where the opponent can safely place pieces and pawns.")
    if after.is_check():reasons.append("The move gives check, so the opponent must respond to it immediately.")
    if piece.piece_type in (chess.KNIGHT,chess.BISHOP,chess.ROOK,chess.QUEEN):
        targets=[chess.square_name(sq) for sq in after.attacks(move.to_square)
                 if (enemy:=after.piece_at(sq)) and enemy.color!=piece.color
                 and enemy.piece_type!=chess.KING]
        if targets:reasons.append("From its new square, this piece attacks occupied enemy square(s): "+", ".join(targets[:4])+".")
    if not reasons:
        reasons.append("This is a legal candidate. Compare its next position and the opponent's reply before making it part of your plan.")
    return reasons[:4]

def changes(board, move):
    """Explain measurable consequences on this board, never invented plans."""
    after=board.copy();after.push(move)
    mover=board.turn
    before=snapshot(board)["White" if mover else "Black"]
    now=snapshot(after)["White" if mover else "Black"]
    messages=[]
    if now["centralPawns"]!=before["centralPawns"]:
        new=sorted(set(now["centralPawns"])-set(before["centralPawns"]))
        removed=sorted(set(before["centralPawns"])-set(now["centralPawns"]))
        if new:messages.append("Your pawns now occupy "+", ".join(new)+" in the center.")
        if removed:messages.append("Your pawn no longer occupies "+", ".join(removed)+".")
    difference=before["undevelopedMinorPieces"]-now["undevelopedMinorPieces"]
    if difference>0:messages.append(str(difference)+" knight or bishop left its original square.")
    for sq in ((chess.C1,chess.F1) if mover else (chess.C8,chess.F8)):
        bishop=board.piece_at(sq)
        if not bishop or bishop.piece_type!=chess.BISHOP or bishop.color!=mover:continue
        before_attack=set(board.attacks(sq))
        after_attack=set(after.attacks(sq))
        new=[chess.square_name(x) for x in sorted(after_attack-before_attack)]
        if new:messages.append("Your bishop on "+chess.square_name(sq)+
          " gains access to "+", ".join(new[:5])+".")
    opponent=not mover
    captures=[chess.square_name(m.to_square) for m in after.legal_moves if after.is_capture(m)]
    if captures:messages.append("The opponent has immediate legal captures on "+", ".join(captures[:4])+
        "; inspect them before settling on your next move.")
    if after.is_check():
        messages.append("Your move gives check, forcing the opponent to answer the check.")
    if not messages:messages.append("The geometry changed, but no simple verified central-development indicator captures its value. Compare the two engine continuations.")
    return messages[:5]

def _format_score(info,perspective):
    p=info["score"].pov(perspective)
    cp=p.score(mate_score=20000)
    if p.is_mate():return {"display":("Mate for you in " if p.mate()>0 else "Mate against you in ")+str(abs(p.mate())),"cp":cp}
    return {"display":("%+.2f"%(cp/100)),"cp":cp}

def _branch(board,pv,info,perspective,role):
    replay=board.copy()
    steps=[{"fen":replay.fen(),"move":None,"uci":None,"index":0}]
    for m in pv[:6]:
        if m not in replay.legal_moves:break
        san=replay.san(m);replay.push(m)
        steps.append({"fen":replay.fen(),"move":san,"uci":m.uci(),"index":len(steps)})
    return {"role":role,"san":board.san(pv[0]),"uci":pv[0].uci(),
      "score":_format_score(info,perspective),"steps":steps,
      "line":variation(board,pv,max_plies=6),
      "why":_explain_move(board,pv[0])}

def lesson(fen,uci=None):
    observed=position(fen)
    board=chess.Board(observed["fen"])
    if not observed["observedGames"]:
        raise ValueError("Choose a position you actually reached in an imported game")
    features=snapshot(board)
    side="White" if board.turn else "Black"
    focus=_stage(board,features)
    chosen=None
    if uci:
        if not isinstance(uci,str) or len(uci) not in (4,5):raise ValueError("Invalid candidate move")
        chosen=chess.Move.from_uci(uci)
        if chosen not in board.legal_moves:raise ValueError("Candidate is not a legal move")
    elif observed["savedMove"]:
        chosen=chess.Move.from_uci(observed["savedMove"])
    elif observed["options"]:
        chosen=chess.Move.from_uci(observed["options"][0]["uci"])
    else:raise ValueError("No observed continuation found")
    # Crucial: the most common observed move is an EXAMPLE, not an endorsed best move.
    path=find_engine()
    if not path:raise RuntimeError("Stockfish not found; the interactive opening comparison needs the local engine.")
    with chess.engine.SimpleEngine.popen_uci(path,timeout=40) as eng:
        eng.configure({"Threads":1,"Hash":64})
        limit=chess.engine.Limit(depth=11)
        entries=eng.analyse(board,limit,multipv=min(3,board.legal_moves.count()))
        if isinstance(entries,dict):entries=[entries]
        entries=[r for r in entries if r.get("pv")]
        if not entries:raise RuntimeError("Stockfish did not return an opening continuation")
        best=entries[0]
        sample=next((r for r in entries if r["pv"][0]==chosen),None)
        if sample is None:
            sample=eng.analyse(board,limit,root_moves=[chosen])
        if not sample.get("pv"):raise RuntimeError("No valid engine line for selected move")
        top=_branch(board,best["pv"],best,board.turn,"engine")
        picked=_branch(board,sample["pv"],sample,board.turn,"candidate")
        opponent_after=board.copy();opponent_after.push(chosen)
        reply=picked["steps"][2]["move"] if len(picked["steps"])>2 else "No legal reply available"
        delta=max(0,top["score"]["cp"]-picked["score"]["cp"])
    verified_changes=changes(board,chosen)
    reply_reasons=[]
    if len(picked["steps"])>2:
        b_after=board.copy();b_after.push(chosen)
        reply_move=chess.Move.from_uci(picked["steps"][2]["uci"])
        reply_reasons=_explain_move(b_after,reply_move)
    lesson_lines=[
      {"title":"Read this position","detail":focus},
      {"title":"What this move changes","detail":" ".join(picked["why"]+verified_changes)},
      {"title":"What the opponent can do","detail":"After "+picked["san"]+", the depth-11 engine's leading reply is "+reply+
          ". "+" ".join(reply_reasons)+
          " This is an analyzed continuation, not a forced move unless a check or mate requires it."},
      {"title":"Your next-game habit","detail":"When you recognize this pawn and piece arrangement, first ask: "+
         "What central squares changed, what is newly attacked, and what is the opponent's best reply? "+
         "A move belongs in your repertoire only if you understand that answer."}
    ]
    return {"fen":board.fen(),"side":side,"observedGames":observed["observedGames"],
      "candidate":picked,"best":top,
      "comparisonCp":delta,"comparable":delta<=65,
      "features":features,"boardChanges":verified_changes,
      "openingStage":focus,"lesson":lesson_lines,
      "savedMove":observed["savedMove"],"mostPlayed":observed["options"][0]["san"],
      "nextQuestion":"After "+picked["san"]+", which reply would you prepare for, and what is your plan if it occurs?",
      "reviewPrompt":"Without viewing the line: explain why "+picked["san"]+
          " makes sense here, then name the opponent's strongest reply from the example.",
      "limits":"Stockfish depth 11. A leading reply is not always forced. These are legal engine continuations and observed board features, not a comprehensive opening-theory or ECO database."}
