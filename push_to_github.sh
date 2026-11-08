#!/usr/bin/env bash
set -euo pipefail
export GH_HOST=github.com
cd "$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
if ! command -v gh >/dev/null 2>&1; then
  printf '%s\n' 'GitHub CLI (gh) is unavailable. Run this script on M5 after gh is available.' >&2
  exit 127
fi
command -v python3 >/dev/null 2>&1 || { printf '%s\n' 'python3 is required for the package integrity check.' >&2; exit 127; }
if [[ -n "$(git status --porcelain --untracked-files=all)" ]]; then
  printf '%s\n' 'The package has uncommitted changes. Review them and regenerate the manifest before pushing.' >&2
  exit 1
fi
python3 - <<'PY'
import csv,hashlib,subprocess
from pathlib import Path
root=Path.cwd()
tracked=set(subprocess.check_output(['git','ls-files','-z']).decode().split('\0'))-{''}
with (root/'FILE_MANIFEST.csv').open(newline='',encoding='utf-8')as f:rows=list(csv.DictReader(f))
expected={r['path']for r in rows}|{'FILE_MANIFEST.csv'}
assert tracked==expected, 'Tracked files differ from the reviewed package manifest.'
total=0
for r in rows:
 p=root/r['path']
 assert not p.is_symlink() and p.is_file(), 'Unexpected link or missing file.'
 assert not ({'data','raw','cache','__pycache__'}&set(p.relative_to(root).parts)), 'Excluded directory found.'
 size=p.stat().st_size
 assert size==int(r['bytes']) and size<50_000_000, 'File size check failed.'
 with p.open('rb')as stream:
  h=hashlib.sha256()
  for block in iter(lambda:stream.read(1024*1024),b''):h.update(block)
 assert h.hexdigest()==r['sha256'], 'Package checksum mismatch.'
 total+=size
total+=(root/'FILE_MANIFEST.csv').stat().st_size
assert total<500_000_000, 'Package exceeds the size limit.'
print(f'Package integrity verified: {len(tracked)} files, {total:,} bytes.')
PY
if ! gh auth status --hostname github.com >/dev/null 2>&1; then
  gh auth login --web --hostname github.com --git-protocol https
fi
owner="$(gh api user --jq '.login')"
[[ -n "$owner" ]] || { printf '%s\n' 'Unable to determine the authenticated GitHub account.' >&2; exit 1; }
description='Replication package: Stock Connect closures and price delay'
if git remote get-url origin >/dev/null 2>&1; then
  origin_url="$(git remote get-url origin)"
  full=''
  for candidate in connect-closed-replication connect-closed-replication-2026; do
    case "$origin_url" in
      "https://github.com/$owner/$candidate"|"https://github.com/$owner/$candidate.git"|"git@github.com:$owner/$candidate"|"git@github.com:$owner/$candidate.git") full="$owner/$candidate"; break ;;
    esac
  done
  [[ -n "$full" ]] || { printf '%s\n' 'Existing origin is outside the expected account/repository names; stopping.' >&2; exit 1; }
  [[ "$(gh repo view "$full" --json isPrivate --jq '.isPrivate')" == true ]] || { printf '%s\n' 'Origin is not private; stopping.' >&2; exit 1; }
  git push -u origin main
else
  full=''
  for candidate in connect-closed-replication connect-closed-replication-2026; do
    if gh repo view "$owner/$candidate" --json name >/dev/null 2>&1; then
      continue
    fi
    gh repo create "$owner/$candidate" --private --source . --push --description "$description"
    full="$owner/$candidate"
    break
  done
  [[ -n "$full" ]] || { printf '%s\n' 'Both private repository names already exist; no existing repository was overwritten.' >&2; exit 1; }
fi
[[ "$(gh repo view "$full" --json isPrivate --jq '.isPrivate')" == true ]] || { printf '%s\n' 'Private visibility verification failed.' >&2; exit 1; }
local_head="$(git rev-parse HEAD)"
remote_head="$(gh api "repos/$full/git/ref/heads/main" --jq '.object.sha')"
[[ "$local_head" == "$remote_head" ]] || { printf '%s\n' 'Remote main does not match the local commit.' >&2; exit 1; }
gh repo view "$full" --json url,isPrivate > ../GITHUB_UPLOAD_STATUS.json
cat ../GITHUB_UPLOAD_STATUS.json
printf '\n%s\n' 'Uploaded and verified private. Only authorized collaborators can open this URL.'
