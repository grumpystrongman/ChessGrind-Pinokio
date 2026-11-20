"""Install and verify ChessGrind's complete LOCAL conversational AI and voices.

Run by the Pinokio setup, and again by its Repair AI & Voices menu.
Existing Ollama installations/models and EmberWriter voices are reused.
No cloud keys, remote inference, GPU requirement, or global model deletion.
"""
from __future__ import annotations
import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

ROOT=Path(__file__).resolve().parent
HOME=ROOT/"userdata"
REPORT=HOME/"local_ai_setup.json"
TAGS="http://127.0.0.1:11434/api/tags"
CHAT="http://127.0.0.1:11434/api/chat"
INSTALLER="https://ollama.com/download/OllamaSetup.exe"
MODEL_SIZES={"qwen3.5:0.8b":1.3,"qwen3.5:2b":3.1,"qwen3.5:4b":4.0}
SUPPORTED=("ornith:9b","qwen3.5:9b","qwen3.5:4b","qwen3.5:2b",
           "qwen3.5:0.8b","llama3.2:3b")
CREATE_NO_WINDOW=getattr(subprocess,"CREATE_NO_WINDOW",0)

def _json(url,post=None,timeout=4):
    data=None if post is None else json.dumps(post).encode("utf-8")
    request=urllib.request.Request(url,data=data,headers={"Content-Type":"application/json"})
    with urllib.request.urlopen(request,timeout=timeout) as result:
        return json.load(result)

def executable():
    found=shutil.which("ollama")
    if found:return str(found)
    if sys.platform=="win32":
        for root in (os.getenv("LOCALAPPDATA",""),os.getenv("PROGRAMFILES","")):
            if root:
                for candidate in (Path(root)/"Programs"/"Ollama"/"ollama.exe",
                                  Path(root)/"Ollama"/"ollama.exe"):
                    if candidate.is_file():return str(candidate)
    return None

def runtime_status():
    try:
        response=_json(TAGS,timeout=2)
        names=[entry["name"] for entry in response.get("models",[])
               if isinstance(entry,dict) and isinstance(entry.get("name"),str)]
        return {"reachable":True,"models":names,
                "selected":next((x for x in SUPPORTED if x in names),None),
                "executableFound":bool(executable())}
    except (OSError,ValueError,KeyError):
        return {"reachable":False,"models":[],"selected":None,
                "executableFound":bool(executable())}

def hardware():
    available_gib=shutil.disk_usage(HOME if HOME.exists() else ROOT).free/(1024**3)
    ram=None
    if sys.platform=="win32":
        try:
            import ctypes
            class Memory(ctypes.Structure):
                _fields_=[("length",ctypes.c_ulong),("memoryLoad",ctypes.c_ulong),
                          ("totalPhys",ctypes.c_ulonglong),("availPhys",ctypes.c_ulonglong),
                          ("totalPage",ctypes.c_ulonglong),("availPage",ctypes.c_ulonglong),
                          ("totalVirtual",ctypes.c_ulonglong),("availVirtual",ctypes.c_ulonglong),
                          ("availExtendedVirtual",ctypes.c_ulonglong)]
            stats=Memory()
            stats.length=ctypes.sizeof(Memory)
            if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stats)):
                ram=round(stats.totalPhys/(1024**3),1)
        except (AttributeError,OSError):pass
    return {"ramGiB":ram,"freeInstallDiskGiB":round(available_gib,1)}

def choose_model(ram_gib):
    # Advanced explicit override (used for reproducible low-memory CI checks).
    # An unknown value is ignored rather than passed to an arbitrary model pull.
    override=os.getenv("CHESSGRIND_INSTALL_MODEL")
    if override in MODEL_SIZES:return override
    if ram_gib is None:return "qwen3.5:2b"
    if ram_gib>=12:return "qwen3.5:4b"
    if ram_gib>=8:return "qwen3.5:2b"
    return "qwen3.5:0.8b"

def launch_server():
    if runtime_status()["reachable"]:return True
    exe=executable()
    if not exe:return False
    # Do not kill, replace, or reconfigure a pre-existing Ollama process.
    subprocess.Popen([exe,"serve"],stdin=subprocess.DEVNULL,
                     stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,
                     creationflags=CREATE_NO_WINDOW,close_fds=True)
    for _ in range(40):
        if runtime_status()["reachable"]:return True
        time.sleep(.5)
    return False

