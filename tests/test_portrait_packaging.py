"""Artwork packaging regression: every character must have a unique bundled portrait."""
from pathlib import Path
import hashlib
import unittest

ROOT=Path(__file__).resolve().parents[1]
BOTS=("milo","pip","nora","theo","iris","remy","ada","basil","sasha",
      "felix","kira","omar","lena","dante","vera","rook","elise",
      "kenji","maeve","atlas","oracle","max")
COACHES=("coach-mentor","coach-tactics","coach-iris","coach-rook","coach-vera")

class CharacterPortraitTests(unittest.TestCase):
    def test_all_27_webp_files_are_unique(self):
        files=[ROOT/"icons"/"bots"/(name+".webp") for name in BOTS]
        files += [ROOT/"icons"/"coaches"/(name+".webp") for name in COACHES]
        self.assertEqual(len(files),27)
        hashes={}
        for file in files:
            self.assertTrue(file.is_file(),f"Portrait not shipped: {file}")
            data=file.read_bytes()
            self.assertGreater(len(data),5000,file.name)
            self.assertEqual(data[:4],b"RIFF",file.name)
            self.assertEqual(data[8:12],b"WEBP",file.name)
            hash=hashlib.sha256(data).hexdigest()
            self.assertNotIn(hash,hashes,f"Duplicate image: {file.name} and {hashes.get(hash)}")
            hashes[hash]=file.name

    def test_dashboard_and_game_references_use_bundled_assets(self):
        files={name:(ROOT/name).read_text("utf8")
               for name in ("dashboard.html","arena_personas_ui.js",
                            "arena_personas.py","arena.html","web_app.py")}
        self.assertIn('coachImage(coach)',files["dashboard.html"])
        self.assertNotIn('pictures[i%5]',files["dashboard.html"])
        self.assertIn('"/icons/portraits/"+c.id+".webp"',files["dashboard.html"])
        self.assertIn('return "/icons/portraits/"+identity+".webp"',files["arena_personas_ui.js"])
        self.assertIn('avatar=f"/icons/portraits/{slug}.webp"',files["arena_personas.py"])
        self.assertIn('g.coachOpponent.id+".webp"',files["arena.html"])
        self.assertIn('mime="image/webp"',files["web_app.py"])
if __name__=="__main__":unittest.main()
