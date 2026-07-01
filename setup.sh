#!/usr/bin/env bash
# ── Serin unified setup — services, deps, config ──────────────────────────
# Usage: bash setup.sh [command]
# Shells: bash / fish / zsh — auto-detected for shell-appropriate output
#
# Commands:
#   setup       Full interactive setup wizard (default)
#   start       Start all configured services (llama-swap + Qdrant)
#   stop        Stop all services
#   status      Show status of all services
#   restart     Restart all services
#   qdrant      Manage Qdrant (setup/start/stop/status/logs/remove/destroy)
#   llama-swap  Manage llama-swap (setup/start/stop/status/logs/remove)
#   discord     Configure Discord/bot settings (channels, voice, debug)
#   deps        Install/reinstall Python dependencies
#   env         Reconfigure .env interactively
#   help        Show this help
set -euo pipefail

# ── Shell detection ─────────────────────────────────────────────────────────
# Detect the user's interactive shell (not the one running this script).
USER_SHELL="${SHELL##*/}"  # bash, fish, zsh, etc.
IS_FISH=false
if [[ "$USER_SHELL" == "fish" ]]; then
    IS_FISH=true
fi

GREEN=$'\033[0;32m';   YELLOW=$'\033[1;33m'
CYAN=$'\033[0;36m';    RED=$'\033[0;31m'
BOLD=$'\033[1m';       NC=$'\033[0m'

info()  { echo "${CYAN}==>${NC} $1"; }
ok()    { echo "${GREEN}  ✓${NC} $1"; }
warn()  { echo "${YELLOW}  ⚠${NC} $1"; }
err()   { echo "${RED}  ✘${NC} $1"; }
header(){ echo -e "\n${BOLD}── $1 ──${NC}\n"; }

# ── Shell-agnostic helpers for user-facing instructions ────────────────────
# When printing shell commands the user should run, use these so the
# output matches their interactive shell (bash, fish, zsh, ...).
set_var()      { echo "  ${BOLD}$1${NC} ${2:-}"; }   # generic env-var syntax
export_cmd()   { $IS_FISH && echo "set -gx $1 $2" || echo "export $1=$2"; }
source_cmd()   { $IS_FISH && echo "source $1"    || echo "source $1"; }
path_add_cmd() { $IS_FISH && echo "fish_add_path $1" || echo "export PATH=\$PATH:$1"; }
run_prefix()   { $IS_FISH && echo "fish -c '"    || echo ""; }  # no-op for bash

# ── Config ─────────────────────────────────────────────────────────────────
PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
STATE_FILE="$PROJECT_DIR/.setup_state"
ENV_FILE="$PROJECT_DIR/.env"
ENV_EXAMPLE="$PROJECT_DIR/.env.example"

QDRANT_CONTAINER="${QDRANT_CONTAINER_NAME:-serin-qdrant}"
QDRANT_IMAGE="${QDRANT_IMAGE:-qdrant/qdrant:latest}"
QDRANT_PORT="${QDRANT_PORT:-6333}"
QDRANT_VOLUME="${QDRANT_CONTAINER}_data"

LLAMA_SWAP_CONTAINER="llama-swap"
LLAMA_SWAP_PORT="${LLAMA_SWAP_PORT:-8080}"
LLAMA_SWAP_CONFIG_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/llama-swap"
LLAMA_SWAP_CONFIG="$LLAMA_SWAP_CONFIG_DIR/config.yaml"
LLAMA_SWAP_BINARY_URL="https://github.com/maximofn/llama-swap/releases/latest/download/llama-swap_linux_amd64.tar.gz"

# ── State ───────────────────────────────────────────────────────────────────
load_state() { [[ -f "$STATE_FILE" ]] && source "$STATE_FILE" || true; }
save_state() {
    local key="$1" val="$2"
    if grep -q "^${key}=" "$STATE_FILE" 2>/dev/null; then
        sed -i "s/^${key}=.*/${key}=${val}/" "$STATE_FILE"
    else
        echo "${key}=${val}" >> "$STATE_FILE"
    fi
}
init_state() { [[ -f "$STATE_FILE" ]] || touch "$STATE_FILE"; }

# ── Prompts ────────────────────────────────────────────────────────────────
ask() {
    local var="$1" prompt="$2" default="$3" current
    current=$(grep "^${var}=" "$STATE_FILE" 2>/dev/null | cut -d= -f2- || echo "")
    current="${current:-$default}"
    read -rp "  $prompt [$current]: " input </dev/tty
    echo "${input:-$current}"
}

ask_yn() {
    local var="$1" prompt="$2" default="${3:-y}"
    local cur
    cur=$(grep "^${var}=" "$STATE_FILE" 2>/dev/null | cut -d= -f2- || echo "${default}")
    local disp="Y/n"
    [[ "$default" == "n" ]] && disp="y/N"
    read -rp "  $prompt [$disp]: " input </dev/tty
    input="${input:-$cur}"
    case "$input" in
        [Yy]*) save_state "$var" "true"; return 0 ;;
        *)     save_state "$var" "false"; return 1 ;;
    esac
}

edit_env() {
    local var="$1" prompt="$2" default="$3"
    local current
    current=$(grep "^${var}=" "$ENV_FILE" 2>/dev/null | cut -d= -f2- || echo "")
    if [[ -z "$current" && -n "$default" ]]; then
        current="$default"
    fi
    read -rp "  $prompt [${current:-}]: " input </dev/tty
    echo "${input:-$current}"
}

# ── Docker helpers ─────────────────────────────────────────────────────────
_docker_available() { command -v docker &>/dev/null && docker info &>/dev/null 2>&1; }

_docker_container_running() {
    [[ "$(docker ps --filter "name=^/${1}$" --format '{{.Names}}' 2>/dev/null)" == "$1" ]]
}

_docker_container_exists() {
    [[ "$(docker ps -a --filter "name=^/${1}$" --format '{{.Names}}' 2>/dev/null)" == "$1" ]]
}

_wait_for_port() {
    local host="$1" port="$2" timeout="${3:-30}"
    info "Waiting for $host:$port..."
    for ((i=1; i<=timeout; i++)); do
        if curl -sf "http://${host}:${port}/health" >/dev/null 2>&1; then
            ok "Ready (${i}s)"
            return 0
        fi
        sleep 1
    done
    err "Not ready after ${timeout}s"
    return 1
}

# ============================================================================
# COMMANDS
# ============================================================================

# ── help ───────────────────────────────────────────────────────────────────
cmd_help() {
    sed -n '/^# Usage/,/^set -e/p' "$0" | head -n -1 | sed 's/^#//' | sed 's/^ //'
}

# ── deps ───────────────────────────────────────────────────────────────────
cmd_deps() {
    header "Python dependencies"
    if ! command -v uv &>/dev/null; then
        info "Installing uv..."
        curl -fsSL https://astral.sh/uv/install.sh | bash
        export PATH="$HOME/.local/bin:$PATH"
    fi
    ok "uv $(uv --version)"
    info "Syncing dependencies..."
    uv sync --frozen 2>/dev/null || uv sync
    ok "Dependencies installed"
    save_state "DEPS_INSTALLED" "true"
}

