module.exports = {
 run:[{method:"shell.run",params:{path:".",message:"git pull --ff-only"}},
      {method:"shell.run",params:{path:".",venv:".venv",
       message:["python -m pip install -r requirements.txt","python pinokio/bootstrap.py setup"]}}]
};

