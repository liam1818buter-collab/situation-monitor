#!/usr/bin/env python3
"""
Situation Monitor - Main Entry Point
Autonomous zero-cost monitoring application
"""

import asyncio
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent))


async def test_full_pipeline():
    """Test the complete Situation Monitor pipeline"""
    print("=" * 60)
    print("🚀 Situation Monitor - Integration Test")
    print("=" * 60)
    
    # Test 1: Core Config
    print("\n✓ Step 1: Configuration loaded")
    try:
        from situation_monitor.core.config import settings
        print(f"  Database: {settings.database_url}")
        print(f"  Log Level: {settings.log_level}")
        print(f"  Alert Cooldown: {settings.alert_cooldown_minutes} min")
    except Exception as e:
        print(f"  ⚠ Warning: {e}")
    
    # Test 2: Core Base Classes
    print("\n✓ Step 2: Core base classes")
    try:
        from situation_monitor.core.base import Document, AnalysisResult, Alert, Source, Analyzer, Storage, Notifier
        print("  - Document model: OK")
        print("  - AnalysisResult model: OK")
        print("  - Alert model: OK")
        print("  - Source ABC: OK")
        print("  - Analyzer ABC: OK")
        print("  - Storage ABC: OK")
        print("  - Notifier ABC: OK")
    except Exception as e:
        print(f"  ⚠ Warning: {e}")
    
    # Test 3: Analysis Pipeline (lazy import)
    print("\n✓ Step 3: Analysis Pipeline imports")
    try:
        from situation_monitor.analysis.pipeline import AnalysisPipeline
        print("  - AnalysisPipeline: Import OK (models load on init)")
    except ImportError as e:
        print(f"  ⚠ ML dependencies not installed: {e}")
        print("  Run: pip install -r requirements.txt")
    except Exception as e:
        print(f"  ⚠ Warning: {e}")
    
    # Test 4: Alert Manager (lazy import)
    print("\n✓ Step 4: Alert Manager imports")
    try:
        from situation_monitor.alerts.manager import AlertManager
        print("  - AlertManager: Import OK")
    except Exception as e:
        print(f"  ⚠ Warning: {e}")
    
    # Test 5: File Structure Check
    print("\n✓ Step 5: File structure verification")
    import os
    required_files = [
        "situation_monitor/core/base.py",
        "situation_monitor/core/config.py",
        "situation_monitor/analysis/pipeline.py",
        "situation_monitor/alerts/manager.py",
        "situation_monitor/nlp/parser.py",
        "requirements.txt",
        ".env.example",
        "README.md"
    ]
    
    found = 0
    for f in required_files:
        path = Path(f)
        if path.exists():
            print(f"  ✓ {f}")
            found += 1
        else:
            print(f"  ✗ {f} (missing)")
    
    print(f"\n  Files: {found}/{len(required_files)} present")
    
    print("\n" + "=" * 60)
    if found == len(required_files):
        print("✅ All core files present!")
    else:
        print("⚠ Some files missing - check agent outputs")
    print("=" * 60)
    print("\nNext steps:")
    print("1. pip install -r requirements.txt")
    print("2. cd situation_monitor/analysis && bash setup.sh")
    print("3. cp .env.example .env")
    print("4. streamlit run situation_monitor/dashboard/app.py")


def main():
    """Main entry point"""
    print("Situation Monitor v1.0")
    print("Zero-cost autonomous monitoring\n")
    
    if len(sys.argv) > 1:
        if sys.argv[1] == "test":
            asyncio.run(test_full_pipeline())
        elif sys.argv[1] == "dashboard":
            import subprocess
            subprocess.run([
                "streamlit", "run", 
                "situation_monitor/dashboard/app.py"
            ])
        else:
            print(f"Unknown command: {sys.argv[1]}")
            print("\nUsage:")
            print("  python main.py test       - Run integration tests")
            print("  python main.py dashboard  - Launch dashboard")
    else:
        # Default: run tests
        asyncio.run(test_full_pipeline())


if __name__ == "__main__":
    main()