# ── env ────────────────────────────────────────────────────────────────────
cmd_env() {
    header "Environment configuration"
    if [[ ! -f "$ENV_FILE" ]]; then
        cp "$ENV_EXAMPLE" "$ENV_FILE" 2>/dev/null || touch "$ENV_FILE"
        ok "Created .env from .env.example"
    fi

    local tok
    tok=$(grep "^DISCORD_TOKEN=" "$ENV_FILE" 2>/dev/null | cut -d= -f2- || echo "")
    if [[ -z "$tok" || "$tok" == "your_discord_bot_token_here" ]]; then
        warn "DISCORD_TOKEN is required"
        read -rp "  Discord bot token: " tok </dev/tty
        if grep -q "^DISCORD_TOKEN=" "$ENV_FILE" 2>/dev/null; then
            sed -i "s/^DISCORD_TOKEN=.*/DISCORD_TOKEN=${tok}/" "$ENV_FILE"
        else
            echo "DISCORD_TOKEN=${tok}" >> "$ENV_FILE"
        fi
    fi

    local model
    model=$(recommend_llm)
    model=$(edit_env "LLM_MODEL" "LLM model" "$model")
    local url
    url=$(edit_env "LLM_BASE_URL" "llama-swap endpoint URL" "http://localhost:8080/v1")
    local vision
    vision=$(edit_env "LLM_SUPPORTS_VISION" "Supports vision? (true/false)" "false")
    local audio
    audio=$(edit_env "LLM_SUPPORTS_AUDIO" "Supports audio? (true/false)" "false")

    # Write clean .env
    {
        echo "DISCORD_TOKEN=${tok:-}"
        echo "LLM_MODEL=${model}"
        echo "LLM_BASE_URL=${url}"
        echo "LLM_SUPPORTS_VISION=${vision}"
        echo "LLM_SUPPORTS_AUDIO=${audio}"
        if [[ -n "$(grep '^QDRANT_USE_DOCKER=' "$ENV_FILE" 2>/dev/null || true)" ]]; then
            grep '^QDRANT_USE_DOCKER=' "$ENV_FILE"
        fi
    } > "$ENV_FILE.tmp" && mv "$ENV_FILE.tmp" "$ENV_FILE"
    ok ".env written"
}

# ── Hardware detection ─────────────────────────────────────────────────────
_detect_hardware() {
    GPU_NAME=""; GPU_VRAM=0; GPU_COUNT=0; HAS_CUDA=false
    if command -v nvidia-smi &>/dev/null; then
        local gpu_info
        gpu_info=$(nvidia-smi --query-gpu=name,memory.total --format=csv,noheader 2>/dev/null | head -1) || true
        if [[ -n "$gpu_info" ]]; then
            GPU_NAME=$(echo "$gpu_info" | cut -d, -f1 | xargs)
            local vram_raw
            vram_raw=$(echo "$gpu_info" | cut -d, -f2 | grep -oP '\d+') || vram_raw=0
            GPU_VRAM=$((vram_raw / 1024))
            GPU_COUNT=$(nvidia-smi --query-gpu=count --format=csv,noheader 2>/dev/null) || GPU_COUNT=0
            HAS_CUDA=true
        fi
    fi

    CPU_CORES=$(nproc)
    local ram_kb
    ram_kb=$(grep MemTotal /proc/meminfo 2>/dev/null | awk '{print $2}') || ram_kb=0
    RAM_GB=$((ram_kb / 1024 / 1024))
}

_recommend_llm() {
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

recommend_llm() { _detect_hardware; _recommend_llm; }

# Infer vision/audio capabilities from a model name
# Data sourced from ggml-org multimodal GGUF collection and llama.cpp docs.
# Returns: "vision=<true|false> audio=<true|false>"
_model_capabilities() {
    local model="$1"
    local model_lc
    model_lc=$(echo "$model" | tr '[:upper:]' '[:lower:]')
    local vision=false audio=false

    # ── Gemma 4: vision + audio (E2B, E4B, 12B) ────────────────────────────
    # Confirmed: google/gemma-4-E4B, ggml-org/gemma-4-E2B-it-GGUF
    # Audio support confirmed in llama.cpp (requires mmproj, still experimental)
    if echo "$model_lc" | grep -qE 'gemma-4'; then
        vision=true; audio=true
        echo "vision=$vision audio=$audio"
        return
    fi

    # ── Omni models: support BOTH vision and audio ───────────────────────────
    # Qwen2.5-Omni-7B, Qwen3-Omni-30B (confirmed by ggml-org collection)
    if echo "$model_lc" | grep -qE 'omni'; then
        vision=true; audio=true
        echo "vision=$vision audio=$audio"
        return
    fi

    # ── Audio-only models ───────────────────────────────────────────────────
    if echo "$model_lc" | grep -qE 'whisper|ultravox|speech'; then
        audio=true
    fi

    # ── Vision models (need separate mmproj.gguf file) ──────────────────────
    # All Qwen-VL / Qwen2-VL / Qwen2.5-VL / Qwen3-VL support vision
    # Confirmed: ggml-org/Qwen2.5-VL-{3B,7B,32B,72B}-Instruct-GGUF
    if echo "$model_lc" | grep -qE -- '-vl-'; then        vision=true; fi

    # Llama-3.2-11B-Vision-Instruct, MiniCPM-V-*, Pixtral-12B, SmolVLM
    if echo "$model_lc" | grep -qE 'vision|pixtral|smolvlm'; then
        vision=true
    fi

    # LLaVA, CogVLM, InternVL, MiniCPM-V (all confirmed vision models)
    if echo "$model_lc" | grep -qE 'llava|cogvlm|internvl|minicpm.*-v'; then
        vision=true
    fi

    # Gemma models: 4B / 12B / 27B support vision; 1B does NOT.
    # Catches: gemma12b, gemma-3-12b-it, gemma-4b-it, gemma-27b, etc.
    # Confirmed: ggml-org/gemma-3-{4b,12b,27b}-it-GGUF, google/gemma-4-E4B
    if echo "$model_lc" | grep -qE 'gemma.*(4b|12b|27b)'; then
        vision=true
    fi

    # GLM multimodal: GLM-4V, GLM-4.6V-Flash etc.
    if echo "$model_lc" | grep -qE 'glm.*4.*v|glm.*v[0-9]'; then
        vision=true
    fi

    echo "vision=$vision audio=$audio"
}

# Probe a running llama-swap endpoint for available model IDs
_probe_llm_models() {
    local base_url="${1:-http://localhost:8080/v1}"
    curl -sf "${base_url}/models" 2>/dev/null | python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
    for m in data.get('data', []):
        print(m.get('id', ''))
except:
    pass
" 2>/dev/null || true
}

# ── llama.cpp Docker auto-setup ─────────────────────────────────────────
# Detect the right Docker image for the user's hardware
_detect_llama_cpp_image() {
    if $HAS_CUDA && command -v nvidia-smi &>/dev/null; then
        echo "ghcr.io/ggml-org/llama.cpp:server-cuda"
    elif lspci 2>/dev/null | grep -qi 'amd\|radeon\|advanced micro'; then
        echo "rocm/llama.cpp:llama.cpp-b6652.amd0_rocm7.0.0_ubuntu24.04_server"
    else
        echo "ghcr.io/ggml-org/llama.cpp:server"
    fi
}

# Map a curated model ID → HuggingFace GGUF repo + quant for llama-server -hf
_model_to_gguf_repo() {
    local model="$1"
    case "$model" in
        *"Meta-Llama-3.1-8B"*)    echo "hugging-quants/Meta-Llama-3.1-8B-Instruct-GGUF:Q5_K_M";;
        *"Llama-3.2-3B"*)         echo "unsloth/Llama-3.2-3B-Instruct-GGUF:Q4_K_M";;
        *"Qwen2.5-7B-Instruct"*)  echo "ggml-org/Qwen2.5-7B-Instruct-GGUF:Q4_K_M";;
        *"Qwen2.5-1.5B"*)         echo "ggml-org/Qwen2.5-1.5B-Instruct-GGUF:Q4_K_M";;
        *"Qwen2.5-VL-7B"*)        echo "ggml-org/Qwen2.5-VL-7B-Instruct-GGUF:Q4_K_M";;
        *"Qwen2.5-Omni-7B"*)      echo "ggml-org/Qwen2.5-Omni-7B-GGUF:Q4_K_M";;
        *"gemma-3-12b"*)          echo "ggml-org/gemma-3-12b-it-GGUF:Q4_K_M";;
        *)                        echo "";;
    esac
}