def _signed_windows_install():
    if sys.platform!="win32":
        raise RuntimeError("Ollama automatic installation is available only on Windows.")
    if executable():return
    # The signed official Windows installer contains sizeable runtime assets.
    # Check both the installation drive and Windows' TEMP drive (which may
    # differ when Pinokio itself is installed on D:).
    install_free=hardware()["freeInstallDiskGiB"]
    temp_free=shutil.disk_usage(Path(tempfile.gettempdir())).free/(1024**3)
    if install_free<7 or temp_free<9:
        raise RuntimeError(
            "Ollama setup needs at least 7 GiB on the application drive and "
            "9 GiB free on the Windows temporary drive. "
            "Currently available: "+str(round(install_free,1))+" / "+
            str(round(temp_free,1))+" GiB.")
    print("Downloading the official Windows Ollama installer...",flush=True)
    with tempfile.TemporaryDirectory(prefix="ChessGrind-Ollama-") as folder:
        destination=Path(folder)/"OllamaSetup.exe"
        request=urllib.request.Request(INSTALLER,
                        headers={"User-Agent":"ChessGrind-Pinokio/1.0"})
        # Ollama's Windows release can exceed 1.5 GB; this bounded limit
        # still prevents accepting a runaway or unexpected payload.
        maximum=5_000_000_000
        size=0
        with urllib.request.urlopen(request,timeout=120) as response,destination.open("wb") as out:
            announced=int(response.headers.get("Content-Length") or 0)
            if announced>maximum:
                raise RuntimeError("Ollama installer exceeds the 5 GB safety limit")
            if announced:
                print("Official installer size:",round(announced/(1024**3),2),"GiB",flush=True)
            while True:
                chunk=response.read(1024*1024)
                if not chunk:break
                size+=len(chunk)
                if size>maximum:
                    raise RuntimeError("Ollama installer exceeds the 5 GB safety limit")
                out.write(chunk)
        if size<2_000_000:raise RuntimeError("Downloaded Ollama installer is unexpectedly small")
        # Verify the Authenticode signature AND certificate publisher as
        # recommended by Ollama's own Windows installation script.
        # Use -File with an explicit PowerShell param: Windows PowerShell
        # -Command does not reliably pass a trailing path via $args.
        verifier=Path(folder)/"verify-signature.ps1"
        verifier.write_text(
            "param([Parameter(Mandatory=$true)][string]$InstallerPath)\n"
            "$sig=Get-AuthenticodeSignature -LiteralPath $InstallerPath\n"
            "Write-Output ('Authenticode: '+$sig.Status+'; Publisher: '+$sig.SignerCertificate.Subject)\n"
            "if($sig.Status -ne 'Valid'){exit 11}\n"
            "if($sig.SignerCertificate.Subject -notmatch '(^|, )O=Ollama Inc\\.(,|$)'){exit 12}\n",
            encoding="utf-8")
        signed=subprocess.run(["powershell.exe","-NoProfile",
                               "-ExecutionPolicy","Bypass","-File",
                               str(verifier),str(destination)],
                 capture_output=True,text=True,timeout=35,creationflags=CREATE_NO_WINDOW)
        if signed.returncode:
            # Signature check remains fail-closed; expose only the public
            # vendor certificate details so package changes can be diagnosed.
            detail=(signed.stdout+" "+signed.stderr).strip()[:400]
            raise RuntimeError("Ollama Authenticode/publisher verification failed ("+
                               str(signed.returncode)+"): "+detail)
        print("Verified Ollama Inc. signature; installing per-user Ollama...",flush=True)
        installed=subprocess.run([str(destination),
                "/VERYSILENT","/NORESTART","/SUPPRESSMSGBOXES"],
                timeout=360,creationflags=CREATE_NO_WINDOW)
        if installed.returncode:
            raise RuntimeError("Ollama installation failed with code "+str(installed.returncode))
    if not executable():
        raise RuntimeError("Ollama installed, but its executable could not be found.")

def pull_model(model):
    if model not in MODEL_SIZES:
        raise ValueError("Unrecognized automatic chess model")
    if model in runtime_status()["models"]:return "already-present"
    available=hardware()["freeInstallDiskGiB"]
    required=MODEL_SIZES[model]+2
    if available<required:
        raise RuntimeError("Insufficient disk space for "+model+
                           " (needs about "+str(required)+" GiB free)")
    exe=executable()
    if not exe:raise RuntimeError("Ollama CLI is missing")
    print("Downloading local "+model+" (~"+str(MODEL_SIZES[model])+
          " GB), one time only...",flush=True)
    result=subprocess.run([exe,"pull",model],timeout=2400,
                  creationflags=CREATE_NO_WINDOW)
    if result.returncode:raise RuntimeError("Ollama model download failed")
    if model not in runtime_status()["models"]:
        raise RuntimeError("Ollama did not register the downloaded model")
    return "installed"

def probe_chat(model):
    if model not in runtime_status()["models"]:return False
    try:
        result=_json(CHAT,{
            "model":model,"stream":False,"think":False,
            "messages":[{"role":"system","content":"Speak one complete sentence as a friendly chess coach."},
                        {"role":"user","content":"Say you are ready to play chess."}],
            "options":{"num_predict":55,"num_ctx":1024},
            "keep_alive":"5m"},timeout=150)
        answer=str(result.get("message",{}).get("content","")).strip()
        return len(answer)>=8
    except (OSError,ValueError,KeyError):return False

