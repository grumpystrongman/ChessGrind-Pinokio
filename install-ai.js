// Safe, repeatable repair for conversational AI and neural speech.
module.exports = {
 run:[{method:"shell.run",params:{
   path:".",venv:".venv",
   message:"python local_ai_setup.py install"
 }}]
};
