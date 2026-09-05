#!/bin/bash
set -euo pipefail

# Portable SessionStart hook, bundled with the plugin-orchestrator plugin.
# Clones/updates renfordn/claude-plugins into the standard plugin data
# directory so CapabilityMap() finds it in ANY host project, on any device,
# with no per-project settings.json config required.

echo "🔌 plugin-orchestrator: bootstrapping dependency plugins..."

if ! command -v python3 &> /dev/null; then
    echo "❌ Python 3 is required but not found"
    exit 1
fi

PLUGINS_REPO_URL="https://github.com/renfordn/claude-plugins"
PLUGINS_DIR="${CLAUDE_PLUGINS_DIR:-$HOME/.claude/plugins/claude-plugins}"
HARD_DEPS=("agent-isdd" "agent-tdd" "code-reviewer")
SOFT_DEPS=("agent-nelly" "agent-ux")

if [ -d "$PLUGINS_DIR" ]; then
  echo "  ↻ Updating claude-plugins..."
  if ! (cd "$PLUGINS_DIR" && git pull origin main --quiet 2>/dev/null); then
    echo "  ⚠️  Failed to update claude-plugins (using existing checkout)"
  fi
else
  echo "  ⬇️  Cloning claude-plugins..."
  mkdir -p "$(dirname "$PLUGINS_DIR")"
  if ! git clone "$PLUGINS_REPO_URL" "$PLUGINS_DIR" --quiet 2>/dev/null; then
    echo "  ❌ Failed to clone claude-plugins"
    echo "     On a fresh cloud session this repo may need to be attached via"
    echo "     add_repo (owner renfordn, repo claude-plugins) before a plain"
    echo "     git clone can succeed here."
    echo "❌ Failed to set up hard dependencies: ${HARD_DEPS[*]}"
    exit 1
  fi
fi

MISSING_HARD=()
for plugin_name in "${HARD_DEPS[@]}"; do
  [ -d "$PLUGINS_DIR/$plugin_name" ] || MISSING_HARD+=("$plugin_name")
done
if [ ${#MISSING_HARD[@]} -gt 0 ]; then
  echo "❌ Missing hard-dependency plugin directories: ${MISSING_HARD[*]}"
  exit 1
fi

for plugin_name in "${SOFT_DEPS[@]}"; do
  [ -d "$PLUGINS_DIR/$plugin_name" ] || echo "  ⚠️  Soft-dependency plugin missing: $plugin_name (continuing)"
done

for plugin_dir in "$PLUGINS_DIR"/*/; do
  plugin_name="$(basename "$plugin_dir")"
  if [ -f "$plugin_dir/requirements.txt" ]; then
    echo "  🔧 Installing dependencies for $plugin_name..."
    python3 -m pip install -r "$plugin_dir/requirements.txt" --quiet 2>/dev/null \
      || echo "  ⚠️  Failed to install dependencies for $plugin_name"
  fi
done

echo "✅ plugin-orchestrator ready ($PLUGINS_DIR)"
