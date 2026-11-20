# Full-Experience Pinokio Installation (Windows)

ChessGrind now provisions its **local conversational model and character voices as part of the standard Install ChessGrind flow**. New users are not expected to know what Ollama or Kokoro means, obtain API keys, or manually configure a Python environment.

## First installation

Selecting **Install ChessGrind** runs `install.js` (or `pinokio/install.js` in the nested layout), which installs Python dependencies and calls `pinokio/bootstrap.py setup`.

The setup then:

1. Downloads and validates Stockfish 19 and seeds the starter training/game data.
2. Installs the small 3-4-piece Syzygy tablebases and builds the SQLite chess knowledge graph and local semantic embeddings (when available).
3. Reuses an existing working local Ollama server/model if present; otherwise downloads the **official Windows OllamaSetup.exe**, checks its Windows Authenticode certificate against **Ollama Inc.**, and installs it silently per user.
4. Starts Ollama locally on `127.0.0.1:11434` when required. Selects an existing supported model, or chooses and downloads a local Qwen3.5 model according to system memory:
   - 12 GB+ system RAM: **qwen3.5:4b**, approximately 3.3–4.0 GB.
   - 8–11 GB system RAM: **qwen3.5:2b**, approximately 2.7–3.1 GB.
   - Below 8 GB: **qwen3.5:0.8b**, approximately 1.2–1.3 GB. This option is less sophisticated and slower hardware may result in reduced conversational quality.
5. Asks the local model an actual test question to verify that Ollama can generate a reply—not merely that a model file exists.
6. Installs the `kokoro-onnx==0.6.1` Python runtime and the official Kokoro ONNX model/voice assets. Existing EmberWriter voice assets are reused when compatible.
7. Synthesizes a short WAV speech sample to confirm that neural voice output actually works.
8. Writes a status/diagnostic record to `userdata/local_ai_setup.json`. The standard **Check installation** action reports Ollama/model and voice readiness.

**No hosted text or voice generation service is required**. Chess replies still come from Stockfish; the language model determines how each character explains those replies.

## Installation requirements and resilience

- **Windows x64 and Pinokio Python support** are required for the current release.
- An internet connection is necessary for the one-time download of Ollama, a model, Kokoro voice assets, Stockfish and some training data.
- First-time downloads may be **several gigabytes**. The chosen model is based on total RAM; a machine's free storage is checked before downloading.
- The installer does **not** overwrite existing Ollama models, remove or delete personal games, or replace compatible EmberWriter voice files.
- If installation fails because of network interruptions, low disk space, incompatible runtime, or permission restrictions, chess remains playable. In that case the app explicitly reports **setup incomplete**; characters use authored dialogue and/or browser speech as fallbacks. The Pinokio **Repair local AI & character voices** menu action retries only the missing components.
- The app checks for and starts an existing Ollama executable on launch to avoid a working model becoming unavailable after reboot.
- The home dashboard shows an incomplete-capabilities message when conversational AI or neural voices are not detected.

## Pinokio menu actions

**Install ChessGrind**: includes chess, Ollama conversational setup, and neural character voices.

**Start ChessGrind**: starts the local game and attempts to launch an installed Ollama service.

**Check installation**: prints whether Stockfish, tablebases, conversational AI, and neural voices are present.

**Repair local AI & character voices**: retries both model and Kokoro installation without reinstalling the whole game.

**Repair neural voices only**: only installs or repairs the Kokoro ONNX voice capability.

**Update application**: preserves an online SQLite backup and local Git changes, fetches the latest release, and rechecks AI/voice setup after updating.

## Testing

The repository includes `tests/test_local_ai_setup.py` and `tests/test_pinokio_provisioning.py` to simulate a fresh install, reusing an existing model, low-memory model selection, and handling a failed network download without modifying a machine's software. Windows CI also compiles the installer code and checks both Pinokio menu variants.

**Validation limitation:** CI does not silently install a multi-gigabyte Ollama model and neural-voice assets on every push. Full network downloads, Windows Authenticode checks, real LLM inference, actual audio synthesis, and the graphical Pinokio first-install UX require a dedicated clean Windows installation acceptance test. A successful mocked test is not proof that all third-party downloads will work on every user's hardware.

### Troubleshooting

Use **Check installation**, followed by **Repair local AI & character voices** if either capability is unavailable. A voice installation can be tested independently with `python local_ai_setup.py voices`, and a local health report with `python local_ai_setup.py check`. The setup saves failures under `userdata/local_ai_setup.json` without storing chess conversation text.
