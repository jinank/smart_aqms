#!/usr/bin/env python3
"""
Azure PostgreSQL Streaming Analytics Demo Runner
Complete demonstration of the Smart City Air Quality Monitoring System

This script orchestrates the entire streaming analytics pipeline:
1. Deploy schema and seed data
2. Start data streaming
3. Launch monitoring system
4. Start dashboard
"""

import subprocess
import time
import threading
import signal
import sys
import os
from pathlib import Path

class StreamingAnalyticsDemo:
    def __init__(self):
        self.processes = []
        self.running = False
        
    def run_command(self, cmd, description):
        """Run a command and track the process"""
        print(f"🚀 {description}")
        print(f"Command: {' '.join(cmd)}")
        
        try:
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
                universal_newlines=True
            )
            self.processes.append((process, description))
            return process
        except Exception as e:
            print(f"❌ Failed to start {description}: {e}")
            return None
    
    def deploy_system(self):
        """Deploy the complete system to Azure PostgreSQL"""
        print("=" * 60)
        print("🏗️ DEPLOYING STREAMING ANALYTICS SYSTEM")
        print("=" * 60)
        
        # Run deployment
        deploy_cmd = [sys.executable, "azure_deploy.py"]
        deploy_process = self.run_command(deploy_cmd, "System Deployment")
        
        if deploy_process:
            # Wait for deployment to complete
            stdout, stderr = deploy_process.communicate()
            
            if deploy_process.returncode == 0:
                print("✅ System deployment completed successfully!")
                return True
            else:
                print(f"❌ Deployment failed: {stderr}")
                return False
        
        return False
    
    def start_streaming(self):
        """Start the data streaming process"""
        print("\n" + "=" * 60)
        print("🌊 STARTING DATA STREAMING")
        print("=" * 60)
        
        # Start streaming with high volume
        stream_cmd = [
            sys.executable, "azure_stream.py", 
            "--continuous", 
            "--rate", "300", 
            "--batch-size", "50"
        ]
        
        stream_process = self.run_command(stream_cmd, "Data Streaming")
        return stream_process
    
    def start_monitoring(self):
        """Start the monitoring system"""
        print("\n" + "=" * 60)
        print("🔍 STARTING MONITORING SYSTEM")
        print("=" * 60)
        
        # Start monitoring
        monitor_cmd = [
            sys.executable, "azure_monitor.py",
            "--interval", "30",  # Faster monitoring cycles
            "--outlier-window", "30",
            "--ml-window", "60"
        ]
        
        monitor_process = self.run_command(monitor_cmd, "Monitoring System")
        return monitor_process
    
    def start_dashboard(self):
        """Start the Streamlit dashboard"""
        print("\n" + "=" * 60)
        print("📊 STARTING DASHBOARD")
        print("=" * 60)
        
        # Start dashboard
        dashboard_cmd = [
            "streamlit", "run", "app.py",
            "--server.port", "8501",
            "--server.address", "0.0.0.0"
        ]
        
        dashboard_process = self.run_command(dashboard_cmd, "Streamlit Dashboard")
        return dashboard_process
    
    def monitor_processes(self):
        """Monitor all running processes"""
        while self.running:
            time.sleep(5)
            
            for process, description in self.processes[:]:
                if process.poll() is not None:  # Process has terminated
                    print(f"⚠️ {description} has stopped (exit code: {process.returncode})")
                    self.processes.remove((process, description))
            
            if not self.processes:
                print("⚠️ All processes have stopped!")
                break
    
    def stop_all_processes(self):
        """Stop all running processes"""
        print("\n⏹️ Stopping all processes...")
        
        for process, description in self.processes:
            try:
                print(f"Stopping {description}...")
                process.terminate()
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                print(f"Force killing {description}...")
                process.kill()
            except Exception as e:
                print(f"Error stopping {description}: {e}")
        
        self.processes.clear()
        self.running = False
    
    def run_full_demo(self):
        """Run the complete streaming analytics demonstration"""
        print("🚀 AZURE POSTGRESQL STREAMING ANALYTICS DEMO")
        print("Smart City Air Quality Monitoring System")
        print("=" * 60)
        
        try:
            # Step 1: Deploy system
            if not self.deploy_system():
                print("❌ Deployment failed. Exiting.")
                return False
            
            # Wait a moment for deployment to settle
            print("⏳ Waiting for system to initialize...")
            time.sleep(5)
            
            # Step 2: Start streaming data
            stream_process = self.start_streaming()
            if not stream_process:
                print("❌ Failed to start streaming. Exiting.")
                return False
            
            # Wait for some data to accumulate
            print("⏳ Waiting for initial data generation...")
            time.sleep(10)
            
            # Step 3: Start monitoring system
            monitor_process = self.start_monitoring()
            if not monitor_process:
                print("❌ Failed to start monitoring. Exiting.")
                return False
            
            # Wait for monitoring to initialize
            print("⏳ Waiting for monitoring system to initialize...")
            time.sleep(5)
            
            # Step 4: Start dashboard
            dashboard_process = self.start_dashboard()
            if not dashboard_process:
                print("❌ Failed to start dashboard. Exiting.")
                return False
            
            # All systems are running
            print("\n" + "=" * 60)
            print("🎉 ALL SYSTEMS RUNNING!")
            print("=" * 60)
            print("📊 Dashboard: http://localhost:8501")
            print("🌊 Data streaming at 300 records/minute")
            print("🔍 Monitoring with 30-second cycles")
            print("⏹️ Press Ctrl+C to stop all systems")
            print("=" * 60)
            
            self.running = True
            
            # Monitor processes
            self.monitor_processes()
            
        except KeyboardInterrupt:
            print("\n⏹️ Demo stopped by user")
        except Exception as e:
            print(f"❌ Demo error: {e}")
        finally:
            self.stop_all_processes()
        
        return True

def signal_handler(sig, frame):
    """Handle Ctrl+C gracefully"""
    print(f"\n⏹️ Received interrupt signal...")
    if 'demo' in globals():
        demo.stop_all_processes()
    sys.exit(0)

def check_dependencies():
    """Check if all required dependencies are installed"""
    required_packages = [
        'streamlit', 'pandas', 'numpy', 'sqlalchemy', 
        'psycopg2', 'plotly', 'sklearn', 'faker'
    ]
    
    missing = []
    for package in required_packages:
        try:
            __import__(package)
        except ImportError:
            missing.append(package)
    
    if missing:
        print(f"❌ Missing dependencies: {', '.join(missing)}")
        print("Install with: pip install -r requirements.txt")
        return False
    
    return True

def main():
    """Main demo function"""
    print("🔍 Checking dependencies...")
    if not check_dependencies():
        return 1
    
    # Set up signal handler
    signal.signal(signal.SIGINT, signal_handler)
    
    global demo
    demo = StreamingAnalyticsDemo()
    
    try:
        success = demo.run_full_demo()
        return 0 if success else 1
    except Exception as e:
        print(f"❌ Demo failed: {e}")
        return 1

if __name__ == "__main__":
    exit(main())