# Pull the llama.cpp Docker image and save state
_setup_llama_cpp_docker() {
    local model="$1"
    local gguf_repo
    gguf_repo=$(_model_to_gguf_repo "$model")
    if [[ -z "$gguf_repo" ]]; then
        warn "No known GGUF repo for '$model' — skipping llama.cpp Docker setup"
        echo "  You can set up llama-server manually later."
        return 1
    fi

    local image
    image=$(_detect_llama_cpp_image)

    info "Pulling llama.cpp Docker image for your hardware..."
    echo "  Image: $image"
    echo "  Model: $gguf_repo"
    docker pull "$image" || {
        warn "Failed to pull $image — continuing without llama.cpp Docker"
        return 1
    }

    save_state "LLAMA_CPP_IMAGE" "$image"
    save_state "LLAMA_CPP_GGUF_REPO" "$gguf_repo"
    save_state "LLAMA_CPP_CONTAINER" "serin-llama-server"
    save_state "LLAMA_CPP_GPUS" "$HAS_CUDA"

    ok "llama.cpp Docker image ready"
    echo "  It will auto-download the model on first start (via -hf)"
    echo "  When you run 'bash setup.sh start', both containers spin up"
}

# Write model + capabilities into .env and print a summary
# Optionally override auto-detection with explicit vision/audio values.
_apply_model() {
    local model="$1" base_url="$2" force_vision="${3:-}" force_audio="${4:-}"
    [[ -z "$model" ]] && return

    local caps; caps=$(_model_capabilities "$model")
    local vision; vision=$(echo "$caps" | cut -d' ' -f1 | cut -d= -f2)
    local audio;  audio=$(echo "$caps" | cut -d' ' -f2 | cut -d= -f2)
    [[ -n "$force_vision" ]] && vision="$force_vision"
    [[ -n "$force_audio" ]] && audio="$force_audio"

    for keyval in "LLM_MODEL=$model" "LLM_BASE_URL=$base_url" "LLM_SUPPORTS_VISION=$vision" "LLM_SUPPORTS_AUDIO=$audio"; do
        local key="${keyval%%=*}" val="${keyval#*=}"
        if grep -q "^${key}=" "$ENV_FILE" 2>/dev/null; then
            sed -i "s|^${key}=.*|${key}=${val}|" "$ENV_FILE"
        else
            echo "${key}=${val}" >> "$ENV_FILE"
        fi
    done

    echo "  ${GREEN}✓${NC} Model: ${BOLD}$model${NC}"
    echo "  ${GREEN}✓${NC} Vision: ${BOLD}$vision${NC}  |  Audio: ${BOLD}$audio${NC}"
    if [[ "$vision" == "true" ]]; then
        echo "  ${YELLOW}ℹ${NC} Vision model needs a separate mmproj.gguf file with llama-server"
    else
        echo "  ${YELLOW}ℹ${NC} Model doesn't support vision — smolvlm will be used for images"
    fi
    if [[ "$audio" == "false" ]]; then
        echo "  ${YELLOW}ℹ${NC} Model doesn't support audio — whisper will transcribe first"
    fi
}

