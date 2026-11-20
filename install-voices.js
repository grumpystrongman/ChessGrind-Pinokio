// Optional neural voices (not part of core chess installation).
module.exports = {
  run:[{method:"shell.run",params:{
    path:".",venv:".venv",
    message:["python -m pip install kokoro-onnx==0.6.1",
             "python coach_voice.py install-assets"]
  }}]
};
