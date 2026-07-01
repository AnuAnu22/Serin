#!/usr/bin/env bash
set -euo pipefail

# ── Colours ──────────────────────────────────────────────────────────────────
GREEN='\033[0;32m';   YELLOW='\033[1;33m'
CYAN='\033[0;36m';    RED='\033[0;31m'
BOLD='\033[1m';       NC='\033[0m'

info()  { echo -e "${CYAN}==>${NC} $1"; }
ok()    { echo -e "${GREEN}  ✓${NC} $1"; }
warn()  { echo -e "${YELLOW}  ⚠${NC} $1"; }
err()   { echo -e "${RED}  ✘${NC} $1"; }
header(){ echo -e "\n${BOLD}── $1 ──${NC}\n"; }

# ── State file (resumable) ───────────────────────────────────────────────────
STATE_FILE=".setup_state"

load_state() {
    [[ -f "$STATE_FILE" ]] && source "$STATE_FILE" || true
}

save_state() {
    local key="$1" val="$2"
    if grep -q "^${key}=" "$STATE_FILE" 2>/dev/null; then
        sed -i "s/^${key}=.*/${key}=${val}/" "$STATE_FILE"
    else
        echo "${key}=${val}" >> "$STATE_FILE"
    fi
}

init_state() {
    [[ -f "$STATE_FILE" ]] || touch "$STATE_FILE"
}

# ── Hardware detection ───────────────────────────────────────────────────────

detect_hardware() {
    header "Detecting hardware"

    GPU_NAME=""; GPU_VRAM=0; GPU_COUNT=0; HAS_CUDA=false
    if command -v nvidia-smi &>/dev/null; then
        GPU_INFO=$(nvidia-smi --query-gpu=name,memory.total --format=csv,noheader 2>/dev/null | head -1) || true
        if [[ -n "$GPU_INFO" ]]; then
            GPU_NAME=$(echo "$GPU_INFO" | cut -d, -f1 | xargs)
            GPU_VRAM_RAW=$(echo "$GPU_INFO" | cut -d, -f2 | grep -oP '\d+') || GPU_VRAM_RAW=0
            GPU_VRAM=$((GPU_VRAM_RAW / 1024))
            GPU_COUNT=$(nvidia-smi --query-gpu=count --format=csv,noheader 2>/dev/null | head -1) || GPU_COUNT=0
            HAS_CUDA=true
            ok "GPU: $GPU_NAME  |  VRAM: ${GPU_VRAM}GB  |  Count: $GPU_COUNT"
        fi
    fi
    if ! $HAS_CUDA; then
        warn "No NVIDIA GPU detected — will use CPU or remote API"
    fi

    CPU_CORES=$(nproc)
    RAM_KB=$(grep MemTotal /proc/meminfo 2>/dev/null | awk '{print $2}') || RAM_KB=0
    RAM_GB=$((RAM_KB / 1024 / 1024))
    ok "CPU: ${CPU_CORES} cores  |  RAM: ${RAM_GB}GB"

    save_state "HAS_CUDA" "$HAS_CUDA"
    save_state "GPU_VRAM" "$GPU_VRAM"
    save_state "CPU_CORES" "$CPU_CORES"
}

# ── Recommend defaults ───────────────────────────────────────────────────────

recommend_llm() {
    if $HAS_CUDA; then
        if (( GPU_VRAM >= 20 )); then
            echo "hugging-quants/Meta-Llama-3.1-8B-Instruct-GPTQ-INT4"
        elif (( GPU_VRAM >= 10 )); then
            echo "ModelCloud/Llama-3.2-3B-Instruct-gptqmodel-4bit-vortex-v3"
        else
            echo "Qwen/Qwen2.5-1.5B-Instruct"
        fi
    else
        echo "Qwen/Qwen2.5-1.5B-Instruct"
    fi
}

# ── Env wizard ───────────────────────────────────────────────────────────────

edit_env() {
    local var="$1" prompt="$2" default="$3" current
    current=$(grep "^${var}=" .env 2>/dev/null | cut -d= -f2- || echo "")
    current="${current:-$default}"
    echo ""
    read -rp "  $prompt [$current]: " input </dev/tty
    echo "${input:-$current}"
}

env_wizard() {
    header "Environment configuration"

    if [[ ! -f ".env" ]]; then
        cp .env.example .env 2>/dev/null || touch .env
        ok "created .env from .env.example"
    fi

    # Only prompt for required vars on first run
    local first_run
    first_run=$(grep "^SETUP_COMPLETE=" "$STATE_FILE" 2>/dev/null || echo "false")

    if [[ "$first_run" != "true" ]]; then
        local tok
        tok=$(grep "^DISCORD_TOKEN=" .env 2>/dev/null | cut -d= -f2- || echo "")
        if [[ -z "$tok" ]]; then
            warn "DISCORD_TOKEN is required"
            read -rp "  Discord bot token: " tok </dev/tty
            if grep -q "^DISCORD_TOKEN=" .env 2>/dev/null; then
                sed -i "s/^DISCORD_TOKEN=.*/DISCORD_TOKEN=${tok}/" .env
            else
                echo "DISCORD_TOKEN=${tok}" >> .env
            fi
        fi
    fi

    local model
    model=$(recommend_llm)
    model=$(edit_env "LLM_MODEL" "LLM model" "$model")

    local provider
    provider=$(edit_env "LLM_PROVIDER" "Provider (vllm/openai/custom)" "vllm")

    local url
    url=$(edit_env "VLLM_BASE_URL" "LLM endpoint URL" "http://localhost:8080/v1")

    local vision
    vision=$(edit_env "LLM_SUPPORTS_VISION" "Supports vision? (true/false)" "false")

    local audio
    audio=$(edit_env "LLM_SUPPORTS_AUDIO" "Supports audio? (true/false)" "false")

    # Write updated .env
    cat > .env <<- ENVEOF
DISCORD_TOKEN=${tok:-}
LLM_MODEL=${model}
LLM_PROVIDER=${provider}
VLLM_BASE_URL=${url}
LLM_SUPPORTS_VISION=${vision}
LLM_SUPPORTS_AUDIO=${audio}
ENVEOF
    ok ".env written"
}

