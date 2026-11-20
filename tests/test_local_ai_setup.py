"""Mocked clean-install checks for ChessGrind's local AI + neural voices.

These tests MUST NOT download models, install software, or touch user data.
They simulate successful and interrupted Pinokio installs on CI.
"""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import local_ai_setup as s

class LocalAISetupTests(unittest.TestCase):
    def test_hardware_model_selection(self):
        self.assertEqual(s.choose_model(32),"qwen3.5:4b")
        self.assertEqual(s.choose_model(12),"qwen3.5:4b")
        self.assertEqual(s.choose_model(8),"qwen3.5:2b")
        self.assertEqual(s.choose_model(4),"qwen3.5:0.8b")
        self.assertEqual(s.choose_model(None),"qwen3.5:2b")

    def test_installed_models_discovered(self):
        with patch.object(s,"_json",return_value={"models":[{"name":"qwen3.5:2b"}]}):
            available=s.runtime_status()
        self.assertTrue(available["reachable"])
        self.assertEqual(available["selected"],"qwen3.5:2b")
        self.assertTrue(available["executableFound"] is True or available["executableFound"] is False)

    def test_missing_service_is_not_ready(self):
        with patch.object(s,"_json",side_effect=OSError("Not running")):
            state=s.runtime_status()
        self.assertFalse(state["reachable"])
        self.assertIsNone(state["selected"])

    def test_reuse_existing_install_no_model_download(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            with patch.object(s,"HOME",root),patch.object(s,"REPORT",root/"status.json"),\
                 patch.object(s,"executable",return_value="C:/Ollama/ollama.exe"),\
                 patch.object(s,"launch_server",return_value=True),\
                 patch.object(s,"runtime_status",return_value={"reachable":True,
                   "models":["qwen3.5:4b"],"selected":"qwen3.5:4b","executableFound":True}),\
                 patch.object(s,"probe_chat",return_value=True),\
                 patch.object(s,"pull_model") as pulled,\
                 patch.object(s,"install_voices",return_value=True),\
                 patch.object(s,"readiness",return_value={"conversationalAIReady":True,
                    "neuralVoicesReady":True}) :
                result=s.setup("all",strict=True)
                pulled.assert_not_called()
            self.assertTrue(result["success"])
            self.assertEqual(json.loads((root/"status.json").read_text())["steps"]["conversationalAI"]["model"],"qwen3.5:4b")

    def test_first_install_pulls_appropriate_model(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            with patch.object(s,"HOME",root),patch.object(s,"REPORT",root/"status.json"),\
                 patch.object(s,"executable",return_value=None),\
                 patch.object(s,"_signed_windows_install") as installer,\
                 patch.object(s,"launch_server",return_value=True),\
                 patch.object(s,"runtime_status",return_value={"reachable":True,
                   "models":[],"selected":None,"executableFound":True}),\
                 patch.object(s,"hardware",return_value={"ramGiB":8,"freeInstallDiskGiB":12}),\
                 patch.object(s,"pull_model") as pulled,\
                 patch.object(s,"probe_chat",return_value=True),\
                 patch.object(s,"readiness",return_value={"conversationalAIReady":True,
                   "neuralVoicesReady":False}):
                result=s.setup("ai",strict=True)
                installer.assert_called_once()
                pulled.assert_called_once_with("qwen3.5:2b")
            self.assertTrue(result["success"])

    def test_failed_download_keeps_chess_playable_and_reports(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            with patch.object(s,"HOME",root),patch.object(s,"REPORT",root/"status.json"),\
                 patch.object(s,"executable",return_value=None),\
                 patch.object(s,"_signed_windows_install",side_effect=RuntimeError("network down")) ,\
                 patch.object(s,"install_voices",return_value=True),\
                 patch.object(s,"readiness",return_value={"conversationalAIReady":False,
                   "neuralVoicesReady":True}):
                result=s.setup("all",strict=False)
            self.assertFalse(result["success"])
            self.assertFalse(result["steps"]["conversationalAI"]["ready"])
            self.assertTrue(result["steps"]["neuralVoices"]["ready"])
            self.assertTrue((root/"status.json").exists())

    def test_installation_is_loopback_only_and_signed(self):
        self.assertEqual(s.CHAT,"http://127.0.0.1:11434/api/chat")
        self.assertEqual(s.TAGS,"http://127.0.0.1:11434/api/tags")
        self.assertTrue(s.INSTALLER.startswith("https://ollama.com/"))
        import inspect
        source=inspect.getsource(s._signed_windows_install)
        self.assertIn("Get-AuthenticodeSignature",source)
        self.assertIn("Ollama Inc",source)

if __name__=="__main__":
    unittest.main()
