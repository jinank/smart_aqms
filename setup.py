#!/usr/bin/env python3
"""
Setup script for Azure PostgreSQL Streaming Analytics Pipeline
Smart City Air Quality Monitoring System
"""

import subprocess
import sys
import os
from pathlib import Path

def run_command(cmd, description):
    """Run a command and handle errors"""
    print(f"🔧 {description}")
    try:
        result = subprocess.run(cmd, shell=True, check=True, capture_output=True, text=True)
        print(f"✅ {description} completed successfully")
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ {description} failed: {e.stderr}")
        return False

def check_python_version():
    """Check if Python version is compatible"""
    version = sys.version_info
    if version.major < 3 or (version.major == 3 and version.minor < 8):
        print("❌ Python 3.8+ is required")
        return False
    print(f"✅ Python {version.major}.{version.minor}.{version.micro} is compatible")
    return True

def install_dependencies():
    """Install required Python packages"""
    print("\n📦 Installing dependencies...")
    
    # Check if requirements.txt exists
    if not Path("requirements.txt").exists():
        print("❌ requirements.txt not found")
        return False
    
    return run_command(f"{sys.executable} -m pip install -r requirements.txt", "Installing Python packages")

def verify_installation():
    """Verify that all required packages are installed"""
    print("\n🔍 Verifying installation...")
    
    required_packages = [
        'streamlit', 'pandas', 'numpy', 'sqlalchemy', 
        'psycopg2', 'plotly', 'sklearn', 'faker'
    ]
    
    missing = []
    for package in required_packages:
        try:
            __import__(package)
            print(f"✅ {package}")
        except ImportError:
            print(f"❌ {package}")
            missing.append(package)
    
    if missing:
        print(f"\n❌ Missing packages: {', '.join(missing)}")
        return False
    
    print("\n✅ All required packages are installed")
    return True

def create_directories():
    """Create necessary directories"""
    print("\n📁 Creating directories...")
    
    directories = ['logs', 'models', 'data']
    for directory in directories:
        Path(directory).mkdir(exist_ok=True)
        print(f"✅ Created {directory}/ directory")
    
    return True

def main():
    """Main setup function"""
    print("🚀 Azure PostgreSQL Streaming Analytics Pipeline Setup")
    print("=" * 60)
    
    # Check Python version
    if not check_python_version():
        return 1
    
    # Install dependencies
    if not install_dependencies():
        print("\n❌ Setup failed during dependency installation")
        return 1
    
    # Verify installation
    if not verify_installation():
        print("\n❌ Setup failed during verification")
        return 1
    
    # Create directories
    if not create_directories():
        print("\n❌ Setup failed during directory creation")
        return 1
    
    print("\n" + "=" * 60)
    print("🎉 Setup completed successfully!")
    print("=" * 60)
    print("\nNext steps:")
    print("1. Deploy the system: python azure_deploy.py")
    print("2. Run the complete demo: python run_demo.py")
    print("3. Or run components individually:")
    print("   - Data streaming: python azure_stream.py --continuous")
    print("   - Monitoring: python azure_monitor.py")
    print("   - Dashboard: streamlit run app.py")
    print("\nFor more information, see README.md")
    
    return 0

if __name__ == "__main__":
    exit(main())