# ── llama-swap install ───────────────────────────────────────────────────────

install_llama_swap() {
    header "llama-swap setup"

    local choice
    echo "  How would you like to run llama-swap?"
    echo "    [1] Docker (recommended) — clean isolation, auto-restart"
    echo "    [2] Binary download — lightweight, no Docker needed"
    echo "    [3] Skip — I'll run it myself"
    echo ""
    read -rp "  Choice [1]: " choice </dev/tty
    choice="${choice:-1}"

    case "$choice" in
        1)
            if command -v docker &>/dev/null; then
                ok "Docker detected"
                docker pull ghcr.io/maximofn/llama-swap:latest
                save_state "LLAMA_SWAP_METHOD" "docker"
                ok "llama-swap image ready"
            else
                warn "Docker not found — installing binary instead"
                install_llama_swap_binary
            fi
            ;;
        2) install_llama_swap_binary ;;
        3) save_state "LLAMA_SWAP_METHOD" "manual" ;;
    esac
}

install_llama_swap_binary() {
    local url="https://github.com/maximofn/llama-swap/releases/latest/download/llama-swap_linux_amd64.tar.gz"
    local tmp
    tmp=$(mktemp -d)
    info "Downloading llama-swap binary..."
    curl -fsSL "$url" -o "$tmp/llama-swap.tar.gz"
    tar xzf "$tmp/llama-swap.tar.gz" -C "$tmp"
    sudo install "$tmp/llama-swap" /usr/local/bin/llama-swap 2>/dev/null || \
        install "$tmp/llama-swap" "$HOME/.local/bin/llama-swap"
    rm -rf "$tmp"
    save_state "LLAMA_SWAP_METHOD" "binary"
    ok "llama-swap installed to $(command -v llama-swap)"
}

# ── Qdrant check ─────────────────────────────────────────────────────────────

check_qdrant() {
    if command -v docker &>/dev/null; then
        if ! docker ps --format '{{.Names}}' 2>/dev/null | grep -q qdrant; then
            header "Qdrant (vector database)"
            echo "  Qdrant is needed for memory. Start it now?"
            echo "    [1] Yes, via Docker (recommended)"
            echo "    [2] No, I'll handle it"
            echo ""
            read -rp "  Choice [1]: " qc </dev/tty
            if [[ "${qc:-1}" == "1" ]]; then
                docker run -d --name qdrant --restart unless-stopped \
                    -p 6333:6333 -p 6334:6334 \
                    qdrant/qdrant:latest
                ok "Qdrant started on port 6333"
            fi
        else
            ok "Qdrant already running"
        fi
    fi
}

# ── Main ─────────────────────────────────────────────────────────────────────

main() {
    clear
    echo ""
    echo "  ┌─────────────────────────────────────────────┐"
    echo "  │  Serin Setup Wizard                         │"
    echo "  │  Hardware-aware, resumable, no secrets      │"
    echo "  └─────────────────────────────────────────────┘"
    echo ""

    init_state
    load_state

    local prev_setup
    prev_setup=$(grep "^SETUP_COMPLETE=" "$STATE_FILE" 2>/dev/null || echo "false")

    if [[ "$prev_setup" == "true" ]]; then
        header "Resuming previous setup"
        echo "  Detected a previous setup. What would you like to change?"
        echo "    [1] Re-detect hardware"
        echo "    [2] Reconfigure .env"
        echo "    [3] Reinstall llama-swap"
        echo "    [4] Full redo"
        echo "    [5] Nothing — exit"
        echo ""
        read -rp "  Choice [5]: " change </dev/tty
        change="${change:-5}"
        case "$change" in
            1) detect_hardware ;;
            2) env_wizard ;;
            3) install_llama_swap ;;
            4) rm -f "$STATE_FILE"; exec "$0" ;;
            5) info "Nothing changed. Exiting."; exit 0 ;;
        esac
        save_state "SETUP_COMPLETE" "true"
        ok "Setup updated"
        exit 0
    fi

    detect_hardware

    header "Recommended defaults"
    local rec_model
    rec_model=$(recommend_llm)
    echo "  Based on your hardware:"
    echo "    LLM model:  ${BOLD}$rec_model${NC}"
    if $HAS_CUDA; then
        echo "    LLM backend: ${BOLD}llama-swap via Docker${NC}"
    else
        echo "    LLM backend: ${BOLD}API endpoint${NC}"
    fi
    echo ""

    env_wizard
    install_llama_swap
    check_qdrant

    save_state "SETUP_COMPLETE" "true"
    save_state "SETUP_DATE" "$(date +%Y-%m-%d)"

    header "Done"
    echo "  Next steps:"
    echo "    ${BOLD}bash start_llama_swap.sh${NC}  — start the LLM server"
    echo "    ${BOLD}uv run discord_bot.py${NC}     — start the bot"
    echo ""
    ok "Setup complete"
}

main "$@"
