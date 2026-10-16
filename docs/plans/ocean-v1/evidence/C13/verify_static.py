"""Record C13 generated contracts and affected v1 browser gates."""
import json
from pathlib import Path
import subprocess
import sys

out=Path(__file__).resolve().parent
root=out.parents[4]
checks=[(name,[sys.executable,"scripts/"+script,"--check"],root) for name,script in [
("scope","export_chat_scope.py"),("schema","export_context_catalogue.py"),
("types","export_catalogue_types.py"),("examples","export_catalogue_examples.py"),
("snapshots","export_catalogue_snapshot.py"),("adapters","export_catalogue_adapter.py"),
("sst","export_sst_catalogue.py"),("edna","export_edna_catalogue.py"),("scientific","export_scientific_catalogue.py")]]
results=[]
for name,command,cwd in checks:
    with (out/(name+".txt")).open("w") as log:
        r=subprocess.run(command,cwd=cwd,stdout=log,stderr=subprocess.STDOUT)
    results.append({"name":name,"command":command,"cwd":str(cwd.relative_to(root)) or ".","exit_code":r.returncode})
    if r.returncode: break
(out/"static-results.json").write_text(json.dumps(results,indent=2)+"\n")
print(json.dumps(results))
sys.exit(results[-1]["exit_code"])
