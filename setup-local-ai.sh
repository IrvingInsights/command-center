#!/usr/bin/env bash
# Local AI dev stack: Ollama + Open WebUI + code-server + Continue
# Run as root or with sudo. Tested on x86_64 Ubuntu/Debian, CPU-only.
set -euo pipefail

OLLAMA_VERSION="v0.21.2"
CODE_SERVER_VERSION="4.117.0"
OPEN_WEBUI_VENV="/opt/open-webui-env"
CODE_SERVER_DIR="/opt/code-server-${CODE_SERVER_VERSION}-linux-amd64"
CODE_SERVER_BIN="/usr/local/bin/code-server"

log() { echo "[setup] $*"; }

# ── 1. Git ──────────────────────────────────────────────────────────────────
log "Checking git..."
if ! command -v git &>/dev/null; then
  apt-get install -y git
fi
git --version

# ── 2. Ollama ───────────────────────────────────────────────────────────────
log "Installing Ollama ${OLLAMA_VERSION}..."
if ! command -v ollama &>/dev/null; then
  apt-get install -y zstd
  curl -fSL "https://github.com/ollama/ollama/releases/download/${OLLAMA_VERSION}/ollama-linux-amd64.tar.zst" \
    -o /tmp/ollama.tar.zst
  tar --use-compress-program=zstd -xf /tmp/ollama.tar.zst -C /usr/local
  rm /tmp/ollama.tar.zst
fi
ollama --version

# Start Ollama server (use systemd if available, otherwise background process)
if command -v systemctl &>/dev/null && systemctl --version &>/dev/null 2>&1; then
  systemctl enable --now ollama
else
  if ! pgrep -x ollama &>/dev/null; then
    nohup ollama serve >/var/log/ollama.log 2>&1 &
    sleep 3
  fi
fi

# Pull models
log "Pulling models (this may take a while on first run)..."
ollama pull qwen2.5-coder:7b
ollama pull llama3.2:3b
ollama pull nomic-embed-text
ollama list

# ── 3. Open WebUI ───────────────────────────────────────────────────────────
log "Installing Open WebUI..."
if [[ ! -d "${OPEN_WEBUI_VENV}" ]]; then
  python3 -m venv "${OPEN_WEBUI_VENV}"
fi
"${OPEN_WEBUI_VENV}/bin/pip" install --quiet open-webui
"${OPEN_WEBUI_VENV}/bin/open-webui" --version

# Start Open WebUI
if ! pgrep -f "open-webui serve" &>/dev/null; then
  DATA_DIR=/home/"${SUDO_USER:-$USER}"/.open-webui \
  WEBUI_PORT=8080 \
  OLLAMA_BASE_URL=http://127.0.0.1:11434 \
  RAG_EMBEDDING_ENGINE=ollama \
  RAG_EMBEDDING_MODEL=nomic-embed-text \
  TRANSFORMERS_OFFLINE=1 \
  nohup "${OPEN_WEBUI_VENV}/bin/open-webui" serve >/var/log/open-webui.log 2>&1 &
  log "Open WebUI starting on http://localhost:8080 ..."
fi

# ── 4. code-server (VS Code in browser) ─────────────────────────────────────
log "Installing code-server ${CODE_SERVER_VERSION}..."
if [[ ! -f "${CODE_SERVER_BIN}" ]]; then
  curl -fSL "https://github.com/coder/code-server/releases/download/v${CODE_SERVER_VERSION}/code-server-${CODE_SERVER_VERSION}-linux-amd64.tar.gz" \
    -o /tmp/code-server.tar.gz
  tar -xzf /tmp/code-server.tar.gz -C /opt
  ln -sf "${CODE_SERVER_DIR}/bin/code-server" "${CODE_SERVER_BIN}"
  rm /tmp/code-server.tar.gz
fi
code-server --version

# Configure code-server
CS_CONFIG="${HOME}/.config/code-server/config.yaml"
mkdir -p "$(dirname "${CS_CONFIG}")"
if [[ ! -f "${CS_CONFIG}" ]]; then
  cat > "${CS_CONFIG}" <<CSCONF
bind-addr: 0.0.0.0:8443
auth: password
password: changeme
cert: false
CSCONF
fi

# Start code-server
if ! pgrep -f "code-server" &>/dev/null; then
  nohup code-server --config "${CS_CONFIG}" >/var/log/code-server.log 2>&1 &
  log "code-server starting on http://localhost:8443 ..."
fi

# ── 5. Continue extension ────────────────────────────────────────────────────
# Install from VS Code Marketplace (requires internet access to marketplace.visualstudio.com)
log "Installing Continue extension..."
code-server --install-extension Continue.continue || \
  log "WARNING: Could not install Continue extension automatically. Install manually from the Extensions panel."

# Write Continue config
CONTINUE_CFG="${HOME}/.continue/config.json"
mkdir -p "$(dirname "${CONTINUE_CFG}")"
if [[ ! -f "${CONTINUE_CFG}" ]]; then
  cp "$(dirname "$0")/.continue/config.json" "${CONTINUE_CFG}" 2>/dev/null || \
  cat > "${CONTINUE_CFG}" <<'CONTINUECONF'
{
  "models": [
    {
      "title": "Qwen2.5 Coder 7B (local)",
      "provider": "ollama",
      "model": "qwen2.5-coder:7b",
      "apiBase": "http://localhost:11434"
    },
    {
      "title": "Llama 3.2 3B (local)",
      "provider": "ollama",
      "model": "llama3.2:3b",
      "apiBase": "http://localhost:11434"
    }
  ],
  "tabAutocompleteModel": {
    "title": "Qwen2.5 Coder (autocomplete)",
    "provider": "ollama",
    "model": "qwen2.5-coder:7b",
    "apiBase": "http://localhost:11434"
  },
  "embeddingsProvider": {
    "provider": "ollama",
    "model": "nomic-embed-text",
    "apiBase": "http://localhost:11434"
  }
}
CONTINUECONF
fi

# ── Validation ───────────────────────────────────────────────────────────────
log ""
log "=== Validation checklist ==="
log "1. Ollama:       curl http://localhost:11434"
log "2. Models:       ollama list"
log "3. Open WebUI:   curl http://localhost:8080 | head -3"
log "4. code-server:  curl http://localhost:8443 | head -3"
log ""
log "Open WebUI   → http://localhost:8080  (create admin account on first visit)"
log "code-server  → http://localhost:8443  (password in ~/.config/code-server/config.yaml)"
log "Continue     → Open the Continue panel (⌘+Shift+P → 'Continue: Focus') in code-server"
log ""
log "First test prompt in Continue:"
log "  Select any code → Ctrl+Shift+J → Ask: 'Explain this code'"
