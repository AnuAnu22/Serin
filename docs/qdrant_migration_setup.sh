#!/bin/bash

# Qdrant Migration Setup Script
# This script automates the setup and migration process from ChromaDB to Qdrant

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BOT_DATA_DIR="$PROJECT_DIR/bot_data"
BACKUP_DIR="$BOT_DATA_DIR/backups"
CONFIG_FILE="$PROJECT_DIR/qdrant_config.json"
ENV_FILE="$PROJECT_DIR/.env"

echo -e "${BLUE}🚀 Qdrant Migration Setup Script${NC}"
echo "====================================="

# Function to print status messages
print_status() {
    echo -e "${GREEN}✅ $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}⚠️  $1${NC}"
}

print_error() {
    echo -e "${RED}❌ $1${NC}"
}

print_info() {
    echo -e "${BLUE}ℹ️  $1${NC}"
}

# Check if running as root
check_root() {
    if [[ $EUID -eq 0 ]]; then
        print_error "This script should not be run as root"
        exit 1
    fi
}

# Check Python version
check_python() {
    print_info "Checking Python version..."
    if ! command -v python3 &> /dev/null; then
        print_error "Python 3 is not installed"
        exit 1
    fi
    
    python_version=$(python3 -c 'import sys; print(".".join(map(str, sys.version_info[:2])))')
    required_version="3.12"
    
    if [ "$(printf '%s\n' "$required_version" "$python_version" | sort -V | head -n1)" != "$required_version" ]; then
        print_error "Python $required_version or higher is required (found $python_version)"
        exit 1
    fi
    
    print_status "Python $python_version found"
}

# Check system requirements
check_requirements() {
    print_info "Checking system requirements..."
    
    # Check available memory
    if command -v free &> /dev/null; then
        available_mem=$(free -m | awk '/Mem:/ {print $7}')
        if [ "$available_mem" -lt 2048 ]; then
            print_warning "Less than 2GB of available memory. Qdrant may perform poorly."
        fi
    fi
    
    # Check disk space
    if command -v df &> /dev/null; then
        available_space=$(df -k "$PROJECT_DIR" | tail -1 | awk '{print $4}')
        if [ "$available_space" -lt 1073741824 ]; then # 1GB
            print_warning "Less than 1GB of available disk space"
        fi
    fi
    
    print_status "System requirements checked"
}

# Create necessary directories
create_directories() {
    print_info "Creating necessary directories..."
    
    mkdir -p "$BOT_DATA_DIR"
    mkdir -p "$BACKUP_DIR"
    mkdir -p "$BOT_DATA_DIR/qdrant_data"
    mkdir -p "$BOT_DATA_DIR/logs"
    
    print_status "Directories created"
}

# Backup existing data


# Install Python dependencies
install_dependencies() {
    print_info "Installing Python dependencies..."
    
    # Create virtual environment if it doesn't exist
    if [ ! -d "$PROJECT_DIR/.venv" ]; then
        print_info "Creating virtual environment..."
        python3 -m venv "$PROJECT_DIR/.venv"
    fi
    
    # Activate virtual environment
    source "$PROJECT_DIR/.venv/bin/activate"
    
    # Upgrade pip
    pip install --upgrade pip
    
    # Install dependencies
    pip install -r "$PROJECT_DIR/requirements.txt" 2>/dev/null || {
        print_warning "requirements.txt not found, installing from pyproject.toml"
        pip install -e "$PROJECT_DIR"
    }
    
    # Install additional Qdrant dependencies
    pip install qdrant-client sentence-transformers rank-bm25
    
    print_status "Dependencies installed"
}