# Show list from a running endpoint and let the user pick
_select_model_from_endpoint() {
    local base_url="$1"
    local -a models=()
    while IFS= read -r m; do
        [[ -n "$m" ]] && models+=("$m")
    done < <(_probe_llm_models "$base_url")

    if [[ ${#models[@]} -eq 0 ]]; then
        warn "Endpoint returned no models"
        _enter_model_manually
        return
    fi

    echo "  Available models:"
    local i
    for i in "${!models[@]}"; do
        printf "    [%d] %s\n" $((i+1)) "${models[$i]}"
    done
    printf "    [%d] Enter custom model name\n" $((i+2))

    local choice
    read -rp "  Select model [1]: " choice </dev/tty
    choice="${choice:-1}"

    local selected
    if (( choice > 0 && choice <= ${#models[@]} )); then
        selected="${models[$((choice-1))]}"
    else
        read -rp "  Model name: " selected </dev/tty
    fi

    if [[ -n "$selected" ]]; then
        local v_default=false a_default=false
        _apply_model "$selected" "$base_url" "$v_default" "$a_default"

        echo ""
        echo "  Model capabilities default to false — override if needed."
        if ! ask_yn "MODEL_CAPS_OK" "  Vision = false, Audio = false — correct?" "y"; then
            local v_override a_override
            read -rp "  Supports vision? (true/false) [false]: " v_override </dev/tty
            v_override="${v_override:-false}"
            read -rp "  Supports audio? (true/false) [false]: " a_override </dev/tty
            a_override="${a_override:-false}"
            _apply_model "$selected" "$base_url" "$v_override" "$a_override"
        fi
    fi
}

# Prompt for model name manually (no endpoint available)
_enter_model_manually() {
    local base_url
    base_url=$(grep "^LLM_BASE_URL=" "$ENV_FILE" 2>/dev/null | cut -d= -f2- || echo "http://localhost:8080/v1")
    local current
    current=$(grep "^LLM_MODEL=" "$ENV_FILE" 2>/dev/null | cut -d= -f2- || echo "")

    echo "  Enter your model name (e.g. Qwen/Qwen2.5-7B-Instruct)"
    local model
    read -rp "  Model [${current:-}]: " model </dev/tty
    model="${model:-$current}"
    [[ -n "$model" ]] && _apply_model "$model" "$base_url" false false
}

# Minimal env phase for the wizard: only DISCORD_TOKEN
_cmd_env_minimal() {
    header "Environment configuration"
    if [[ ! -f "$ENV_FILE" ]]; then
        cp "$ENV_EXAMPLE" "$ENV_FILE" 2>/dev/null || touch "$ENV_FILE"
        ok "Created .env from .env.example"
    fi

    # LLM_BASE_URL
    local url
    url=$(grep "^LLM_BASE_URL=" "$ENV_FILE" 2>/dev/null | cut -d= -f2- || echo "")
    if [[ -z "$url" ]]; then
        url=$(edit_env "LLM_BASE_URL" "llama-swap endpoint URL" "http://localhost:8080/v1")
        echo "LLM_BASE_URL=${url}" >> "$ENV_FILE"
    fi

    # DISCORD_TOKEN
    local tok
    tok=$(grep "^DISCORD_TOKEN=" "$ENV_FILE" 2>/dev/null | cut -d= -f2- || echo "")
    if [[ -z "$tok" || "$tok" == "your_discord_bot_token_here" ]]; then
        warn "DISCORD_TOKEN is required"
        read -rp "  Discord bot token: " tok </dev/tty
        if grep -q "^DISCORD_TOKEN=" "$ENV_FILE" 2>/dev/null; then
            sed -i "s/^DISCORD_TOKEN=.*/DISCORD_TOKEN=${tok}/" "$ENV_FILE"
        else
            echo "DISCORD_TOKEN=${tok}" >> "$ENV_FILE"
        fi
    fi

    ok "Environment basics set"
}

# ── Discord / Bot configuration phase ─────────────────────────────────────
_setup_discord_config() {
    header "Discord / Bot configuration"

    local key val edited=false

    for key in ALLOWED_CHANNEL_IDS ENABLE_VOICE ENABLE_TTS VOICE_RECEIVER_MODE CONTROL_PANEL_PORT CONTROL_PANEL_KEY DEBUG_MODE TRACE_MESSAGES; do
        val=$(grep "^${key}=" "$ENV_FILE" 2>/dev/null | cut -d= -f2- || echo "")
        if [[ -n "$val" ]]; then
            case "$key" in
                ENABLE_VOICE|ENABLE_TTS|DEBUG_MODE|TRACE_MESSAGES)
                    local norm="${val,,}"
                    case "$norm" in
                        true|false) echo "  ${GREEN}✓${NC} $key = $val"; continue;;
                        yes|y|on|1) _write_env "$key" "true"; edited=true; continue;;
                        *) _write_env "$key" "false"; edited=true; continue;;
                    esac
                    ;;
                VOICE_RECEIVER_MODE)
                    if [[ "$val" == "rust" || "$val" == "pycord" ]]; then
                        echo "  ${GREEN}✓${NC} $key = $val"; continue
                    fi
                    _write_env "VOICE_RECEIVER_MODE" "rust"; edited=true; continue
                    ;;
                *)
                    echo "  ${GREEN}✓${NC} $key = $val"; continue
                    ;;
            esac
        fi
        case "$key" in
            ENABLE_VOICE)
                if ask_yn "ENABLE_VOICE" "Enable voice (join voice channels)?" "y"; then
                    _write_env "ENABLE_VOICE" "true"; edited=true
                else
                    _write_env "ENABLE_VOICE" "false"; edited=true
                fi
                ;;
            ENABLE_TTS)
                if ask_yn "ENABLE_TTS" "Enable text-to-speech?" "y"; then
                    _write_env "ENABLE_TTS" "true"; edited=true
                else
                    _write_env "ENABLE_TTS" "false"; edited=true
                fi
                ;;
            VOICE_RECEIVER_MODE)
                echo "  Voice receiver mode:"
                echo "    [1] rust (DAVE-compatible, default)"
                echo "    [2] pycord (AudioSink, simpler)"
                local choice
                read -rp "  Choice [1]: " choice </dev/tty
                choice="${choice:-1}"
                if [[ "$choice" == "2" ]]; then
                    _write_env "VOICE_RECEIVER_MODE" "pycord"; edited=true
                else
                    _write_env "VOICE_RECEIVER_MODE" "rust"; edited=true
                fi
                ;;
            DEBUG_MODE)
                if ask_yn "DEBUG_MODE" "Enable debug mode?" "y"; then
                    _write_env "DEBUG_MODE" "true"; edited=true
                else
                    _write_env "DEBUG_MODE" "false"; edited=true
                fi
                ;;
            TRACE_MESSAGES)
                if ask_yn "TRACE_MESSAGES" "Log all message content?" "y"; then
                    _write_env "TRACE_MESSAGES" "true"; edited=true
                else
                    _write_env "TRACE_MESSAGES" "false"; edited=true
                fi
                ;;
            ALLOWED_CHANNEL_IDS)
                echo "  Comma-separated Discord channel IDs:"
                while true; do
                    read -rp "  (e.g. 123456789,987654321): " val </dev/tty
                    if [[ -z "$val" ]]; then
                        break
                    fi
                    if echo "$val" | grep -qE '^[0-9]+(,[0-9]+)*$'; then
                        _write_env "ALLOWED_CHANNEL_IDS" "$val"; edited=true
                        break
                    else
                        warn "Invalid — enter numbers only, comma-separated"
                    fi
                done
                ;;
            CONTROL_PANEL_PORT)
                echo "  Control panel port [8081]:"
                read -rp "  Port: " val </dev/tty
                val="${val:-8081}"
                _write_env "CONTROL_PANEL_PORT" "$val"; edited=true
                ;;
            CONTROL_PANEL_KEY)
                echo "  Auth key for control panel (empty = no auth):"
                read -rp "  Key: " val </dev/tty
                _write_env "CONTROL_PANEL_KEY" "$val"; edited=true
                ;;
        esac
    done

    if ask_yn "RECONFIGURE_DISCORD" "Reconfigure any setting?" "n"; then
            echo "  Select which to reconfigure:"
            local -a klist=(ALLOWED_CHANNEL_IDS ENABLE_VOICE ENABLE_TTS VOICE_RECEIVER_MODE CONTROL_PANEL_PORT CONTROL_PANEL_KEY DEBUG_MODE TRACE_MESSAGES)
            for i in "${!klist[@]}"; do
                printf "    [%d] %s\n" $((i+1)) "${klist[$i]}"
            done
            echo ""
            read -rp "  Choice: " choice </dev/tty
            if (( choice > 0 && choice <= ${#klist[@]} )); then
                key="${klist[$((choice-1))]}"
                # Re-run the same case logic for that key
                val=""
                case "$key" in
                    ENABLE_VOICE) ask_yn "ENABLE_VOICE" "Enable voice?" "y" && _write_env "ENABLE_VOICE" "true" || _write_env "ENABLE_VOICE" "false";;
                    ENABLE_TTS) ask_yn "ENABLE_TTS" "Enable TTS?" "y" && _write_env "ENABLE_TTS" "true" || _write_env "ENABLE_TTS" "false";;
                    VOICE_RECEIVER_MODE) echo "  [1] rust  [2] pycord"; read -rp "  Choice [1]: " c; c="${c:-1}"; _write_env "VOICE_RECEIVER_MODE" "$([[ $c == 2 ]] && echo pycord || echo rust)";;
                    DEBUG_MODE) ask_yn "DEBUG_MODE" "Enable debug?" "y" && _write_env "DEBUG_MODE" "true" || _write_env "DEBUG_MODE" "false";;
                    TRACE_MESSAGES) ask_yn "TRACE_MESSAGES" "Trace messages?" "y" && _write_env "TRACE_MESSAGES" "true" || _write_env "TRACE_MESSAGES" "false";;
                    ALLOWED_CHANNEL_IDS) while true; do read -rp "  Channel IDs: " val </dev/tty; [[ -z "$val" ]] && break; echo "$val" | grep -qE '^[0-9]+(,[0-9]+)*$' && { _write_env "ALLOWED_CHANNEL_IDS" "$val"; break; } || warn "Invalid — numbers only, comma-separated"; done;;
                    CONTROL_PANEL_PORT) read -rp "  Port [8081]: " val; _write_env "CONTROL_PANEL_PORT" "${val:-8081}";;
                    CONTROL_PANEL_KEY) read -rp "  Key: " val; _write_env "CONTROL_PANEL_KEY" "$val";;
                esac
            fi
        fi
    ok "Discord config done"
}

