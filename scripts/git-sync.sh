#!/usr/bin/env bash
set -euo pipefail
trap 'echo "ERROR: $0 failed at line $LINENO" >> /var/log/octoagent_errors.log; exit 1' ERR


MODE="${1:-check}"
BRANCH="${2:-main}"

if ! git rev-parse --git-dir >/dev/null 2>&1; then
  echo "Error: current directory is not a git repository."
  exit 2
fi

echo "Fetching origin/${BRANCH}..."
git fetch origin "${BRANCH}:refs/remotes/origin/${BRANCH}"

LOCAL_HEAD="$(git rev-parse HEAD)"
REMOTE_HEAD="$(git rev-parse "origin/${BRANCH}")"

echo "Local HEAD : ${LOCAL_HEAD}"
echo "Remote HEAD: ${REMOTE_HEAD}"

if [[ "${MODE}" == "check" ]]; then
  if [[ -n "$(git status --porcelain)" ]]; then
    echo "Result: local working tree is dirty."
    exit 1
  fi
  if [[ "${LOCAL_HEAD}" != "${REMOTE_HEAD}" ]]; then
    echo "Result: local HEAD is not aligned with origin/${BRANCH}."
    exit 1
  fi
  echo "Result: local repository is fully aligned with origin/${BRANCH}."
  exit 0
fi

if [[ "${MODE}" == "align" ]]; then
  echo "Applying hard alignment to origin/${BRANCH}..."
  git checkout -B "${BRANCH}" "origin/${BRANCH}"
  git reset --hard "origin/${BRANCH}"
  git clean -fdx
  echo "Result: local repository was hard-aligned to origin/${BRANCH}."
  exit 0
fi

echo "Usage: scripts/git-sync.sh [check|align] [branch]"
exit 2
