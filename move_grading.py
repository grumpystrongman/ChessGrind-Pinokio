"""Stockfish move grading with alternative-move credit and instructive variations."""
import chess
import chess.engine
from game_analysis import find_engine
from lesson_explainer import explain

def _score(info,color):
    return info["score"].pov(color).score(mate_score=20000)

def grade(fen,played,best_san,depth=11,tolerance_cp=65):
    """Credit an alternative if its score is within the configured tolerance.
    Analyze both moves at the same depth to make the comparison fair.
    """
    board=chess.Board(fen)
    if played not in board.legal_moves:raise ValueError("Illegal move")
    original=board.parse_san(best_san)
    path=find_engine()
    if path is None:
        raise RuntimeError("Stockfish is required to grade and explain a position.")
    with chess.engine.SimpleEngine.popen_uci(path,timeout=30) as engine:
        engine.configure({"Threads":1,"Hash":64})
        limit=chess.engine.Limit(depth=depth)
        strongest=engine.analyse(board,limit)
        top=strongest.get("pv",[original])[0]
        # Preserve the originally stored best move when it is also competitive.
        # But do not automatically credit it if a deeper engine finds it poor.
        if original==top:
            original_info=strongest
        else:
            original_info=engine.analyse(board,limit,root_moves=[original])
        if played==top:
            candidate=strongest
        elif played==original:
            candidate=original_info
        else:
            candidate=engine.analyse(board,limit,root_moves=[played])
    top_score=_score(strongest,board.turn)
    actual_score=_score(candidate,board.turn)
    diff=max(0,top_score-actual_score)
    accepted=diff<=tolerance_cp
    best_san_current=board.san(top)
    # Avoid pretending a score is an exact assessment of a beginner's skill.
    lesson=explain(fen,board.san(played),best_san_current,
       best_pv=strongest.get("pv",[]),chosen_pv=candidate.get("pv",[]),
       accepted=accepted,difference_cp=diff)
    from visual_coach import annotate
    visual=annotate(fen,best_san_current,
        chosen_san=board.san(played) if played!=top else None,
        best_pv=strongest.get('pv',[]),chosen_pv=candidate.get('pv',[]))
    if accepted:
        message=("Excellent: that matches the best move." if played==top else
          "Good alternative: this move is close enough to Stockfish's top choice for full credit.")
    else:
        message=("That move is legal, but Stockfish finds a stronger continuation. "+
                 "Study the concrete line and the chess principle below.")
    return {"accepted":accepted,"difference_cp":diff,"best_san":best_san_current,
            "played_san":board.san(played),"explanation":message,"lesson":lesson,
            "visual":visual,"best_line":lesson["bestLine"],"your_line":lesson["yourLine"]}