# Write a key=value to .env (add or replace)
_write_env() {
    local key="$1" val="$2"
    if grep -q "^${key}=" "$ENV_FILE" 2>/dev/null; then
        sed -i "s|^${key}=.*|${key}=${val}|" "$ENV_FILE"
    else
        echo "${key}=${val}" >> "$ENV_FILE"
    fi
    ok "${key}=${val}"
}

# ── setup ──────────────────────────────────────────────────────────────────
cmd_setup() {
    clear
    echo ""
    echo "  ┌──────────────────────────────────────────────────┐"
    echo "  │  Serin Setup Wizard                              │"
    echo "  │  One-time, resumable, remembers your choices     │"
    echo "  └──────────────────────────────────────────────────┘"
    echo ""
    init_state; load_state

    # Check if resuming
    if [[ "$(grep "^SETUP_COMPLETE=" "$STATE_FILE" 2>/dev/null | cut -d= -f2- || echo "false")" == "true" ]]; then
        header "Resuming previous setup"
        echo "  What would you like to change?"
        echo "    [1] Re-detect hardware"
        echo "    [2] Reconfigure .env"
        echo "    [3] Reinstall llama-swap"
        echo "    [4] Reconfigure Qdrant"
        echo "    [5] Reconfigure Discord/bot settings"
        echo "    [6] Full redo"
        echo "    [7] Nothing — exit"
        echo ""
        local change
        read -rp "  Choice [7]: " change </dev/tty
        change="${change:-7}"
        case "$change" in
            1) _detect_hardware;;
            2) cmd_env;;
            3) _setup_llama_swap;;
            4) _setup_qdrant;;
            5) _setup_discord_config;;
            6) rm -f "$STATE_FILE"; exec "$0" setup;;
            7) info "Nothing changed."; exit 0;;
        esac
        save_state "SETUP_COMPLETE" "true"
        ok "Updated"
        exit 0
    fi

    # Phase 1: hardware detection
    header "Detecting hardware"
    ok "Shell: $USER_SHELL ($(export_cmd SHELL "$(which $USER_SHELL 2>/dev/null || echo "$SHELL")" 2>/dev/null))"
    _detect_hardware
    if $HAS_CUDA; then
        ok "GPU: $GPU_NAME  |  VRAM: ${GPU_VRAM}GB  |  Count: $GPU_COUNT"
    else
        warn "No NVIDIA GPU — will use CPU or remote API"
    fi
    ok "CPU: ${CPU_CORES} cores  |  RAM: ${RAM_GB}GB"
    save_state "HAS_CUDA" "$HAS_CUDA"
    save_state "GPU_VRAM" "$GPU_VRAM"

    # Phase 2: Python deps
    cmd_deps

    # Phase 3: .env basics (token + endpoint URL; model is set in the LLM phase)
    _cmd_env_minimal

    # Phase 4: Qdrant — install, connect, verify, retry on failure
    local qdrant_retries=0
    while true; do
        if curl -sf "http://localhost:${QDRANT_PORT}/health" >/dev/null 2>&1; then
            ok "Qdrant running on http://localhost:${QDRANT_PORT}"
            break
        fi
        if ask_yn "SETUP_QDRANT" "Qdrant is not running. Set it up?" "y"; then
            if _setup_qdrant; then
                if curl -sf "http://localhost:${QDRANT_PORT}/health" >/dev/null 2>&1; then
                    ok "Qdrant setup complete and verified"
                    break
                fi
                warn "Qdrant started but health check failed"
            else
                warn "Qdrant setup failed"
            fi

            ((qdrant_retries++))
            if (( qdrant_retries >= 2 )); then
                echo ""
                warn "Multiple attempts failed — the container may be broken."
                if ask_yn "RECREATE_QDRANT" "Remove and recreate the Qdrant container?" "y"; then
                    docker rm -f "$QDRANT_CONTAINER" 2>/dev/null || true
                    docker rm -f "$(docker ps -a --filter "ancestor=$QDRANT_IMAGE" --format "{{.Names}}" 2>/dev/null | head -1)" 2>/dev/null || true
                    continue
                fi
            fi

            if ! ask_yn "RETRY_QDRANT" "Try again?" "y"; then
                warn "Skipping Qdrant — memory features won't work"
                break
            fi
        else
            warn "Skipping Qdrant — memory features won't work"
            break
        fi
    done

    # Phase 5: LLM backend — probe, install, verify, retry on failure
    while true; do
        local base_url
        base_url=$(grep "^LLM_BASE_URL=" "$ENV_FILE" 2>/dev/null | cut -d= -f2- || echo "http://localhost:8080/v1")
        _setup_llama_swap
        if curl -sf "${base_url}/models" >/dev/null 2>&1; then
            ok "LLM endpoint verified at $base_url"
            break
        fi
        warn "LLM endpoint still not responding — run 'bash setup.sh start' first"
        if ! ask_yn "RETRY_LLM" "Check again?" "y"; then
            warn "Skipping LLM — bot won't generate responses"
            break
        fi
    done

    # Phase 6: Discord / Bot configuration (only prompts for missing env vars)
    _setup_discord_config

    save_state "SETUP_COMPLETE" "true"
    save_state "SETUP_DATE" "$(date +%Y-%m-%d)"

    header "Done"
    echo "  Start all services:  ${BOLD}bash setup.sh start${NC}"
    echo "  Run the bot:         ${BOLD}uv run python -m serin${NC}"
    if $IS_FISH; then
        echo ""
        echo "  ${YELLOW}Fish shell detected${NC}"
        echo "  Add to your config.fish if needed:"
        echo "    $(export_cmd PATH \"\$HOME/.local/bin:\$PATH\")"
    fi
    echo ""
    ok "Setup complete"
}

# ── llama-swap ─────────────────────────────────────────────────────────────
_setup_llama_swap() {
    header "LLM backend — llama-swap"
    _detect_hardware
    local rec_model; rec_model=$(_recommend_llm)
    local base_url
    base_url=$(grep "^LLM_BASE_URL=" "$ENV_FILE" 2>/dev/null | cut -d= -f2- || echo "http://localhost:8080/v1")

    echo "  Hardware: ${GPU_NAME:-CPU} (${GPU_VRAM:-0}GB) / ${CPU_CORES}C / ${RAM_GB}GB"
    echo ""

    # 1 — Try to probe a running endpoint
    if curl -sf "${base_url}/models" >/dev/null 2>&1; then
        ok "llama-swap endpoint detected at $base_url"
        _select_model_from_endpoint "$base_url"
        return 0
    fi

    # 2 — Not running; ask whether to set up
    echo "  No LLM endpoint found at $base_url"
    echo ""
    if _docker_available; then
        echo "  How would you like to run llama-swap?"
        echo "    [1] Docker (recommended) — pull image, select a model"
        echo "    [2] Binary download"
        echo "    [3] Skip — I'll run it myself"
        echo ""
        local choice
        read -rp "  Choice [1]: " choice </dev/tty
        choice="${choice:-1}"
        case "$choice" in
            1) _setup_llama_swap_docker "$rec_model"; save_state "LLAMA_SWAP_METHOD" "docker";;
            2) _install_llama_swap_binary; _enter_model_manually; save_state "LLAMA_SWAP_METHOD" "binary";;
            3) save_state "LLAMA_SWAP_METHOD" "manual"; _enter_model_manually;;
        esac
    else
        echo "  Docker not available — installing binary"
        _install_llama_swap_binary
        _enter_model_manually
        save_state "LLAMA_SWAP_METHOD" "binary"
    fi
}

