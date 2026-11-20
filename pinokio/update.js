module.exports = {
 run:[{method:"shell.run",params:{
   path:"..",
   message:"powershell -NoProfile -ExecutionPolicy Bypass -File sync-pinokio.ps1 -PinokioFolder ."
 }}]
};
