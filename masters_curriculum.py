"""Story-style guided chapters from documented historical games.

Chapter descriptions distinguish verified moves from possible strategies.
They are generated anew from original legally replayed game score, not copied
historical commentary. No emotional or psychological attributions to players.
"""
from __future__ import annotations
import chess
from opening_theory_cards import theory
PROFILES={
 "Morphy":("Rapid development and open lines","Study how open files, coordinated pieces and initiative can decide a position while the opponent lags in development."),
 "Anderssen":("Romantic-era sacrifices","Observe forcing moves and the importance of calculating the defender's options before sacrificing material."),
 "Steinitz":("Accumulating positional advantages","Study the transition from direct attack to understanding structure, space and weaknesses."),
 "Lasker":("Resourceful practical defense","Consider how both players complicate or simplify positions and handle imperfect plans."),
 "Capablanca":("Endgame technique and simplicity","Notice active pieces, sound exchanges, clear pawn structures and purposeful endgames."),
 "Alekhine":("Dynamic attacks and calculation","Study how positional pressure creates tactical chances, with concrete verification."),
 "Botvinnik":("Strategic preparation","Focus on pawn structures, long-term plans and timely positional transformation."),
 "Tal":("Tactical imagination and sacrifices","Reconstruct forcing lines and ask whether defenders had better resources."),
 "Fischer":("Opening precision and active pieces","Track central play, coordinated development and conversion of advantages."),
 "Karpov":("Restricting opposing pieces","Observe how space, maneuvering and gradual pressure constrain the opponent."),
 "Kasparov":("Dynamic initiative and central breaks","Study activity, tactical complications and the timing of forcing play."),
 "PolgarJ":("Attacking chess and concrete calculation","Compare ambitious attacking ideas with the opponent's best defense."),
 "Anand":("Calculation and practical decisions","Focus on tactical alertness, activity and dynamic opening transitions."),
 "Carlsen":("Endgame persistence and small advantages","Explore king activity, pawn weaknesses and the conversion of small edges."),
 "Gaprindashvili":("Active universal chess","Study coordination and practical choices across all phases."),
 "Hou":("Balanced strategic and tactical play","Compare structural plans and concrete tactical opportunities."),
 "Kramnik":("Opening structure and strong defense","Study prophylaxis, piece activity and the strategic logic behind exchanges."),
 "Petrosian":("Prophylaxis and restriction","Before each move ask what threat it prevents and which enemy piece is restrained."),
 "Nimzowitsch":("Blockades and prophylaxis","Observe outposts, pawn chains, and controlling important squares without occupying them."),
 "Spassky":("Classical and dynamic balance","Explore the transition between sound development, attack and defense."),
 "Ding":("Resilience and complexity","Analyze defensive resources, exchanges, and counterplay in complex positions."),
 "Gukesh":("Calculation and practical fighting chess","Test concrete tactics and opponent resources, not just memorized lines."),
 "Smyslov":("Piece harmony","Watch how small improvements in coordination make a plan easier."),
 "Euwe":("Classical development and active plans","Explore the balance between pawn structure and piece activity."),
 "Bronstein":("Creative central counterplay","Look for tactical resources against seemingly quiet advantages."),
 "Rubinstein":("Rook endgames and positional coordination","Study piece harmony, activity and pawn endings."),
 "Reti":("Hypermodern central influence","Observe how pieces exert central influence without early pawn occupation."),
 "Tarrasch":("Classical central principles","Test when active central play makes structural concessions worthwhile."),
 "Keres":("Active attacking choices","Study tactical calculation in otherwise strategic positions."),
 "Caruana":("Opening precision and calculation","Compare concrete variations with longer strategic goals."),
 "Nakamura":("Dynamic initiative and complications","Study practical decision-making and calculation under pressure."),
 "Kosteniuk":("Active positional and tactical play","Learn to compare candidate plans from both sides."),
 "Chiburdanidze":("Positional technique","Study restrained development and the conversion of structural strengths."),
 "Stefanova":("Dynamic practical chess","Observe how forcing play connects to structural advantages."),
 "Koneru":("Positional control and technique","Study central control and how advantages are converted."),
 "Staunton":("Early modern opening development","Compare open-game development with the opponent's defensive resources."),
 "Reshevsky":("Defensive resourcefulness","Study positions where the defender has resilient counterplay."),
 "Korchnoi":("Counterattack and defense","Ask how the defender creates active chances rather than waiting."),
 "Chigorin":("Active piece play","Watch how dynamic piece play can challenge apparently stable structures.")
}
def profile(source):
 theme,practice=PROFILES.get(source,("Historic chess decisions",
    "Practice reading both sides and verifying tactical claims against legal moves."))
 return {"name":source,"knownFor":theme,"studyFocus":practice,
    "scope":"These are general teaching themes, not claims about every move or a player's private thinking."}

def walkthrough(record,moves,analysis=None):
 if not moves:return []
 last=len(moves)-1
 raw=[0,4,9,15,22,32,45,62,last-7]
 if last>75:raw.append(round(last*.78))
 raw.append(max(0,last-1))
 indices=sorted({max(0,min(last-1,i)) for i in raw if i<last})
 if len(indices)>9:
  indices=[indices[i] for i in (0,1,2,3,4,5,6,7,-1)]
 result=[]
 family=theory(record.get("opening") or "", "White")
 for i,ply in enumerate(indices):
  board=chess.Board(moves[ply]["fen"]);following=moves[ply+1]
  phase="Opening" if ply<20 else "Middlegame" if ply<65 else "Endgame or late middlegame"
  moments=[a for a in (analysis or {}).get("turningPoints",[]) if abs(a["ply"]-(ply+1))<=2]
  shift=moments[0] if moments else None
  mover=following["side"]
  if ply==0:title="The first strategic choices"
  elif shift:title="A possible turning point"
  elif phase=="Opening":title="Development and central tension"
  elif phase=="Middlegame":title="Plans meet resistance"
  else:title="Converting or defending the endgame"
  verified=following.get("observedChanges") or following.get("moveFacts") or []
  comment=("The next recorded move is "+following["san"]+" by "+mover+". "+
           (" ".join(verified[:2]) if verified else
            "Compare the board before and after the move."))
  if shift:
   comment+=(" At a sampled depth-9 checkpoint, the engine preferred "+shift["bestSan"]+
      " to the recorded "+shift["playedSan"]+". "+
      "This is a candidate decision to investigate, not a proven single cause of the result.")
  result.append({"index":i,"ply":ply,"title":title,"phase":phase,
   "sideToMove":"White" if board.turn else "Black",
   "nextMove":following["san"],"nextSide":mover,
   "comment":comment,
   "whitePlan":family["white"],"blackPlan":family["black"],
   "question":"Before revealing "+mover+"'s move, what is the strongest threat you can identify for each side, and what would you play?",
   "limits":"The next historical move is recorded fact. General strategic plans are interpretations unless supported by this position's exact board evidence."})
 return result