_setup_llama_swap_docker() {
    local rec_model="${1:-}"

    info "Pulling llama-swap Docker image..."
    docker pull ghcr.io/maximofn/llama-swap:latest

    local base_url
    base_url=$(grep "^LLM_BASE_URL=" "$ENV_FILE" 2>/dev/null | cut -d= -f2- || echo "http://localhost:8080/v1")

    echo ""
    echo "  Select a model for your hardware:"
    echo ""

    # VRAM-based menu
    if $HAS_CUDA && (( GPU_VRAM >= 20 )); then
        echo "    ${BOLD}Recommended:${NC} Llama 3.1 8B (Q5_K_M) — solid all-rounder (20GB+ VRAM)"
        echo "    [1] hugging-quants/Meta-Llama-3.1-8B-Instruct-GPTQ-INT4"
        echo "    [2] Qwen/Qwen2.5-7B-Instruct (Q4_K_M)"
        echo "    [3] Qwen/Qwen2.5-VL-7B-Instruct (Q4_K_M, vision, needs mmproj)"
        echo "    [4] google/gemma-3-12b-it (Q4_K_M, vision, needs mmproj)"
        echo "    [5] Qwen/Qwen2.5-Omni-7B (Q4_K_M, vision + audio)"
        echo "    [6] Enter custom model name"
        echo ""
        local choice
        read -rp "  Choice [1]: " choice </dev/tty
        choice="${choice:-1}"
        case "$choice" in
            1) model="hugging-quants/Meta-Llama-3.1-8B-Instruct-GPTQ-INT4";;
            2) model="Qwen/Qwen2.5-7B-Instruct";;
            3) model="Qwen/Qwen2.5-VL-7B-Instruct";;
            4) model="google/gemma-3-12b-it";;
            5) model="Qwen/Qwen2.5-Omni-7B";;
            6) read -rp "  Model name: " model </dev/tty;;
        esac
    elif $HAS_CUDA && (( GPU_VRAM >= 10 )); then
        echo "    ${BOLD}Recommended:${NC} Llama 3.2 3B (Q4_K_M) — fits 10-12GB VRAM"
        echo "    [1] ModelCloud/Llama-3.2-3B-Instruct-gptqmodel-4bit-vortex-v3"
        echo "    [2] Qwen/Qwen2.5-1.5B-Instruct (Q4_K_M)"
        echo "    [3] Qwen/Qwen2.5-VL-7B-Instruct (Q4_K_M, vision, needs mmproj)"
        echo "    [4] Qwen/Qwen2.5-Omni-7B (Q4_K_M, vision + audio)"
        echo "    [5] Enter custom model name"
        echo ""
        local choice
        read -rp "  Choice [1]: " choice </dev/tty
        choice="${choice:-1}"
        case "$choice" in
            1) model="ModelCloud/Llama-3.2-3B-Instruct-gptqmodel-4bit-vortex-v3";;
            2) model="Qwen/Qwen2.5-1.5B-Instruct";;
            3) model="Qwen/Qwen2.5-VL-7B-Instruct";;
            4) model="Qwen/Qwen2.5-Omni-7B";;
            5) read -rp "  Model name: " model </dev/tty;;
        esac
    else
        echo "    ${BOLD}Recommended:${NC} Qwen2.5-1.5B-Instruct (Q4_K_M) — CPU / low-VRAM"
        echo "    [1] Qwen/Qwen2.5-1.5B-Instruct"
        echo "    [2] ModelCloud/Llama-3.2-3B-Instruct-gptqmodel-4bit-vortex-v3"
        echo "    [3] Enter custom model name"
        echo ""
        local choice
        read -rp "  Choice [1]: " choice </dev/tty
        choice="${choice:-1}"
        case "$choice" in
            1) model="Qwen/Qwen2.5-1.5B-Instruct";;
            2) model="ModelCloud/Llama-3.2-3B-Instruct-gptqmodel-4bit-vortex-v3";;
            3) read -rp "  Model name: " model </dev/tty;;
        esac
    fi

    model="${model:-$rec_model}"
    if [[ -n "$model" ]]; then
        _apply_model "$model" "$base_url"
        _write_llama_swap_config
        # Auto-setup llama.cpp Docker backend for curated models
        _setup_llama_cpp_docker "$model" || true
    fi
    ok "llama-swap Docker image ready"
}

_install_llama_swap_binary() {
    local tmp
    tmp=$(mktemp -d)
    info "Downloading llama-swap binary..."
    if curl -fsSL "$LLAMA_SWAP_BINARY_URL" -o "$tmp/llama-swap.tar.gz" && \
       tar xzf "$tmp/llama-swap.tar.gz" -C "$tmp" && \
       install "$tmp/llama-swap" /usr/local/bin/llama-swap 2>/dev/null || \
       install "$tmp/llama-swap" "$HOME/.local/bin/llama-swap"; then
         _write_llama_swap_config
        ok "llama-swap installed to $(command -v llama-swap)"
        # Ask if they also want a Docker llama.cpp backend
        echo ""
        if ask_yn "SETUP_LLAMA_CPP" "Set up a Docker-based llama-server backend too?" "y"; then
            local model
            model=$(grep "^LLM_MODEL=" "$ENV_FILE" 2>/dev/null | cut -d= -f2- || echo "")
            if [[ -n "$model" ]]; then
                _setup_llama_cpp_docker "$model" || true
            else
                warn "No model configured — skipping llama.cpp Docker setup"
            fi
        fi
    else
        err "Binary download failed"
    fi
    rm -rf "$tmp"
}

_write_llama_swap_config() {
    mkdir -p "$LLAMA_SWAP_CONFIG_DIR"
    if [[ ! -f "$LLAMA_SWAP_CONFIG" ]]; then
        local model
        model=$(grep "^LLM_MODEL=" "$ENV_FILE" 2>/dev/null | cut -d= -f2- || echo "Qwen/Qwen2.5-7B-Instruct")
        cat > "$LLAMA_SWAP_CONFIG" <<- LLMAC
host: 0.0.0.0
port: ${LLAMA_SWAP_PORT}
backends:
  - name: default
    type: vllm
    model: ${model}
    url: http://localhost:8000/v1
    api_key: unused
LLMAC
        ok "llama-swap config written to $LLAMA_SWAP_CONFIG"
    fi
}

