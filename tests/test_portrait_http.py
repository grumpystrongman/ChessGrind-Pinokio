"""Exercise the real ChessGrind local HTTP portrait handler in a fresh checkout."""
import hashlib
import threading
import unittest
import urllib.request
from http.server import ThreadingHTTPServer

from web_app import Handler
from test_portrait_packaging import BOTS,COACHES

class PortraitServerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.http=ThreadingHTTPServer(("127.0.0.1",0),Handler)
        cls.server_thread=threading.Thread(target=cls.http.serve_forever,daemon=True)
        cls.server_thread.start()
        cls.base="http://127.0.0.1:"+str(cls.http.server_address[1])

    @classmethod
    def tearDownClass(cls):
        cls.http.shutdown()
        cls.http.server_close()
        cls.server_thread.join(timeout=3)

    def test_http_returns_all_unique_webp_portraits(self):
        fingerprints=set()
        for name in BOTS+COACHES:
            with self.subTest(name=name):
                with urllib.request.urlopen(self.base+"/icons/portraits/"+name+".webp",timeout=6) as r:
                    self.assertEqual(r.status,200)
                    self.assertTrue(r.headers["Content-Type"].startswith("image/webp"))
                    binary=r.read()
                self.assertEqual(binary[:4],b"RIFF")
                self.assertEqual(binary[8:12],b"WEBP")
                signature=hashlib.sha256(binary).hexdigest()
                self.assertNotIn(signature,fingerprints,"Repeated artwork for "+name)
                fingerprints.add(signature)
        self.assertEqual(len(fingerprints),27)

if __name__=="__main__":
    unittest.main()