def install_voices():
    from coach_voice import status,install_assets
    if not status()["runtimeInstalled"]:
        print("Installing local neural voice runtime...",flush=True)
        subprocess.run([sys.executable,"-m","pip","install","kokoro-onnx==0.6.1"],
                        check=True,timeout=900)
    install_assets()
    # Only a genuine WAV confirms the assets and ONNX runtime actually work.
    from coach_voice import speak,status
    if not status()["available"]:
        raise RuntimeError("Voice assets are present but neural speech is not operational")
    sample=speak("Ready for chess.",voice="af_sarah",rate=1.0)
    if not sample.startswith(b"RIFF") or len(sample)<1000:
        raise RuntimeError("Kokoro returned invalid speech audio")
    return True

def readiness(test_voice=False,test_chat=False):
    status=runtime_status()
    voice={}
    try:
        from coach_voice import status as voice_status
        voice=voice_status()
    except (ImportError,ValueError,OSError) as e:voice={"available":False,"error":str(e)}
    summary={
        "ollamaReachable":status["reachable"],
        "localModels":status["models"],
        "selectedChatModel":status["selected"],
        "conversationalAIReady":bool(status["selected"]),
        "neuralVoicesReady":bool(voice.get("available")),
        "voiceProvider":voice.get("engine"),
        "browserVoiceFallback":True,
        "system":hardware(),
        "note":"Model inference and neural speech remain local to this computer."}
    if test_chat and status["selected"]:
        summary["chatGeneratedSuccessfully"]=probe_chat(status["selected"])
        summary["conversationalAIReady"]=summary["chatGeneratedSuccessfully"]
    if test_voice and voice.get("available"):
        try:
            from coach_voice import speak
            output=speak("Ready.",voice="af_sarah",rate=1.0)
            summary["speechGeneratedSuccessfully"]=output.startswith(b"RIFF") and len(output)>1000
        except (OSError,RuntimeError,ValueError) as e:
            summary["speechGeneratedSuccessfully"]=False
            summary["voiceTestError"]=str(e)[:150]
        summary["neuralVoicesReady"]=summary["speechGeneratedSuccessfully"]
    return summary

def setup(only="all",strict=False):
    HOME.mkdir(parents=True,exist_ok=True)
    summary={"schema":1,"steps":{},"success":False}
    try:
        if only in ("all","ai"):
            try:
                if not executable():_signed_windows_install()
                if not launch_server():raise RuntimeError("Local Ollama service failed to start")
                installed=runtime_status()["selected"]
                preferred=installed or choose_model(hardware()["ramGiB"])
                if not installed:pull_model(preferred)
                if not probe_chat(preferred):
                    raise RuntimeError("Local model was installed but did not answer a test question")
                summary["steps"]["conversationalAI"]={"ready":True,"model":preferred}
            except (OSError,ValueError,RuntimeError,subprocess.SubprocessError) as exc:
                summary["steps"]["conversationalAI"]={"ready":False,"error":str(exc)[:300]}
                print("Conversational AI installation warning: "+str(exc),flush=True)
                if strict:raise
        if only in ("all","voices"):
            try:
                install_voices()
                summary["steps"]["neuralVoices"]={"ready":True}
            except (OSError,ValueError,RuntimeError,subprocess.SubprocessError) as exc:
                summary["steps"]["neuralVoices"]={"ready":False,"error":str(exc)[:300]}
                print("Neural voice installation warning: "+str(exc),flush=True)
                if strict:raise
    finally:
        summary["readiness"]=readiness()
        summary["success"]=all(x["ready"] for x in summary["steps"].values())
        REPORT.write_text(json.dumps(summary,indent=2),encoding="utf8")
    print("Local conversational AI:",summary["readiness"]["conversationalAIReady"],flush=True)
    print("Local neural voices:",summary["readiness"]["neuralVoicesReady"],flush=True)
    if not summary["success"]:
        print("Chess remains playable. Run the Pinokio Repair AI & Voices action to retry.",flush=True)
    return summary

if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("action",choices=("install","status","ai","voices","check"))
    parser.add_argument("--strict",action="store_true")
    args=parser.parse_args()
    if args.action=="status":output=readiness()
    elif args.action=="check":output=readiness(test_voice=True,test_chat=True)
    else:output=setup("all" if args.action=="install" else args.action,args.strict)
    print(json.dumps(output,indent=2))
    if args.strict and (not output.get("success",True)
                        if args.action not in ("status","check")
                        else not(output["conversationalAIReady"] and output["neuralVoicesReady"])):
        raise SystemExit(1)
