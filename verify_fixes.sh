echo "=== 1. Git HEAD ==="
cd /home/sieve-pub/public-workspace/octoagent
git log --oneline -1

echo ""
echo "=== 2. Git Status ==="
git status --short

echo ""
echo "=== 3. Verify files exist ==="
for f in backend/src/utils/serialization.py backend/src/tools/builtins/ecosystem_projects.yaml backend/src/governance/model_auth/providers.yaml; do
  if [ -f "$f" ]; then echo "OK: $f ($(wc -l < "$f") lines)"; else echo "MISSING: $f"; fi
done

echo ""
echo "=== 4. No _json defs in builtins ==="
grep -rn "^def _json" backend/src/tools/builtins/ 2>/dev/null | wc -l

echo ""
echo "=== 5. No _json defs in builtins (list) ==="
grep -rln "^def _json" backend/src/tools/builtins/ 2>/dev/null || echo "(none)"

echo ""
echo "=== 6. Verify message-list.tsx has use-client ==="
head -1 frontend/src/components/workspace/messages/message-list.tsx

echo ""
echo "=== 7. Verify memory_middleware max_workers ==="
grep "max_workers" backend/src/agents/middlewares/memory_middleware.py

echo ""
echo "=== 8. Verify system_rag_store has write_gen ==="
grep "_write_gen" backend/src/agents/memory/system_rag_store.py

echo ""
echo "=== 9. Verify FAISS fix (no re-add on cache hit) ==="
grep -c "cache_hit_count" backend/src/storage/rag/faiss_backend.py

echo ""
echo "=== 10. Verify ecosystem_workflow loads from YAML ==="
grep -c "ecosystem_projects.yaml" backend/src/tools/builtins/ecosystem_workflow_tools.py

echo ""
echo "=== 11. Verify providers.yaml loaded ==="
grep -c "providers.yaml" backend/src/governance/model_auth/service.py
