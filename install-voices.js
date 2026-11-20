// Neural voices are normally installed during the core Pinokio setup.
module.exports = {
 run:[{method:"shell.run",params:{
   path:".",venv:".venv",
   message:"python local_ai_setup.py voices"
 }}]
};
