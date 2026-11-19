module.exports = {
 run:[{method:"shell.run",params:{
   path:".",venv:".venv",
   message:["python -m pip install --upgrade pip",
            "python -m pip install -r requirements.txt",
            "python pinokio/bootstrap.py setup"]
 }}]
};

