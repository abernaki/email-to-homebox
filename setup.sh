#!/bin/bash
# Quick setup script for Receipt Processor

set -e

echo "========================================="
echo "Receipt Processor Setup"
echo "========================================="
echo ""

# Check Python version
echo "Checking Python version..."
if command -v python3 &> /dev/null; then
    PYTHON_VERSION=$(python3 --version | cut -d' ' -f2)
    echo "✓ Found Python $PYTHON_VERSION"
else
    echo "✗ Python 3 not found. Please install Python 3.10 or later."
    exit 1
fi

# Create project structure
echo ""
echo "Creating project structure..."
mkdir -p src config data/{logs,failed,processed}
echo "✓ Directories created"

# Create virtual environment
echo ""
echo "Creating virtual environment..."
if [ ! -d "venv" ]; then
    python3 -m venv venv
    echo "✓ Virtual environment created"
else
    echo "✓ Virtual environment already exists"
fi

# Activate virtual environment
echo ""
echo "Activating virtual environment..."
source venv/bin/activate

# Install dependencies
echo ""
echo "Installing dependencies..."
echo "This may take a few minutes..."
pip install --upgrade pip > /dev/null 2>&1
pip install -r requirements.txt

echo "✓ Dependencies installed"

# Create .env if it doesn't exist
if [ ! -f ".env" ]; then
    echo ""
    echo "Creating .env file..."
    cat > .env << 'EOF'
# Email Configuration
EMAIL_PROVIDER=gmail
EMAIL_ADDRESS=your-email@gmail.com
EMAIL_PASSWORD=your-app-password-here
EMAIL_IMAP_HOST=imap.gmail.com
EMAIL_IMAP_PORT=993

# Homebox Configuration
HOMEBOX_URL=http://192.168.1.xxx:7745
HOMEBOX_API_KEY=your-dedicated-service-account-key
# Legacy username/password fallback only; prefer a dedicated API key.
# HOMEBOX_USERNAME=your-homebox-username
# HOMEBOX_PASSWORD=your-homebox-password

# Ollama Model Configuration
OLLAMA_HOST=http://localhost:11434
AI_MODEL=qwen2.5:7b
AI_TEMPERATURE=0.1
AI_MAX_TOKENS=2048

# Processing Settings
CHECK_INTERVAL=300
MIN_CONFIDENCE=0.7

# Logging
LOG_LEVEL=INFO
EOF
    echo "✓ Created .env file - PLEASE EDIT IT WITH YOUR SETTINGS"
else
    echo "✓ .env file already exists"
fi

# Create .gitignore
if [ ! -f ".gitignore" ]; then
    echo ""
    echo "Creating .gitignore..."
    cat > .gitignore << 'EOF'
# Environment
venv/
.env
*.pyc
__pycache__/

# Data
data/logs/*
data/failed/*
data/processed/*

# Keep directories
!data/logs/.gitkeep
!data/failed/.gitkeep
!data/processed/.gitkeep

# OS
.DS_Store
*.swp

# IDE
.vscode/
.idea/
EOF
    
    # Create .gitkeep files
    touch data/logs/.gitkeep data/failed/.gitkeep data/processed/.gitkeep
    echo "✓ Created .gitignore"
fi

echo ""
echo "========================================="
echo "Setup Complete!"
echo "========================================="
echo ""
echo "Next steps:"
echo ""
echo "1. Edit .env with your email and Homebox credentials:"
echo "   - For Gmail: Create an App Password at https://myaccount.google.com/apppasswords"
echo "   - For Homebox: Set a dedicated service-account API key"
echo ""
echo "2. Verify your config in config/config.yml"
echo ""
echo "3. Run the processor:"
echo "   source venv/bin/activate"
echo "   python src/app.py --live"
echo ""
echo "Make sure Ollama is running and has the configured model available."
echo ""
echo "Tips:"
echo "  - Test with a single receipt email first"
echo "  - Check data/failed/ for emails that couldn't be processed"
echo "  - Check data/logs/processor.log for detailed logs"
echo ""