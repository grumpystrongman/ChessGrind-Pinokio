module.exports = {
 daemon:true,
 run:[{method:"shell.run",params:{
   path:"..",venv:".venv",
   message:"python pinokio/bootstrap.py launch --port {{port}}",
   on:[{event:"/(http:\\/\\/127\\.0\\.0\\.1:[0-9]+)/",done:true}]
 }},{method:"local.set",params:{url:"{{input.event[1]}}"}}]
};