_start_llama_swap() {
    header "Starting llama-swap"

    # First, start the llama-server Docker container if configured
    local llm_image llm_repo llm_container llm_gpus
    llm_image=$(grep "^LLAMA_CPP_IMAGE=" "$STATE_FILE" 2>/dev/null | cut -d= -f2- || echo "")
    llm_repo=$(grep "^LLAMA_CPP_GGUF_REPO=" "$STATE_FILE" 2>/dev/null | cut -d= -f2- || echo "")
    llm_container=$(grep "^LLAMA_CPP_CONTAINER=" "$STATE_FILE" 2>/dev/null | cut -d= -f2- || echo "serin-llama-server")
    llm_gpus=$(grep "^LLAMA_CPP_GPUS=" "$STATE_FILE" 2>/dev/null | cut -d= -f2- || echo "false")

    if [[ -n "$llm_image" && -n "$llm_repo" ]]; then
        if _docker_container_running "$llm_container"; then
            ok "llama-server already running"
        else
            if _docker_container_exists "$llm_container"; then
                info "Starting llama-server..."
                docker start "$llm_container" 2>/dev/null || {
                    docker rm "$llm_container" 2>/dev/null
                    _create_llama_server_container "$llm_image" "$llm_repo" "$llm_container" "$llm_gpus"
                }
            else
                _create_llama_server_container "$llm_image" "$llm_repo" "$llm_container" "$llm_gpus"
            fi
            _wait_for_port "localhost" 8000 120
        fi
    fi

    # Then start llama-swap
    local method
    method=$(grep "^LLAMA_SWAP_METHOD=" "$STATE_FILE" 2>/dev/null | cut -d= -f2- || echo "docker")

    if [[ "$method" == "docker" ]]; then
        if _docker_container_running "$LLAMA_SWAP_CONTAINER"; then
            ok "llama-swap already running"
            return 0
        fi
        if ! _docker_container_exists "$LLAMA_SWAP_CONTAINER"; then
            warn "llama-swap container doesn't exist — run 'bash setup.sh llama-swap setup' first"
            return 1
        fi
        info "Starting llama-swap container..."
        docker start "$LLAMA_SWAP_CONTAINER"
        _wait_for_port "localhost" "$LLAMA_SWAP_PORT" 30
        ok "llama-swap running on http://localhost:$LLAMA_SWAP_PORT"
    elif [[ "$method" == "binary" ]]; then
        if command -v llama-swap &>/dev/null; then
            nohup llama-swap --config "$LLAMA_SWAP_CONFIG" > /tmp/llama-swap.log 2>&1 &
            ok "llama-swap started (PID $!) — logs: /tmp/llama-swap.log"
        else
            err "llama-swap binary not found"
        fi
    else
        warn "llama-swap not configured — run 'bash setup.sh setup' to configure"
    fi
}

_create_llama_server_container() {
    local image="$1" repo="$2" container="$3" has_gpu="$4"
    local gpu_flag=""
    [[ "$has_gpu" == "true" ]] && gpu_flag="--gpus all"
    info "Creating llama-server container ($container)..."
    docker run -d \
        --name "$container" \
        --restart unless-stopped \
        $gpu_flag \
        -p 8000:8080 \
        -v "${container}_models:/models" \
        -v "${container}_hf:/root/.cache/huggingface" \
        "$image" \
        -hf "$repo" --port 8080 -ngl 99
}

_stop_llama_swap() {
    header "Stopping services"

    # Stop llama-server first
    local llm_container
    llm_container=$(grep "^LLAMA_CPP_CONTAINER=" "$STATE_FILE" 2>/dev/null | cut -d= -f2- || echo "serin-llama-server")
    if _docker_container_running "$llm_container"; then
        info "Stopping llama-server..."
        docker stop "$llm_container"
        ok "llama-server stopped"
    fi

    # Then stop llama-swap
    if _docker_container_running "$LLAMA_SWAP_CONTAINER"; then
        info "Stopping llama-swap..."
        docker stop "$LLAMA_SWAP_CONTAINER"
        ok "llama-swap stopped"
    elif command -v pkill &>/dev/null && pkill -f "llama-swap" 2>/dev/null; then
        ok "llama-swap (binary) stopped"
    else
        warn "llama-swap not running"
    fi
}

_status_llama_swap() {
    local ls_status=0

    # Check llama-server
    local llm_container
    llm_container=$(grep "^LLAMA_CPP_CONTAINER=" "$STATE_FILE" 2>/dev/null | cut -d= -f2- || echo "")
    if [[ -n "$llm_container" ]]; then
        if _docker_container_running "$llm_container"; then
            ok "llama-server: running (port 8000)"
        elif _docker_container_exists "$llm_container"; then
            warn "llama-server: stopped"
            ls_status=1
        fi
    fi

    # Check llama-swap
    if _docker_container_running "$LLAMA_SWAP_CONTAINER"; then
        ok "llama-swap (Docker): running"
    elif command -v pgrep &>/dev/null && pgrep -f "llama-swap" >/dev/null 2>&1; then
        ok "llama-swap (binary): running"
    elif _docker_container_exists "$LLAMA_SWAP_CONTAINER"; then
        warn "llama-swap (Docker): stopped"
        ls_status=1
    else
        warn "llama-swap: not configured"
        ls_status=1
    fi
    return $ls_status
}

# ── Qdrant ─────────────────────────────────────────────────────────────────
_setup_qdrant() {
    header "Qdrant (vector database)"
    if ! _docker_available; then
        err "Docker is required for Qdrant. Install Docker first."
        return 1
    fi

    # Check if something is already listening on the port
    if curl -sf "http://localhost:${QDRANT_PORT}/health" >/dev/null 2>&1; then
        ok "Qdrant already running on port ${QDRANT_PORT}"
        _write_qdrant_env
        return 0
    fi

    # Check for any existing Qdrant container
    local existing
    existing=$(docker ps -a --filter "ancestor=$QDRANT_IMAGE" --format "{{.Names}}" 2>/dev/null | head -1)
    if [[ -z "$existing" ]]; then
        existing=$(docker ps -a --format "{{.Names}}\t{{.Image}}" 2>/dev/null | awk -F'\t' '/qdrant/ {print $1; exit}')
    fi

    if [[ -n "$existing" ]]; then
        info "Found existing Qdrant container: $existing"
        if _docker_container_running "$existing"; then
            info "Container already running — waiting for health endpoint..."
        else
            docker start "$existing"
        fi
        if ! _wait_for_port "localhost" "$QDRANT_PORT" 60; then
            _diagnose_container "$existing"
            return 1
        fi
        _write_qdrant_env
        ok "Qdrant ready (container: $existing)"
        return 0
    fi

    # Check if port is already bound by a non-Qdrant container
    if command -v ss &>/dev/null; then
        if ss -tlnp | grep -q ":${QDRANT_PORT} "; then
            warn "Port ${QDRANT_PORT} is already in use by another process"
            echo "  Something else is using port ${QDRANT_PORT}. Free it or set QDRANT_PORT in .env"
            return 1
        fi
    fi

    info "Pulling Qdrant image..."
    docker pull "$QDRANT_IMAGE" || { err "Failed to pull Qdrant image"; return 1; }
    info "Creating Docker volume..."
    docker volume create "$QDRANT_VOLUME" 2>/dev/null || true
    info "Starting Qdrant container..."
    docker run -d \
        --name "$QDRANT_CONTAINER" \
        --restart unless-stopped \
        -p "$QDRANT_PORT:6333" \
        -p "6334:6334" \
        -v "${QDRANT_VOLUME}:/qdrant/storage" \
        --health-cmd "curl -sf http://localhost:6333/health || exit 1" \
        --health-interval 30s --health-timeout 5s --health-retries 3 \
        "$QDRANT_IMAGE" || { err "Failed to start Qdrant container"; return 1; }

    if ! _wait_for_port "localhost" "$QDRANT_PORT" 60; then
        _diagnose_container "$QDRANT_CONTAINER"
        return 1
    fi
    _write_qdrant_env
    ok "Qdrant ready"
}