# Setup environment variables
setup_environment() {
    print_info "Setting up environment variables..."
    
    # Create .env file if it doesn't exist
    if [ ! -f "$ENV_FILE" ]; then
        cat > "$ENV_FILE" << EOF
# Qdrant Configuration
USE_QDRANT=true
QDRANT_HOST=localhost
QDRANT_PORT=6333

# Bot Configuration
DEBUG_MODE=false
TRACE_MESSAGES=true
MAINTENANCE_INTERVAL_HOURS=24
CONTROL_PANEL_PORT=8080
ENABLE_VOICE=true
ENABLE_TTS=false

# Data Configuration
DATA_DIR=./bot_data

# Model Configuration
LLM_MODEL=__LARGEST__
BACKGROUND_MODEL=__SMALLEST__

# Security
DISCORD_TOKEN=your_discord_token_here
EOF
        print_status "Created .env file with default configuration"
    else
        print_info ".env file already exists"
    fi
    

    
    print_status "Environment variables configured"
}

# Start Qdrant service
start_qdrant() {
    print_info "Starting Qdrant service..."
    
    # Check if Qdrant is already running
    if curl -s http://localhost:6333/ >/dev/null 2>&1; then
        print_info "Qdrant is already running"
        return 0
    fi
    
    # Try to start Qdrant using Docker (preferred method)
    if command -v docker &> /dev/null; then
        print_info "Starting Qdrant using Docker..."
        
        # Check if Qdrant Docker image exists
        if ! docker images | grep -q "qdrant/qdrant"; then
            print_info "Pulling Qdrant Docker image..."
            docker pull qdrant/qdrant:v1.12.0
        fi
        
        # Start Qdrant container
        docker run -d \
            --name qdrant-serin \
            -p 6333:6333 \
            -v "$BOT_DATA_DIR/qdrant_data:/qdrant/storage" \
            qdrant/qdrant:v1.12.0
        
        # Wait for Qdrant to start
        print_info "Waiting for Qdrant to start..."
        for i in {1..30}; do
            if curl -s http://localhost:6333/ >/dev/null 2>&1; then
                print_status "Qdrant started successfully"
                return 0
            fi
            sleep 1
        done
        
        print_error "Qdrant failed to start"
        exit 1
    else
        print_warning "Docker not found. Please start Qdrant manually:"
        print_warning "  docker run -d --name qdrant-serin -p 6333:6333 qdrant/qdrant:v1.12.0"
        print_warning "Or install Qdrant using your package manager"
        return 1
    fi
}

# Test Qdrant connection
test_qdrant_connection() {
    print_info "Testing Qdrant connection..."
    
    if curl -s http://localhost:6333/ >/dev/null 2>&1; then
        print_status "Qdrant connection successful"
        
        # Test Python connection
        source "$PROJECT_DIR/.venv/bin/activate"
        python3 -c "
import sys
sys.path.append('$PROJECT_DIR')
from qdrant_memory_system import QdrantMemorySystem
try:
    ms = QdrantMemorySystem()
    print('✅ Python Qdrant connection successful')
except Exception as e:
    print(f'❌ Python connection failed: {e}')
    sys.exit(1)
"
    else
        print_error "Qdrant connection failed"
        exit 1
    fi
}

# Initialize memory system
initialize_memory_system() {
    print_info "Initializing memory system..."
    
    source "$PROJECT_DIR/.venv/bin/activate"
    cd "$PROJECT_DIR"
    
    python3 -c "
import sys
sys.path.append('$PROJECT_DIR')
from qdrant_memory_system import QdrantMemorySystem
import logging

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

try:
    # Initialize Qdrant memory system
    memory_system = QdrantMemorySystem()
    print('✅ Qdrant Memory System initialized successfully')
    
    # Test basic operations
    stats = memory_system.get_stats()
    print(f'📊 Memory system stats: {stats}')
    
except Exception as e:
    logger.error(f'❌ Failed to initialize memory system: {e}')
    sys.exit(1)
"
    
    print_status "Memory system initialized"
}

