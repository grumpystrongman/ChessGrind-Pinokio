"""Local voice rendering reused from EmberWriter's optional Kokoro ONNX setup.

Voice assets remain on the user's machine, synthesis is loopback-only. Browser
speech synthesis is a no-install fallback; no remote voice API is involved.
"""
from __future__ import annotations
import io, os, re, threading, wave
from pathlib import Path
from arena_personas import KOKORO_VOICES
LOCAL=Path(os.environ.get("LOCALAPPDATA",str(Path.home()/"AppData"/"Local")))
NATIVE=LOCAL/"ChessGrind"/"models"/"kokoro"
SHARED=LOCAL/"EmberWriter"/"models"/"kokoro"
ROOT=Path(os.environ["CHESSGRIND_KOKORO_DIR"]) if os.environ.get("CHESSGRIND_KOKORO_DIR") else (
    SHARED if (SHARED/"kokoro-v1.0.onnx").exists() and (SHARED/"voices-v1.0.bin").exists() else NATIVE)
MODEL=ROOT/"kokoro-v1.0.onnx"
VOICES=ROOT/"voices-v1.0.bin"
_LOCK=threading.Lock()
_ENGINE=None

def status():
    assets=MODEL.is_file() and VOICES.is_file()
    try:
        import kokoro_onnx
        runtime=True
    except ImportError:
        runtime=False
    return {"available":bool(assets and runtime),"assetsPresent":assets,"runtimeInstalled":runtime,
       "engine":"Local Kokoro ONNX (EmberWriter-compatible)",
       "voices":list(KOKORO_VOICES),
       "fallback":"Browser speechSynthesis if local neural voice is unavailable.",
       "note":"Voice is synthesized locally, never sent to a hosted TTS service."}

def speak(message,voice="af_sarah",rate=1.0):
    global _ENGINE
    if not isinstance(message,str):raise ValueError("Text must be a string")
    text=" ".join(message.split())
    if not 1<=len(text)<=450:raise ValueError("Speech must be 1-450 characters")
    if not isinstance(voice,str) or voice not in KOKORO_VOICES:raise ValueError("Unknown voice")
    if isinstance(rate,bool) or not isinstance(rate,(int,float)) or not 0.7<=rate<=1.4:
        raise ValueError("Unsupported speaking speed")
    if not status()["available"]:raise ValueError("Local neural voices aren't installed. Use browser speech or install optional Kokoro runtime.")
    with _LOCK:
        if _ENGINE is None:
            from kokoro_onnx import Kokoro
            _ENGINE=Kokoro(str(MODEL),str(VOICES))
        language="en-gb" if voice.startswith(("bf_","bm_")) else "en-us"
        samples,frequency=_ENGINE.create(text,voice=voice,speed=float(rate),lang=language)
        if int(frequency)!=24000 or not 0<len(samples)<=24000*50:
            raise RuntimeError("Voice engine returned unexpected audio")
        import numpy as np
        pcm=(np.asarray(samples).clip(-1,1)*32767).astype("<i2").tobytes()
        output=io.BytesIO()
        with wave.open(output,"wb") as writer:
            writer.setnchannels(1);writer.setsampwidth(2);writer.setframerate(24000)
            writer.writeframes(pcm)
        return output.getvalue()

def install_assets():
    """Explicit opt-in installation; reuse existing EmberWriter assets if present."""
    if MODEL.is_file() and VOICES.is_file():
        print("Existing local Kokoro model and voices found at",ROOT,flush=True)
        return
    import urllib.request
    target=NATIVE
    target.mkdir(parents=True,exist_ok=True)
    base="https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.1/"
    for name,min_size,max_size in (("kokoro-v1.0.onnx",20_000_000,700_000_000),
                                   ("voices-v1.0.bin",100_000,100_000_000)):
        file=target/name
        if file.is_file() and min_size<=file.stat().st_size<=max_size:continue
        partial=target/(name+".part")
        print("Downloading optional local Kokoro asset",name,flush=True)
        try:
            req=urllib.request.Request(base+name,headers={"User-Agent":"ChessGrind-Pinokio/0.2"})
            with urllib.request.urlopen(req,timeout=180) as response,partial.open("wb") as stream:
                count=0
                while True:
                    chunk=response.read(1024*1024)
                    if not chunk:break
                    count+=len(chunk)
                    if count>max_size:raise ValueError("Voice model file exceeds expected size")
                    stream.write(chunk)
            if count<min_size:raise ValueError("Voice model download was truncated")
            partial.replace(file)
        finally:partial.unlink(missing_ok=True)
    print("Local Kokoro assets available in",target,flush=True)

if __name__=="__main__":
    import sys
    if sys.argv[1:]==["install-assets"]:install_assets()
    elif sys.argv[1:]==["status"]:print(status())
    else:raise SystemExit("Usage: coach_voice.py install-assets|status")