# Print diagnostics for a failing container
_diagnose_container() {
    local name="$1"
    warn "Container diagnostics for '$name':"
    echo "  Status: $(docker inspect "$name" --format '{{.State.Status}}' 2>/dev/null || echo 'unknown')"
    local health; health=$(docker inspect "$name" --format '{{.State.Health.Status}}' 2>/dev/null || echo 'unknown')
    echo "  Health: $health"
    echo "  Ports: $(docker port "$name" 2>/dev/null | tr '\n' ' ' || echo 'unknown')"
    echo "  Recent logs (last 5 lines):"
    docker logs --tail 5 "$name" 2>&1 | sed 's/^/    /'
}

_write_qdrant_env() {
    if ! grep -q "^QDRANT_USE_DOCKER=" "$ENV_FILE" 2>/dev/null; then
        echo "" >> "$ENV_FILE"
        echo "# Qdrant auto-managed via Docker" >> "$ENV_FILE"
        echo "QDRANT_USE_DOCKER=true" >> "$ENV_FILE"
    fi
    ok "QDRANT_USE_DOCKER=true set in .env"
}

_start_qdrant() {
    header "Starting Qdrant"
    if ! _docker_available; then
        err "Docker not available"
        return 1
    fi
    if curl -sf "http://localhost:${QDRANT_PORT}/health" >/dev/null 2>&1; then
        ok "Qdrant already running on port ${QDRANT_PORT}"
        return 0
    fi
    if _docker_container_running "$QDRANT_CONTAINER"; then
        ok "Qdrant already running"
        return 0
    fi
    if _docker_container_exists "$QDRANT_CONTAINER"; then
        info "Starting Qdrant..."
        docker start "$QDRANT_CONTAINER"
    else
        # Search for any Qdrant container
        local existing
        existing=$(docker ps -a --filter "ancestor=$QDRANT_IMAGE" --format "{{.Names}}" 2>/dev/null | head -1)
        if [[ -z "$existing" ]]; then
            existing=$(docker ps -a --format "{{.Names}}\t{{.Image}}" 2>/dev/null | awk -F'\t' '/qdrant/ {print $1; exit}')
        fi
        if [[ -n "$existing" ]]; then
            info "Starting existing Qdrant container: $existing"
            docker start "$existing"
        else
            warn "No Qdrant container found — run 'bash setup.sh qdrant setup' first"
            return 1
        fi
    fi
    _wait_for_port "localhost" "$QDRANT_PORT" 30
    ok "Qdrant running on http://localhost:$QDRANT_PORT"
}

_stop_qdrant() {
    header "Stopping Qdrant"
    if _docker_container_running "$QDRANT_CONTAINER"; then
        docker stop "$QDRANT_CONTAINER"
        ok "Stopped"
    else
        warn "Not running"
    fi
}

_status_qdrant() {
    if _docker_container_running "$QDRANT_CONTAINER"; then
        ok "Qdrant: running (http://localhost:$QDRANT_PORT)"
        return 0
    elif _docker_container_exists "$QDRANT_CONTAINER"; then
        warn "Qdrant: stopped"
    else
        warn "Qdrant: not configured"
    fi
    return 1
}

_logs_qdrant() {
    if _docker_container_exists "$QDRANT_CONTAINER"; then
        docker logs -f "$QDRANT_CONTAINER"
    else
        err "Qdrant container not found"
    fi
}

_remove_qdrant() {
    warn "Removing Qdrant container (data volume preserved)"
    docker stop "$QDRANT_CONTAINER" 2>/dev/null || true
    docker rm "$QDRANT_CONTAINER" 2>/dev/null || true
    ok "Container removed. Volume '$QDRANT_VOLUME' preserved"
}

_destroy_qdrant() {
    warn "DESTROYING Qdrant container AND volume — all data lost!"
    read -rp "  Type 'yes' to confirm: " confirm </dev/tty
    if [[ "$confirm" != "yes" ]]; then
        info "Cancelled"; return
    fi
    docker stop "$QDRANT_CONTAINER" 2>/dev/null || true
    docker rm "$QDRANT_CONTAINER" 2>/dev/null || true
    docker volume rm "$QDRANT_VOLUME" 2>/dev/null || true
    ok "Destroyed"
}

# ── qdrant subcommand dispatcher ──────────────────────────────────────────
cmd_qdrant() {
    local sub="${1:-setup}"
    shift 2>/dev/null || true
    case "$sub" in
        setup)   _setup_qdrant || return $?;;
        start)   _start_qdrant || return $?;;
        stop)    _stop_qdrant || true;;
        status)  _status_qdrant || true;;
        restart) _stop_qdrant || true; _start_qdrant || return $?;;
        logs)    _logs_qdrant || true;;
        remove)  _remove_qdrant || true;;
        destroy) _destroy_qdrant || true;;
        *)       err "Usage: bash setup.sh qdrant {setup|start|stop|status|restart|logs|remove|destroy}"; return 1;;
    esac
}

cmd_llama_swap() {
    local sub="${1:-setup}"
    shift 2>/dev/null || true
    case "$sub" in
        setup)   _setup_llama_swap || return $?;;
        start)   _start_llama_swap || return $?;;
        stop)    _stop_llama_swap || true;;
        status)  _status_llama_swap || true;;
        restart) _stop_llama_swap || true; _start_llama_swap || return $?;;
        logs)    docker logs -f "$LLAMA_SWAP_CONTAINER" 2>/dev/null || { err "Not found"; return 1; };;
        *)       err "Usage: bash setup.sh llama-swap {setup|start|stop|status|restart|logs}"; return 1;;
    esac
}

# ── start / stop / status / restart ───────────────────────────────────────
cmd_start() {
    _start_qdrant || true
    _start_llama_swap || true
    header "All services started"
    echo "  Qdrant:    http://localhost:$QDRANT_PORT"
    echo "  llama-swap: http://localhost:$LLAMA_SWAP_PORT/v1"
    echo ""
    echo "  Run the bot:  uv run python -m serin"
}

cmd_stop() {
    _stop_llama_swap || true
    _stop_qdrant || true
    ok "All services stopped"
}

cmd_status() {
    header "Service status"
    _status_qdrant || true
    _status_llama_swap || true
    echo ""
    if [[ -f "$ENV_FILE" ]]; then
        local tok
        tok=$(grep "^DISCORD_TOKEN=" "$ENV_FILE" 2>/dev/null | cut -d= -f2- || echo "(not set)")
        [[ "$tok" != "your_discord_bot_token_here" ]] && ok "DISCORD_TOKEN configured" || warn "DISCORD_TOKEN not set"
    fi
}

cmd_restart() { cmd_stop; cmd_start; }

cmd_discord() { _setup_discord_config; }

# ============================================================================
# MAIN
# ============================================================================
main() {
    local cmd="${1:-setup}"
    shift 2>/dev/null || true

    case "$cmd" in
        setup|deps|env|start|stop|status|restart|qdrant|llama-swap|discord|help)
            "cmd_$cmd" "$@"
            ;;
        *)
            err "Unknown command: $cmd"
            cmd_help
            exit 1
            ;;
    esac
}

main "$@"
