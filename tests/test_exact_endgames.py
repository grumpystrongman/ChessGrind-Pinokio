"""Source-level and real tablebase integrity checks for the compact local set."""
import os
import tempfile
import unittest
from pathlib import Path
import chess
from verified_chess import tablebase_status, syzygy_result

class ExactTablebaseTests(unittest.TestCase):
    @unittest.skipUnless(tablebase_status()["installed"],"Local Syzygy files not installed")
    def test_queen_wins_and_best_moves_are_legal(self):
        board=chess.Board("7k/8/8/8/8/8/4K3/4Q3 w - - 0 1")
        result=syzygy_result(board)
        self.assertIsNotNone(result)
        self.assertTrue(result["exact"])
        self.assertEqual(result["wdl"],2)
        self.assertGreater(len(result["moveDetails"]),4)
        for entry in result["moveDetails"]:
            candidate=chess.Move.from_uci(entry["uci"])
            self.assertIn(candidate,board.legal_moves)
            self.assertEqual(board.san(candidate),entry["san"])

    @unittest.skipUnless(tablebase_status()["installed"],"Local Syzygy files not installed")
    def test_rook_wins(self):
        board=chess.Board("7k/8/8/8/8/8/4K3/4R3 w - - 0 1")
        result=syzygy_result(board)
        self.assertIsNotNone(result)
        self.assertEqual(result["wdl"],2)
        self.assertIsInstance(result["dtz"],int)

    @unittest.skipUnless(tablebase_status()["installed"],"Local Syzygy files not installed")
    def test_pawn_endgame_exact_result(self):
        board=chess.Board("7k/8/8/8/8/8/4KP2/8 w - - 0 1")
        result=syzygy_result(board)
        self.assertIsNotNone(result)
        self.assertEqual(result["wdl"],2)

    def test_no_castling_positions_misreported(self):
        board=chess.Board()
        self.assertIsNone(syzygy_result(board))
        
    def test_missing_directory_has_no_false_claims(self):
        old=os.environ.get("CHESSGRIND_SYZYGY_DIR")
        with tempfile.TemporaryDirectory() as tmp:
            os.environ["CHESSGRIND_SYZYGY_DIR"]=str(Path(tmp)/"missing")
            try:
                self.assertFalse(tablebase_status()["installed"])
                self.assertIsNone(syzygy_result(chess.Board("7k/8/8/8/8/8/4K3/4Q3 w - - 0 1")))
            finally:
                if old is None:os.environ.pop("CHESSGRIND_SYZYGY_DIR",None)
                else:os.environ["CHESSGRIND_SYZYGY_DIR"]=old

if __name__=="__main__":unittest.main()
