"""Evidence-only historical game conclusion, safe from narrative hallucinations."""
from __future__ import annotations
import chess

def outcome(rec,frames,analysis,facts):
 side=rec["winner"]
 final=chess.Board(frames[-1]["fen"])
 end=("The final position is checkmate; the board and legal moves verify this."
      if final.is_checkmate() else
      "The recorded game result does not establish the exact termination mechanism.")
 paragraph=("The recorded result is "+rec["result"]+
  " ("+("draw" if side=="Draw" else side+" won")+"). "+end)
 if not analysis or not analysis.get("sideFindings"):
  return (paragraph+" The result alone cannot identify a decisive mistake. "+
    "Select Analyze turning points for engine evidence and then ask again. "+
    "I won't invent an explanation of why a historical player lost. "+
    "You can still step through every actual move on the board and examine "+
    "their opponent's legal replies.")
 paragraphs=[paragraph]
 for player in ("White","Black"):
  r=analysis["sideFindings"].get(player,{})
  biggest=r.get("largestLoss")
  if not biggest:
   paragraphs.append("For "+player+", the sampled depth-9 checkpoints "+
     "did not exceed the configured evaluation-loss threshold. "+
     "Other, unexamined moves may still contain important mistakes.")
   continue
  number=(biggest["ply"]+1)//2
  prefix=str(number)+("." if biggest["ply"]%2 else "...")
  paragraphs.append(player+": "+str(r.get("flagged",0))+
    " potentially costly decisions in "+str(r.get("sampled",0))+
    " sampled checkpoints. Its largest observed evaluation loss was "+
    prefix+biggest["played"]+". At depth 9, Stockfish preferred "+
    biggest["best"]+" (roughly "+format(biggest["gapCp"]/100,".2f")+
    " pawns of evaluation difference). An analyzed continuation is "+
    biggest["line"]+". This identifies a plausible learning point, "+
    "not proof that this was the game's unique deciding move.")
 themes=facts["generic_familial_plans_NOT_board_proven"]
 paragraphs.append("Compare the broader strategic ideas. "+
   "A typical plan for White in this opening family: "+
   themes["White"]+" A typical Black response: "+
   themes["Black"]+" These plans are instructional patterns, not "+
   "historical mind-reading. To understand the finish, compare the "+
   "recorded moves against the engine alternatives and the actual "+
   "final board. Neither a result tag nor a sampled evaluation is "+
   "a complete explanation of a human decision.")
 paragraphs.append("Which sampled decision by the losing side should we "+
   "replay first? We can study the opponent's strongest continuation together.")
 return "\n\n".join(paragraphs)

def position(rec,facts):
 turn=facts["side_to_move"]
 actual=facts.get("next_ACTUAL_historical_move")
 engine=facts.get("current_position_depth_10")
 note=("At this exact game position ("+turn+" to move), the next recorded "+
  "move is "+actual+"." if actual else
  "This is the final recorded position and no further move is known.")
 if engine:
  note+=(" Stockfish's depth-10 candidate is "+engine["bestSan"]+
   ", with continuation "+engine["bestLine"]+
   ". The recorded move's estimated loss is "+
   str(round(engine["lossCp"]/100,2))+" pawns at this limited depth.")
 concepts=facts["generic_familial_plans_NOT_board_proven"]
 return (note+"\n\n"+
  "White's usual opening-family goal: "+concepts["White"]+
  " Black's possible counterplan: "+concepts["Black"]+
  " These are general strategic patterns; they cannot reveal either "+
  "player's private thoughts. The specific engine continuation is "+
  "the appropriate test of an alternative here."+
  "\n\nWhich exact move or defensive resource should we examine next?")
