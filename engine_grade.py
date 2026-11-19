"""Mate-aware comparisons of two Stockfish evaluations from the same mover.

Ordinary centipawn differences alone can treat missing mate in one as an
'equal move': Mate(1) vs Mate(6) differs by only 5 units when using the
conventional mate_score=20000 conversion. Convert forced-mate distance
regressions into a meaningful decision error while retaining centipawn
comparisons for non-mating positions. Search-depth uncertainty remains.
"""
def engine_gap(best_pov,played_pov):
 best=best_pov.mate()
 chosen=played_pov.mate()
 if best is not None and best>0:
  if chosen is None or chosen<=0:return 1000
  return 0 if chosen<=best else max(100,110*(chosen-best))
 if best is not None and best<0:
  if chosen is not None and chosen<0:
   return 0 if chosen<=best else max(100,110*(chosen-best))
  # A selected move that avoids the mating sequence should not be
  # penalized, though Stockfish ideally would prefer that move itself.
  if chosen is None:return 0
 if best is None and chosen is not None and chosen<0:return 1000
 a=best_pov.score(mate_score=20000)
 b=played_pov.score(mate_score=20000)
 if a is None or b is None:return 0
 return max(0,a-b)
