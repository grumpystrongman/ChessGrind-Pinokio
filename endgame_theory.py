"""Deep chess endgame instruction grounded in legal position geometry.

Pedagogy is written per endgame theme and applies to either side. Claims
about the specific position are recomputed with python-chess. Does not
conflate depth-limited Stockfish evaluations with Syzygy proof.
"""
from __future__ import annotations
import chess
from endgame_lab import lesson as base_lesson, LESSONS

TOPICS={
 "opposition":{
  "definition":"Direct opposition means the two kings share a file or rank with exactly one square between them. The side that must move may have to yield ground.",
  "why":"This matters in pawn endings because kings cannot stand next to one another. Forcing the other king to step aside can create an entry square for your king or pawn.",
  "trap":"Opposition is not a magic win. A spare pawn move can change who must move first, and a king may be too far from the promotion squares.",
  "decision":"Name the square between the kings, identify whose turn it is, then list each king's legal moves and pawn waiting moves.",
  "memory":"One square between kings; count the tempo.",
  "questions":["Whose turn is it, and what would change if the other side moved?","Which legal pawn move could change the opposition?"]},
 "promotion-race":{
  "definition":"A passed pawn has no opposing pawn ahead of it on its own file or either adjacent file. It may still be stopped by an opposing king or piece.",
  "why":"A passed pawn creates a promotion deadline. Compare how many moves it needs to queen with whether the opposing king can intercept or give a checking resource.",
  "trap":"Don't count only your pawn's moves. Consider whose turn it is, whether the pawn can advance two squares, and whether promoting allows immediate capture.",
  "decision":"Trace every square the pawn must cross. Count both sides' legal moves and the defending king's route.",
  "memory":"Passed doesn't mean unstoppable; count both clocks.",
  "questions":["How many pawn advances remain before promotion?","Can the defending king enter the pawn's path in time?"]},
 "rook-activity":{
  "definition":"A rook behind its own passed pawn often supports the pawn's advance without needing to move as the pawn walks away.",
  "why":"Rook activity is often more important than grabbing an extra pawn. The rook can check the enemy king, attack from the side, or defend a pawn from a long distance.",
  "trap":"Moving behind a pawn is not automatically best. Check tactics on the rook and king, especially enemy checks and the rook's access to open files.",
  "decision":"Find the passed pawn, compare front/behind rook placements, and calculate the opponent's most forcing check.",
  "memory":"Active rooks and safe kings first; support passers from behind when the line works.",
  "questions":["What can the opponent check on the next move?","Can your rook get behind the passer without losing material?"]},
 "king-support":{
  "definition":"In king-and-pawn endings your king is an attacking piece. It can support a pawn's advance, block the defending king, and control critical squares.",
  "why":"A protected passed pawn can force the defender into zugzwang, but the attacking king must help it rather than simply pushing when the path is blocked.",
  "trap":"An impulsive pawn push can lose opposition or let the defender block directly in front of the pawn.",
  "decision":"Before moving, identify the square directly ahead of the pawn, who controls it, and which king can approach it legally.",
  "memory":"Bring the king to the key squares; don't push past your support.",
  "questions":["Who controls the square in front of the pawn?","Does moving the king or pawn preserve more useful choices?"]},
 "queen-mate":{
  "definition":"A queen attacks along ranks, files and diagonals. With your king controlling escape squares, you can confine the opponent king to the edge and deliver mate.",
  "why":"Checkmate means the king is in check and has no legal reply—not a check that merely looks decisive.",
  "trap":"A queen can accidentally give stalemate if the opposing king has no legal move but is not in check.",
  "decision":"For every checking candidate, count every king escape, capture of your queen, and possible interposition. Verify that no legal reply exists.",
  "memory":"No legal reply plus check equals checkmate; no legal reply without check is stalemate.",
  "questions":["Does the move give check?","Can the defending king move, capture the checking piece, or block?"]},
 "rook-checks":{
  "definition":"A rook controls an entire file and rank until blocked. Rook checks are forcing but do not automatically win.",
  "why":"A well-placed rook can cut off a king, coordinate with your king, or force the defending king away from a critical file.",
  "trap":"A series of pointless checks can allow the opposing king to improve its position or escape. Also watch for a rook left undefended.",
  "decision":"Calculate the opponent's legal replies after the check and identify which squares your rook will control afterward.",
  "memory":"Every check needs a purpose; calculate the reply.",
  "questions":["What are the opponent's legal replies to the check?","Where should your rook and king cooperate next?"]}
}

