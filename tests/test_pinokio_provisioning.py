"""Verify that a clean Pinokio install actually reaches AI and voice setup."""
import ast
from pathlib import Path
import unittest

ROOT=Path(__file__).resolve().parents[1]

class PinokioProvisioningTests(unittest.TestCase):
    def test_bootstrap_invokes_complete_setup(self):
        source=(ROOT/"pinokio"/"bootstrap.py").read_text(encoding="utf-8-sig")
        tree=ast.parse(source)
        self.assertIn('setup_local_ai("all")',source)
        self.assertIn('from local_ai_setup import setup as setup_local_ai',source)
        self.assertIn("Neural character voices:",source)
        self.assertIn("Conversational AI:",source)
        self.assertIn("launch_server()",source)
        self.assertTrue(any(isinstance(x,ast.FunctionDef) and x.name=="main" for x in tree.body))

    def test_pinokio_install_and_update_hooks(self):
        root=(ROOT/"install.js").read_text(encoding="utf-8-sig")
        nested=(ROOT/"pinokio"/"install.js").read_text(encoding="utf-8-sig")
        updater=(ROOT/"sync-pinokio.ps1").read_text(encoding="utf-8-sig")
        for source in (root,nested):
            self.assertIn("pinokio/bootstrap.py setup",source)
        self.assertIn('local_ai_setup.py","install',updater)

    def test_both_menus_expose_repair(self):
        for relative in ("pinokio.js","pinokio/pinokio.js"):
            content=(ROOT/relative).read_text(encoding="utf-8-sig")
            self.assertIn("install-ai.js",content)
            self.assertIn("install-voices.js",content)

    def test_local_status_and_help_are_in_app(self):
        backend=(ROOT/"web_app.py").read_text(encoding="utf-8-sig")
        frontend=(ROOT/"dashboard.html").read_text(encoding="utf-8-sig")
        self.assertIn('"/api/chess/setup/status"',backend)
        self.assertIn('id="local-ai-health"',frontend)
        self.assertIn("Repair local AI & character voices",frontend)

if __name__=="__main__": unittest.main()
