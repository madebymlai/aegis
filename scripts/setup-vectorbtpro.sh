#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
cd "$REPO_ROOT"

REF="${VECTORBTPRO_REF:-develop}"
EXTRA="${VECTORBTPRO_EXTRA:-base}"
PYTHON_VERSION="${PYTHON_VERSION:-3.12}"
VENV_DIR="${VENV_DIR:-.venv}"
VBT_SETTINGS_FILE="${VBT_SETTINGS_FILE:-vbt.toml}"

write_mcp_configs() {
  local python_path
  local settings_path

  python_path="$(pwd -P)/$VENV_DIR/bin/python"
  settings_path="$(pwd -P)/$VBT_SETTINGS_FILE"

  cat > .mcp.json <<EOF
{
  "mcpServers": {
    "vectorbtpro": {
      "type": "stdio",
      "command": "$python_path",
      "args": [
        "-m",
        "vectorbtpro.mcp_server"
      ],
      "env": {
        "GITHUB_TOKEN": "$GITHUB_TOKEN",
        "OPENAI_API_KEY": "${OPENAI_API_KEY:-}",
        "VBT_SETTINGS_PATH": "$settings_path"
      }
    }
  }
}
EOF

  cat > opencode.json <<EOF
{
  "\$schema": "https://opencode.ai/config.json",
  "mcp": {
    "vectorbtpro": {
      "type": "local",
      "command": [
        "$python_path",
        "-m",
        "vectorbtpro.mcp_server"
      ],
      "environment": {
        "GITHUB_TOKEN": "$GITHUB_TOKEN",
        "OPENAI_API_KEY": "${OPENAI_API_KEY:-}",
        "VBT_SETTINGS_PATH": "$settings_path"
      },
      "timeout": 120000,
      "enabled": true
    }
  }
}
EOF
}

write_vbt_settings() {
  cat > "$VBT_SETTINGS_FILE" <<EOF
[knowledge.assets.vbt]
token = "$GITHUB_TOKEN"

[knowledge.chat]
embeddings = "openai"
completions = "openai"

[knowledge.assets.vbt.chat.doc_ranker_config]
doc_store = "lmdb"
emb_store = "lmdb"

[knowledge.assets.vbt.chat.doc_ranker_config.doc_store_configs.lmdb.open_kwargs]
flag = "c"
map_size = 21474836480

[knowledge.assets.vbt.chat.doc_ranker_config.emb_store_configs.lmdb.open_kwargs]
flag = "c"
map_size = 21474836480
EOF
  chmod 600 "$VBT_SETTINGS_FILE"
}

if ! command -v uv >/dev/null 2>&1; then
  echo "uv is required. Install it from https://github.com/astral-sh/uv" >&2
  exit 1
fi

if [[ -f .env ]]; then
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
fi

if [[ -z "${GITHUB_USERNAME:-}" ]]; then
  read -r -p "GitHub username: " GITHUB_USERNAME
fi

if [[ -z "${GITHUB_TOKEN:-}" ]]; then
  read -r -s -p "GitHub token: " GITHUB_TOKEN
  printf '\n'
fi

if [[ -z "${OPENAI_API_KEY:-}" ]]; then
  read -r -s -p "OpenAI API key for optional docs/chat search features [press Enter to skip]: " OPENAI_API_KEY
  printf '\n'
fi

if [[ -z "$GITHUB_USERNAME" || -z "$GITHUB_TOKEN" ]]; then
  echo "GitHub username and token are required." >&2
  exit 1
fi

cat > .env <<EOF
GITHUB_USERNAME=$GITHUB_USERNAME
GITHUB_TOKEN=$GITHUB_TOKEN
OPENAI_API_KEY=${OPENAI_API_KEY:-}
EOF
chmod 600 .env
echo "Environment written to $REPO_ROOT/.env"

if [[ -d "$VENV_DIR" ]]; then
  read -r -p "$VENV_DIR already exists. Replace it? [y/N] " replace
  case "$replace" in
    [yY]|[yY][eE][sS]) rm -rf "$VENV_DIR" ;;
    *) echo "Keeping existing $VENV_DIR" ;;
  esac
fi

uv venv "$VENV_DIR" --python "$PYTHON_VERSION"

export GITHUB_USERNAME GITHUB_TOKEN

if [[ -n "$EXTRA" ]]; then
  package="vectorbtpro[$EXTRA] @ git+https://$GITHUB_USERNAME:$GITHUB_TOKEN@github.com/polakowo/vectorbt.pro.git@$REF"
else
  package="git+https://$GITHUB_USERNAME:$GITHUB_TOKEN@github.com/polakowo/vectorbt.pro.git@$REF"
fi

uv pip install --python "$VENV_DIR/bin/python" -U "$package"
"$VENV_DIR/bin/python" -c "import vectorbtpro as vbt; print(vbt.__version__)"
write_vbt_settings
write_mcp_configs

echo "VectorBT PRO is ready. Activate with: source $VENV_DIR/bin/activate"
echo "VectorBT PRO settings written to $REPO_ROOT/$VBT_SETTINGS_FILE"
echo "Claude MCP config written to $REPO_ROOT/.mcp.json"
echo "OpenCode MCP config written to $REPO_ROOT/opencode.json"
