#!/usr/bin/env bash
# serve_site.sh - Serve MkDocs site on port 80
# This script requires root privileges to bind to port 80.
# Usage: sudo ./scripts/serve_site.sh

# Change to the directory containing the built site
dir=$(dirname "$(realpath "$0")")/../site

# Verify the site directory exists
if [[ ! -d "$dir" ]]; then
  echo "Error: site directory not found at $dir"
  exit 1
fi

# Start a simple HTTP server on port 80 serving the site directory
python3 -m http.server 80 --directory "$dir"
