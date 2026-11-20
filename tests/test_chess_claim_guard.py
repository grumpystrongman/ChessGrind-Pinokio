"""Regression fixtures for ChessGrind's board-grounded dialogue guard.

No live model is required: tests must catch known false assertions exactly,
then separately check real responses in a local HTTP integration run.
"""
import chess
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from chess_claim_guard import inspect,validate,safe_fallback
from conversational_chess import PERSONALITIES

START=chess.Board()
CHECK=chess.Board()
for san in ["f3","e5","g4","Qh4#"]:
    CHECK.push_san(san)
assert CHECK.is_checkmate()
MID=chess.Board()
for san in ["e4","e5","Nf3","Nc6","Bc4","Bc5"]:
    MID.push_san(san)
CHECK_ONLY=chess.Board("4k3/8/8/8/8/8/4R3/4K3 b - - 0 1")
assert CHECK_ONLY.is_check() and not CHECK_ONLY.is_checkmate()
rows=[
 ("Checkmate claimed at start","This is checkmate!",START,False,None,True),
 ("False stalemate","This is stalemate.",START,False,None,True),
 ("Impossible piece claim","The white queen on h7 is attacking.",START,False,None,True),
 ("Wrong-color piece","Your black king on e1 is trapped.",START,False,None,True),
 ("Unproven forced mate","I have forced mate in 3.",MID,False,None,True),
 ("Invented winning eval","You are clearly winning.",MID,False,None,True),
 ("Unverified engine source","Stockfish confirms e4 is best.",START,False,None,True),
 ("Leaking best-move advice","The best move is e4.",START,False,None,True),
 ("Incorrect check claim","Your king is in check.",MID,False,None,True),
 ("Illegal post-game suggestion","Right now play Qh7.",MID,True,None,True),
 ("Neutral tactics principle","Before moving, scan checks and captures.",START,False,None,False),
 ("Accurate named white pawn","The white pawn on e4 helps control the center.",MID,False,None,False),
 ("Verified check","Black is in check. Look for an escape.",CHECK_ONLY,False,None,False),
 ("Actual checkmate","This is checkmate.",CHECK,True,None,False),
 ("Wrong king named","White is in check.",CHECK_ONLY,False,None,True),
 ("False adjacent kings","You've got your kings side by side, ready to fight.",START,False,None,True),
 ("False adjacent black and white kings","The kings are adjacent.",MID,False,None,True),
 ("Impossible empty start board","The board is entirely empty.",START,False,None,True),
 ("Accurate board not empty","The board has pieces and pawn lines.",START,False,None,False),
 ("No unverified win claim","I would examine the king's safety before a pawn push.",MID,False,None,False),
 ("Historical line not forced","The archived master played e4. That was a human choice.",START,False,None,False),
 ("Mate as teaching concept","Learn the checkmate patterns in this lesson.",START,False,None,False),
 ("Passed pawn hypothetical","A passed pawn may matter in some endings.",START,False,None,False),
]
failed=[]
for name,text,board,finished,grade,bad in rows:
    outcome=validate(text,board,human_color="White",
                     game_finished=finished,grade=grade)
    if outcome["ok"]==bad:failed.append((name,outcome["findings"]))
    print(("PASS" if outcome["ok"]!=bad else "FAIL"),name,
          [x["code"] for x in outcome["findings"]],flush=True)
assert not failed,failed
assert len(PERSONALITIES)==27
for persona in [{"name":"MAX","id":"max"},{"name":"Coach Vera","id":"coach-vera"}]:
    for board,finished,grade in [
        (START,False,None),(CHECK_ONLY,False,None),
        (CHECK,True,None),(MID,False,{"categoryOfPreviousHumanMove":"blunder",
                                       "previousHumanMove":"c3"})]:
        text=safe_fallback(persona=persona,event="turn",board=board,
                           finished=finished,grade=grade)
        result=validate(text,board,human_color="White",
                        game_finished=finished,grade=grade)
        assert result["ok"],(persona,text,result)
print("GUARD QA PASS:",len(rows),"adversarial fixtures, 8 fallbacks, 27 distinct personas")
