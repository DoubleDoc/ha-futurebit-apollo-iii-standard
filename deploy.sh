#!/bin/sh
# Copy the integration from this repo into the live Home Assistant config.
# Backs up the live copy first. Does not restart HA: Python and manifest
# changes take effect only after a restart (confirm before restarting).
set -eu

REPO_DIR=$(cd "$(dirname "$0")" && pwd)
SRC="$REPO_DIR/custom_components/apollo_iii"
DEST=/config/custom_components/apollo_iii
BACKUP_ROOT=/data/home/apollo-iii-backups

[ -d "$SRC" ] || { echo "Missing $SRC" >&2; exit 1; }

if [ -d "$DEST" ]; then
    stamp=$(date +%Y%m%d-%H%M%S)
    mkdir -p "$BACKUP_ROOT"
    cp -a "$DEST" "$BACKUP_ROOT/apollo_iii-$stamp"
    echo "Backed up live copy to $BACKUP_ROOT/apollo_iii-$stamp"
fi

# Replace contents (so files deleted in the repo are removed live too),
# leaving __pycache__ for Python to regenerate.
rm -rf "$DEST.new"
cp -a "$SRC" "$DEST.new"
find "$DEST.new" -name __pycache__ -prune -exec rm -rf {} +
rm -rf "$DEST"
mv "$DEST.new" "$DEST"

echo "Deployed $(git -C "$REPO_DIR" describe --always --dirty) to $DEST"
echo "Restart Home Assistant to load it (run 'ha core check' first)."
