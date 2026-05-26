#!/usr/bin/env bash
# OctoAgent desktop shortcut installer (Phase 5, 2026-05-26).
#
# Linux: writes ~/.local/share/applications/octoagent.desktop
# macOS: writes ~/Applications/OctoAgent.app (AppleScript launcher)
#
# Both shortcuts invoke `octoagent start` and then open the WebUI.

set -euo pipefail

REPO_ROOT="${OCTOAGENT_HOME:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
OCTOAGENT_BIN="${OCTOAGENT_BIN:-$REPO_ROOT/scripts/octoagent}"
WEBUI_URL="${OCTOAGENT_PUBLIC_BASE_URL:-http://127.0.0.1:19800}"

ACTION="${1:-install}"

uninstall_linux() {
    rm -f "$HOME/.local/share/applications/octoagent.desktop"
    rm -f "$HOME/.local/share/applications/octoagent-stop.desktop"
    echo "Removed Linux .desktop entries."
}

install_linux() {
    local apps="$HOME/.local/share/applications"
    mkdir -p "$apps"

    local icon_path="$REPO_ROOT/frontend/public/favicon.ico"
    [ -f "$icon_path" ] || icon_path="utilities-terminal"

    cat >"$apps/octoagent.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=OctoAgent
Comment=Start OctoAgent and open the WebUI
Exec=bash -c "$OCTOAGENT_BIN start && xdg-open $WEBUI_URL"
Icon=$icon_path
Terminal=false
Categories=Development;Utility;
StartupNotify=true
EOF

    cat >"$apps/octoagent-stop.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=OctoAgent (Stop)
Comment=Stop the OctoAgent service
Exec=$OCTOAGENT_BIN stop
Icon=$icon_path
Terminal=true
Categories=Development;Utility;
EOF

    update-desktop-database "$apps" 2>/dev/null || true
    echo "Installed: $apps/octoagent.desktop"
    echo "Installed: $apps/octoagent-stop.desktop"
}

install_macos() {
    local app_dir="$HOME/Applications/OctoAgent.app"
    rm -rf "$app_dir"
    mkdir -p "$app_dir/Contents/MacOS" "$app_dir/Contents/Resources"

    cat >"$app_dir/Contents/Info.plist" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleName</key><string>OctoAgent</string>
    <key>CFBundleDisplayName</key><string>OctoAgent</string>
    <key>CFBundleIdentifier</key><string>pub.sieve.octoagent</string>
    <key>CFBundleVersion</key><string>2026.5.26</string>
    <key>CFBundleExecutable</key><string>octoagent-launcher</string>
    <key>CFBundleIconFile</key><string>icon</string>
    <key>LSUIElement</key><false/>
</dict>
</plist>
EOF

    cat >"$app_dir/Contents/MacOS/octoagent-launcher" <<EOF
#!/bin/bash
"$OCTOAGENT_BIN" start
open "$WEBUI_URL"
EOF
    chmod +x "$app_dir/Contents/MacOS/octoagent-launcher"

    # Stop helper
    local stop_dir="$HOME/Applications/OctoAgent Stop.app"
    rm -rf "$stop_dir"
    mkdir -p "$stop_dir/Contents/MacOS"
    cat >"$stop_dir/Contents/Info.plist" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<plist version="1.0"><dict>
<key>CFBundleName</key><string>OctoAgent Stop</string>
<key>CFBundleIdentifier</key><string>pub.sieve.octoagent.stop</string>
<key>CFBundleExecutable</key><string>octoagent-stop</string>
</dict></plist>
EOF
    cat >"$stop_dir/Contents/MacOS/octoagent-stop" <<EOF
#!/bin/bash
"$OCTOAGENT_BIN" stop
EOF
    chmod +x "$stop_dir/Contents/MacOS/octoagent-stop"

    # Refresh Launch Services cache
    /System/Library/Frameworks/CoreServices.framework/Versions/A/Frameworks/LaunchServices.framework/Versions/A/Support/lsregister -f "$app_dir" "$stop_dir" 2>/dev/null || true

    echo "Installed: $app_dir"
    echo "Installed: $stop_dir"
}

uninstall_macos() {
    rm -rf "$HOME/Applications/OctoAgent.app" "$HOME/Applications/OctoAgent Stop.app"
    echo "Removed macOS .app bundles."
}

case "$(uname -s)" in
    Darwin)
        case "$ACTION" in
            install) install_macos ;;
            uninstall) uninstall_macos ;;
            *) echo "Usage: $0 {install|uninstall}" >&2; exit 2 ;;
        esac
        ;;
    Linux)
        case "$ACTION" in
            install) install_linux ;;
            uninstall) uninstall_linux ;;
            *) echo "Usage: $0 {install|uninstall}" >&2; exit 2 ;;
        esac
        ;;
    *)
        echo "Unsupported OS: $(uname -s)" >&2
        exit 2
        ;;
esac
