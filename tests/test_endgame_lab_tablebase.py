"""Live endgame grading in a disposable local SQLite database.

Requires Stockfish and a complete compact Syzygy collection.
"""
import os
import tempfile
import unittest
from pathlib import Path
import chess
from verified_chess import syzygy_result, tablebase_status
from game_analysis import find_engine

class LabTests(unittest.TestCase):
    @unittest.skipUnless(tablebase_status()["threeFourComplete"] and find_engine(),
                         "Needs Stockfish and all 35 compact tablebase pairs")
    def test_queen_endgame_grades_with_exact_wnl(self):
        # Must set CHESS_GRIND_HOME *before* importing the DB-backed lab.
        from endgame_lab import BY_ID, play
        fen=BY_ID["queen-mate"]["fen"]
        outcome=syzygy_result(chess.Board(fen))
        self.assertIsNotNone(outcome)
        candidate=outcome["bestMoves"][0]["uci"]
        result=play("queen-mate",candidate)
        self.assertTrue(result["tablebaseVerified"])
        self.assertTrue(result["correct"])
        self.assertIsNotNone(result["exactBestMoves"])
        self.assertIn(result["bestSan"],result["exactBestMoves"])
        self.assertEqual(result["bestLine"]["steps"][1]["san"],result["bestSan"])
        self.assertEqual(result["yourLine"]["steps"][1]["san"],result["yourSan"])
        self.assertIn("Syzygy",result["limit"])

if __name__=="__main__":
    # Don't overwrite an existing player's CHESS_GRIND_HOME.
    # For isolated tests the CI job sets it to a disposable temp dir.
    unittest.main()
