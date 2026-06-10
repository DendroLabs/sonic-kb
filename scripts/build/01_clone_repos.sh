#!/usr/bin/env bash
# Clone SONiC source repos at the 202511 release for KB extraction.
#
# Repos land in build/repos/ (gitignored). sonic-buildimage is cloned blobless
# + sparse (yang models, rules, dockers, files) to keep the download small. sonic-frr has no
# release branches, so we check out the exact commit pinned by the
# src/sonic-frr/frr submodule in sonic-buildimage.
#
# Usage: scripts/build/01_clone_repos.sh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
REPOS_DIR="$ROOT/build/repos"
BRANCH="202511"
FRR_FALLBACK_BRANCH="frr/10.3"

mkdir -p "$REPOS_DIR"

clone_shallow() {
  local repo="$1"
  local dest="$REPOS_DIR/$repo"
  if [ -d "$dest/.git" ]; then
    echo "== $repo already cloned, skipping"
    return
  fi
  echo "== cloning $repo @ $BRANCH"
  if ! git clone --depth 1 --branch "$BRANCH" \
      "https://github.com/sonic-net/$repo.git" "$dest"; then
    echo "   no $BRANCH branch; falling back to default branch"
    git clone --depth 1 "https://github.com/sonic-net/$repo.git" "$dest"
  fi
}

clone_shallow sonic-swss
clone_shallow sonic-sairedis
clone_shallow sonic-platform-daemons
clone_shallow sonic-dbsyncd   # lldpsyncd
clone_shallow sonic-stp       # stpd (master only — no release branches)
clone_shallow sonic-utilities # config/show CLI entry points for code paths

# sonic-buildimage: blobless + sparse checkout — we only need the YANG models
# (CONFIG_DB schemas), rules/ (version pins), and .gitmodules.
BUILDIMAGE_DEST="$REPOS_DIR/sonic-buildimage"
if [ -d "$BUILDIMAGE_DEST/.git" ]; then
  echo "== sonic-buildimage already cloned, skipping"
else
  echo "== cloning sonic-buildimage @ $BRANCH (sparse: yang models + rules)"
  git clone --depth 1 --branch "$BRANCH" --filter=blob:none --no-checkout \
    "https://github.com/sonic-net/sonic-buildimage.git" "$BUILDIMAGE_DEST"
  git -C "$BUILDIMAGE_DEST" sparse-checkout set \
    src/sonic-yang-models rules dockers files .gitmodules
  git -C "$BUILDIMAGE_DEST" checkout -q "$BRANCH"
fi

# sonic-frr: fetch the exact commit sonic-buildimage 202511 pins as a submodule.
FRR_DEST="$REPOS_DIR/sonic-frr"
if [ -d "$FRR_DEST/.git" ]; then
  echo "== sonic-frr already cloned, skipping"
else
  FRR_SHA="$(git -C "$BUILDIMAGE_DEST" ls-tree HEAD src/sonic-frr/frr | awk '{print $3}')"
  echo "== cloning sonic-frr @ ${FRR_SHA:-<none>} (pinned by sonic-buildimage)"
  git init -q "$FRR_DEST"
  git -C "$FRR_DEST" remote add origin https://github.com/sonic-net/sonic-frr.git
  if [ -n "$FRR_SHA" ] && git -C "$FRR_DEST" fetch --depth 1 origin "$FRR_SHA"; then
    git -C "$FRR_DEST" checkout -q FETCH_HEAD
  else
    echo "   fetch by SHA failed; falling back to $FRR_FALLBACK_BRANCH"
    git -C "$FRR_DEST" fetch --depth 1 origin "$FRR_FALLBACK_BRANCH"
    git -C "$FRR_DEST" checkout -q FETCH_HEAD
  fi
fi

echo
echo "Cloned repos:"
for d in "$REPOS_DIR"/*/; do
  name="$(basename "$d")"
  head="$(git -C "$d" log -1 --format='%h %cs %s' 2>/dev/null | cut -c1-90)"
  echo "  $name: $head"
done