# Run basic tests
run_tests() {
    print_info "Running basic tests..."
    
    source "$PROJECT_DIR/.venv/bin/activate"
    cd "$PROJECT_DIR"
    
    # Test memory operations
    python3 -c "
import sys
sys.path.append('$PROJECT_DIR')
from qdrant_memory_system import QdrantMemorySystem

try:
    ms = QdrantMemorySystem()
    
    # Test adding a memory
    memory_id = ms.add_memory_enhanced(
        content='Test memory for Qdrant migration',
        user_id='test_user',
        username='TestUser',
        channel_id='test_channel',
        participants=['test_user'],
        emotional_tone='neutral',
        importance=0.5
    )
    print(f'✅ Memory added: {memory_id}')
    
    # Test searching
    results = ms.search_hybrid('test', 'test_user', 5)
    print(f'✅ Search completed: {len(results)} results')
    
    # Test user management
    ms.upsert_user('test_user', 'TestUser', 'Test User')
    profile = ms.get_user_profile('test_user')
    print(f'✅ User profile: {profile[\"username\"] if profile else \"Not found\"}')
    
    print('🎉 All tests passed!')
    
except Exception as e:
    print(f'❌ Test failed: {e}')
    import traceback
    traceback.print_exc()
    sys.exit(1)
"
}

# Create startup script
create_startup_script() {
    print_info "Creating startup script..."
    
    cat > "$PROJECT_DIR/start_qdrant_bot.sh" << 'EOF'
#!/bin/bash

# Startup script for Qdrant-enabled Discord bot

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Activate virtual environment
source "$SCRIPT_DIR/.venv/bin/activate"

# Check if Qdrant is running
if ! curl -s http://localhost:6333/ >/dev/null 2>&1; then
    echo "🚀 Starting Qdrant..."
    docker start qdrant-serin 2>/dev/null || {
        echo "❌ Qdrant container not found. Please run setup script first."
        exit 1
    }
    
    # Wait for Qdrant
    echo "⏳ Waiting for Qdrant to start..."
    for i in {1..30}; do
        if curl -s http://localhost:6333/ >/dev/null 2>&1; then
            break
        fi
        sleep 1
    done
fi

# Start the bot
echo "🤖 Starting Discord bot..."
python3 -m serin
EOF
    
    chmod +x "$PROJECT_DIR/start_qdrant_bot.sh"
    print_status "Startup script created: start_qdrant_bot.sh"
}

# Create control panel startup script
create_control_panel_script() {
    print_info "Creating control panel startup script..."
    
    cat > "$PROJECT_DIR/start_control_panel.sh" << 'EOF'
#!/bin/bash

# Startup script for Qdrant control panel

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Activate virtual environment
source "$SCRIPT_DIR/.venv/bin/activate"

# Start control panel
echo "🌐 Starting control panel..."
python3 enhanced_api_routes.py
EOF
    
    chmod +x "$PROJECT_DIR/start_control_panel.sh"
    print_status "Control panel script created: start_control_panel.sh"
}

# Main setup process
main() {
    echo -e "\n${BLUE}🔧 Starting Qdrant Migration Setup${NC}"
    echo "====================================="
    
    check_root
    check_python
    check_requirements
    create_directories

    install_dependencies
    setup_environment
    start_qdrant
    test_qdrant_connection
    initialize_memory_system
    run_tests
    create_startup_script
    create_control_panel_script
    
    echo -e "\n${GREEN}🎉 Qdrant Migration Setup Complete!${NC}"
    echo "====================================="
    echo ""
    echo "Next steps:"
    echo "1. Edit your .env file with your Discord bot token"
    echo "2. Run './start_qdrant_bot.sh' to start the bot"
    echo "3. Run './start_control_panel.sh' to start the control panel"
    echo "4. Access the control panel at http://localhost:8080"
    echo ""
    echo "Backup location: $BACKUP_DIR"
    echo "Configuration: $CONFIG_FILE"
    echo ""
    echo "For troubleshooting, check the logs in $BOT_DATA_DIR/logs/"
}

# Run main function
main "$@"