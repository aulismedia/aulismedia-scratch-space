#!/usr/bin/env bash
set -euo pipefail

if [[ $# -eq 0 ]]; then
  echo "Usage: drag a folder from Finder into the terminal after the script name"
  echo "  e.g.: bash tree.sh /path/to/folder"
  exit 1
fi

ROOT="${1%/}"

if [[ ! -d "$ROOT" ]]; then
  echo "Error: '$ROOT' is not a directory"
  exit 1
fi

FOLDER_NAME="${ROOT##*/}"
OUTPUT_FILE="$(pwd)/tree_${FOLDER_NAME}_$(date +%Y%m%d_%H%M%S).json"

echo "Building tree for: $ROOT"

python3 - "$ROOT" "$OUTPUT_FILE" <<'PYEOF'
import os, sys, json

def build_node(path):
    name = os.path.basename(path)

    if os.path.islink(path):
        return {"type": "symlink", "name": name, "size": 0}

    if os.path.isfile(path):
        return {"type": "file", "name": name, "size": os.path.getsize(path)}

    if os.path.isdir(path):
        children = []
        total_size = 0
        try:
            entries = sorted(os.scandir(path), key=lambda e: (e.is_file(), e.name.lower()))
            for entry in entries:
                child = build_node(entry.path)
                children.append(child)
                total_size += child.get("size", 0)
        except PermissionError:
            pass
        return {"type": "directory", "name": name, "size": total_size, "children": children}

    return {"type": "unknown", "name": name, "size": 0}

root_path = sys.argv[1]
output_file = sys.argv[2]

tree = build_node(root_path)

with open(output_file, "w", encoding="utf-8") as f:
    json.dump(tree, f, ensure_ascii=False, indent=2)

print(f"Done. JSON saved to:\n  {output_file}")
PYEOF
