"""Fast structural tests for the expanded chess evidence benchmark."""
import unittest
from chess_accuracy_suite import cases
import chess

class EvidenceSuiteTests(unittest.TestCase):
    def test_test_positions_unique_and_valid(self):
        positions=cases(24,3)
        self.assertGreaterEqual(len(positions),45)
        seen=set()
        for _,ident,fen in positions:
            board=chess.Board(fen)
            self.assertTrue(board.is_valid(),ident)
            key=board.epd()
            self.assertNotIn(key,seen,"duplicate evaluation case")
            seen.add(key)
    def test_source_distribution(self):
        positions=cases(24,3)
        self.assertEqual(sum(p[0]=="curated" for p in positions),6)
        self.assertEqual(sum(p[0]=="academy" for p in positions),18)
        self.assertGreaterEqual(sum(p[0]=="exact-endgame" for p in positions),20)

if __name__=="__main__":unittest.main()
