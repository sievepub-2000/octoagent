cd /home/sieve-pub/public-workspace/octoagent
rm -f opt_patch.patch opt_patch2.patch
git add -A
git commit -m "perf: fix message-list.tsx use-client, dedup _json() helper, extract data to YAML, fix FAISS cache, ThreadPoolExecutor, search cache invalidation"
git push origin main