def distance(a,b):
 return chess.square_distance(a,b)

def geometry(board):
 turn=board.turn
 side="White" if turn else "Black"
 pieces=board.piece_map()
 my_king=board.king(turn);their_king=board.king(not turn)
 pawns=[]
 for sq,p in pieces.items():
  if p.piece_type!=chess.PAWN:continue
  opposing=[other for other,q in pieces.items() if q.piece_type==chess.PAWN and q.color!=p.color
   and abs(chess.square_file(other)-chess.square_file(sq))<=1
   and (chess.square_rank(other)>chess.square_rank(sq) if p.color else chess.square_rank(other)<chess.square_rank(sq))]
  remaining=(7-chess.square_rank(sq)) if p.color else chess.square_rank(sq)
  target=chess.square(chess.square_file(sq),7 if p.color else 0)
  pawns.append({"square":chess.square_name(sq),"side":"White" if p.color else "Black",
   "passed":not opposing,"movesToPromotionIgnoringOpposition":remaining,
   "defendingKingDistanceToPromotionSquare":distance(board.king(not p.color),target)})
 checks=[board.san(m) for m in board.legal_moves if board.gives_check(m)]
 captures=[board.san(m) for m in board.legal_moves if board.is_capture(m)]
 opposition=(
  (chess.square_file(my_king)==chess.square_file(their_king) and
   abs(chess.square_rank(my_king)-chess.square_rank(their_king))==2) or
  (chess.square_rank(my_king)==chess.square_rank(their_king) and
   abs(chess.square_file(my_king)-chess.square_file(their_king))==2))
 return {"side":side,"pieces":len(pieces),"myKing":chess.square_name(my_king),
  "theirKing":chess.square_name(their_king),"opposition":opposition,
  "pawns":pawns,"checks":checks[:12],"captures":captures[:12],
  "legalMoves":board.legal_moves.count(),
  "inCheck":board.is_check()}

def teach(lesson_id):
 original=base_lesson(lesson_id)
 board=chess.Board(original["fen"])
 kind=lesson_id.split("-variation-")[0].removesuffix("-mirror")
 topic=TOPICS[kind];metrics=geometry(board)
 pieces=metrics["pieces"];side=metrics["side"]
 observed=["It is "+side+"'s turn, with "+str(pieces)+" pieces on the board.",
   "Your king is on "+metrics["myKing"]+" and the defending king is on "+metrics["theirKing"]+".",
   "There are "+str(metrics["legalMoves"])+" legal choices for the side to move."]
 if metrics["opposition"]:
  observed.append("The kings are in direct opposition on the current board.")
 else:observed.append("The kings are not in direct opposition.")
 for p in metrics["pawns"]:
  observed.append(p["side"]+" pawn "+p["square"]+
    (" is passed" if p["passed"] else " is not passed")+
    ", "+str(p["movesToPromotionIgnoringOpposition"])+" rank(s) from promotion.")
 if metrics["checks"]:
  observed.append("Legal checking candidates on this board: "+", ".join(metrics["checks"][:5])+".")
 if metrics["captures"]:
  observed.append("Legal captures available now: "+", ".join(metrics["captures"][:5])+".")
 return {"id":original["id"],"title":original["title"],"color":side,
  "fen":original["fen"],"theme":kind,"intro":original["principle"],
  "sections":[
   {"title":"The underlying rule","detail":topic["definition"]},
   {"title":"Why strong players care","detail":topic["why"]},
   {"title":"Read this exact board","detail":" ".join(observed)},
   {"title":"What goes wrong","detail":topic["trap"]},
   {"title":"A thinking process to reuse","detail":topic["decision"]}
  ],"memory":topic["memory"],"questions":topic["questions"],
  "geometry":metrics,
  "note":"Statements about this board are computed from legal geometry; winning/drawing claims require exact tablebase verification, which may be unavailable."}
