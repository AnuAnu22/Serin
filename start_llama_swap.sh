#!/usr/bin/env bash
set -euo pipefail

NAME="llama-swap"
PORT="${LLAMA_SWAP_PORT:-8080}"
CONFIG_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/llama-swap"
CONFIG_FILE="$CONFIG_DIR/config.yaml"

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

info()  { echo -e "${CYAN}==>${NC} $1"; }
ok()    { echo -e "${GREEN}  ✓${NC} $1"; }
warn()  { echo -e "${YELLOW}  ⚠${NC} $1"; }

BINARY_URL="https://github.com/maximofn/llama-swap/releases/latest/download/llama-swap_linux_amd64.tar.gz"

# ── Prerequisites ────────────────────────────────────────────────────────────

check_docker() {
    command -v docker &>/dev/null && docker info &>/dev/null 2>&1
}

check_binary() {
    command -v llama-swap &>/dev/null
}

# ── Default config (no personal data) ────────────────────────────────────────

write_default_config() {
    mkdir -p "$CONFIG_DIR"
    if [[ ! -f "$CONFIG_FILE" ]]; then
        cat > "$CONFIG_FILE" <<- 'EOF'
# llama-swap configuration
# See https://github.com/maximofn/llama-swap for full docs

host: 0.0.0.0
port: 8080

backends:
  - name: default
    type: vllm
    model: Qwen/Qwen2.5-7B-Instruct
    url: http://localhost:8000/v1
    api_key: unused
EOF
        ok "default config written to $CONFIG_FILE — edit it before first use"
    fi
}

# ── Install helpers ──────────────────────────────────────────────────────────

install_docker() {
    info "pulling $NAME Docker image..."
    docker pull ghcr.io/maximofn/llama-swap:latest
    ok "Docker image ready"
}

install_binary() {
    local tmp
    tmp=$(mktemp -d)
    info "downloading $NAME binary from GitHub..."
    curl -fsSL "$BINARY_URL" -o "$tmp/llama-swap.tar.gz"
    tar xzf "$tmp/llama-swap.tar.gz" -C "$tmp"
    install "$tmp/llama-swap" /usr/local/bin/llama-swap
    rm -rf "$tmp"
    ok "binary installed to /usr/local/bin/llama-swap"
}

# ── Start helpers ────────────────────────────────────────────────────────────

start_docker() {
    info "starting $NAME via Docker on port $PORT..."
    docker rm -f "$NAME" 2>/dev/null || true
    docker run -d \
        --name "$NAME" \
        --restart unless-stopped \
        -p "$PORT:8080" \
        -v "$CONFIG_FILE:/etc/llama-swap/config.yaml:ro" \
        --gpus all \
        ghcr.io/maximofn/llama-swap:latest
    ok "$NAME running on http://localhost:$PORT"
}

start_binary() {
    info "starting $NAME binary on port $PORT..."
    nohup llama-swap --config "$CONFIG_FILE" > /tmp/llama-swap.log 2>&1 &
    ok "$NAME started (PID $!) — logs: /tmp/llama-swap.log"
}

# ── Main ─────────────────────────────────────────────────────────────────────

if [[ -f ".llama_swap_ready" ]]; then
    if check_docker; then
        start_docker
        exit 0
    elif check_binary; then
        start_binary
        exit 0
    fi
fi

echo ""
echo "  ┌─────────────────────────────────────────────┐"
echo "  │  $NAME — inference proxy                     │"
echo "  │  Runs vLLM, llama.cpp, SGLang & more        │"
echo "  └─────────────────────────────────────────────┘"
echo ""

write_default_config

if check_docker; then
    ok "Docker detected"
    install_docker
    touch ".llama_swap_ready"
    start_docker
elif check_binary; then
    ok "binary detected at $(command -v llama-swap)"
    touch ".llama_swap_ready"
    start_binary
else
    warn "no $NAME installation found"
    echo ""
    echo "  Choose install method:"
    echo "    [1] Docker (recommended) — isolates dependencies"
    echo "    [2] Binary download — no Docker needed"
    echo "    [3] Skip — I'll run it myself"
    echo ""
    read -rp "  Choice [1]: " choice </dev/tty
    choice="${choice:-1}"

    case "$choice" in
        1) install_docker && touch ".llama_swap_ready" && start_docker ;;
        2) install_binary && touch ".llama_swap_ready" && start_binary ;;
        3) info "skipping — set LLAMA_SWAP_PORT in .env when ready" ;;
    esac
fi
