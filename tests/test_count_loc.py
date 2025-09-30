"""Test the count_loc script functionality."""
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_count_loc_runs():
    """Test that count_loc script runs without errors."""
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "count_loc.py")],
        capture_output=True,
        text=True,
        timeout=10
    )
    assert result.returncode == 0
    assert "TRIBUTE-PIPELINE LINES OF CODE STATISTICS" in result.stdout
    assert "Python Files Breakdown:" in result.stdout


def test_count_loc_json():
    """Test that count_loc produces valid JSON output."""
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "count_loc.py"), "--json"],
        capture_output=True,
        text=True,
        timeout=10
    )
    assert result.returncode == 0
    
    # Parse JSON to verify it's valid
    data = json.loads(result.stdout)
    assert "python_breakdown" in data
    assert "all_languages" in data
    
    # Check that Python breakdown has expected categories
    python_breakdown = data["python_breakdown"]
    assert "src" in python_breakdown
    assert "scripts" in python_breakdown
    assert "tests" in python_breakdown
    
    # Validate structure of each category
    for category, stats in python_breakdown.items():
        assert "files" in stats
        assert "code" in stats
        assert "blank" in stats
        assert "comment" in stats
        assert "total" in stats
        assert stats["files"] > 0
        assert stats["code"] > 0


def test_count_loc_detailed():
    """Test that detailed flag works."""
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "count_loc.py"), "--detailed"],
        capture_output=True,
        text=True,
        timeout=10
    )
    assert result.returncode == 0
    assert "Detailed File Listing" in result.stdout
    assert "SRC:" in result.stdout or "SCRIPTS:" in result.stdout
