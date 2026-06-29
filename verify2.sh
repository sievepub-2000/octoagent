cd /home/sieve-pub/public-workspace/octoagent
echo "=== publishing_workflow_tools.py ==="
grep -n "def _json\|from src.utils" backend/src/tools/builtins/publishing_workflow_tools.py
echo "=== workflow_runtime_tools.py ==="
grep -n "def _json\|from src.utils" backend/src/tools/builtins/workflow_runtime_tools.py
echo "=== _json defs remaining ==="
grep -rln "^def _json" backend/src/tools/builtins/
echo "=== service.py providers.yaml ==="
grep -n "providers.yaml" backend/src/governance/model_auth/service.py
echo "=== serialization import check ==="
grep -rn "from src.utils.serialization" backend/src/tools/builtins/ | wc -l
