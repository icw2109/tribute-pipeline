#!/usr/bin/env python3
"""Count lines of code (LOC) in the tribute-pipeline repository.

Provides statistics on:
- Total files and LOC by language
- Python code breakdown (src/ vs scripts/ vs tests/)
- Detailed file-level metrics (optional)

Usage:
  python scripts/count_loc.py
  python scripts/count_loc.py --detailed
  python scripts/count_loc.py --json
  tribute-loc
  tribute-loc --detailed
"""
from __future__ import annotations
import argparse
import json
import os
import sys
from pathlib import Path
from typing import Dict, List


def count_lines(filepath: Path) -> tuple[int, int, int]:
    """Count lines in a file: (total, blank, comment).
    
    Returns:
        Tuple of (total_lines, blank_lines, comment_lines)
    """
    total = 0
    blank = 0
    comment = 0
    
    try:
        with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
            for line in f:
                total += 1
                stripped = line.strip()
                if not stripped:
                    blank += 1
                elif stripped.startswith('#'):
                    comment += 1
    except Exception:
        pass
    
    return total, blank, comment


def count_python_files(root_dir: Path) -> Dict:
    """Count Python files and LOC in repository.
    
    Returns:
        Dictionary with file counts and LOC statistics
    """
    # Directories to exclude
    exclude_dirs = {'.venv', '__pycache__', '.git', 'out', '.pytest_cache', 'build', 'dist', '*.egg-info'}
    
    # Categorize Python files
    categories = {
        'src': [],
        'scripts': [],
        'tests': [],
        'root': []
    }
    
    # Walk the directory tree
    for py_file in root_dir.rglob('*.py'):
        # Skip excluded directories
        if any(excluded in py_file.parts for excluded in exclude_dirs):
            continue
        
        # Categorize file
        relative = py_file.relative_to(root_dir)
        if relative.parts[0] == 'src':
            category = 'src'
        elif relative.parts[0] == 'scripts':
            category = 'scripts'
        elif relative.parts[0] == 'tests':
            category = 'tests'
        else:
            category = 'root'
        
        # Count lines
        total, blank, comment = count_lines(py_file)
        code = total - blank - comment
        
        categories[category].append({
            'path': str(relative),
            'total': total,
            'blank': blank,
            'comment': comment,
            'code': code
        })
    
    # Aggregate statistics
    stats = {}
    for cat, files in categories.items():
        if files:
            stats[cat] = {
                'files': len(files),
                'total': sum(f['total'] for f in files),
                'blank': sum(f['blank'] for f in files),
                'comment': sum(f['comment'] for f in files),
                'code': sum(f['code'] for f in files),
                'details': files
            }
    
    return stats


def count_all_files(root_dir: Path) -> Dict:
    """Count all code files by extension.
    
    Returns:
        Dictionary with counts by file type
    """
    exclude_dirs = {'.venv', '__pycache__', '.git', 'out', '.pytest_cache', 'build', 'dist'}
    exclude_exts = {'.jsonl', '.pyc', '.pyo'}
    
    # File extensions to track
    extensions = {
        '.py': 'Python',
        '.md': 'Markdown',
        '.json': 'JSON',
        '.yml': 'YAML',
        '.yaml': 'YAML',
        '.toml': 'TOML',
        '.txt': 'Text',
        '.ps1': 'PowerShell',
        '.sh': 'Shell',
        '.ini': 'INI'
    }
    
    counts = {}
    
    for file_path in root_dir.rglob('*'):
        # Skip directories and excluded paths
        if file_path.is_dir():
            continue
        if any(excluded in file_path.parts for excluded in exclude_dirs):
            continue
        
        ext = file_path.suffix.lower()
        if ext in exclude_exts:
            continue
        
        if ext in extensions:
            lang = extensions[ext]
            if lang not in counts:
                counts[lang] = {
                    'files': 0,
                    'total': 0,
                    'blank': 0,
                    'comment': 0,
                    'code': 0
                }
            
            total, blank, comment = count_lines(file_path)
            code = total - blank - comment
            
            counts[lang]['files'] += 1
            counts[lang]['total'] += total
            counts[lang]['blank'] += blank
            counts[lang]['comment'] += comment
            counts[lang]['code'] += code
    
    return counts


def format_number(n: int) -> str:
    """Format number with thousands separator."""
    return f"{n:,}"


def print_summary(python_stats: Dict, all_stats: Dict, detailed: bool = False):
    """Print LOC summary in human-readable format."""
    print("\n" + "="*70)
    print("TRIBUTE-PIPELINE LINES OF CODE STATISTICS")
    print("="*70)
    
    # Python breakdown
    print("\nPython Files Breakdown:")
    print("-" * 70)
    print(f"{'Category':<15} {'Files':>8} {'Code':>10} {'Blank':>10} {'Comment':>10} {'Total':>10}")
    print("-" * 70)
    
    total_files = 0
    total_code = 0
    total_blank = 0
    total_comment = 0
    total_total = 0
    
    for category in ['src', 'scripts', 'tests', 'root']:
        if category in python_stats:
            stats = python_stats[category]
            print(f"{category:<15} {stats['files']:>8} {format_number(stats['code']):>10} "
                  f"{format_number(stats['blank']):>10} {format_number(stats['comment']):>10} "
                  f"{format_number(stats['total']):>10}")
            total_files += stats['files']
            total_code += stats['code']
            total_blank += stats['blank']
            total_comment += stats['comment']
            total_total += stats['total']
    
    print("-" * 70)
    print(f"{'PYTHON TOTAL':<15} {total_files:>8} {format_number(total_code):>10} "
          f"{format_number(total_blank):>10} {format_number(total_comment):>10} "
          f"{format_number(total_total):>10}")
    
    # All files breakdown
    print("\n\nAll Files by Language:")
    print("-" * 70)
    print(f"{'Language':<15} {'Files':>8} {'Code':>10} {'Blank':>10} {'Comment':>10} {'Total':>10}")
    print("-" * 70)
    
    grand_total_files = 0
    grand_total_code = 0
    grand_total_blank = 0
    grand_total_comment = 0
    grand_total_total = 0
    
    # Sort by code lines (descending)
    sorted_langs = sorted(all_stats.items(), key=lambda x: x[1]['code'], reverse=True)
    
    for lang, stats in sorted_langs:
        print(f"{lang:<15} {stats['files']:>8} {format_number(stats['code']):>10} "
              f"{format_number(stats['blank']):>10} {format_number(stats['comment']):>10} "
              f"{format_number(stats['total']):>10}")
        grand_total_files += stats['files']
        grand_total_code += stats['code']
        grand_total_blank += stats['blank']
        grand_total_comment += stats['comment']
        grand_total_total += stats['total']
    
    print("-" * 70)
    print(f"{'GRAND TOTAL':<15} {grand_total_files:>8} {format_number(grand_total_code):>10} "
          f"{format_number(grand_total_blank):>10} {format_number(grand_total_comment):>10} "
          f"{format_number(grand_total_total):>10}")
    print("="*70 + "\n")
    
    # Detailed breakdown if requested
    if detailed:
        print("\nDetailed File Listing (Python):")
        print("-" * 70)
        for category in ['src', 'scripts', 'tests', 'root']:
            if category in python_stats and python_stats[category]['details']:
                print(f"\n{category.upper()}:")
                for file_info in sorted(python_stats[category]['details'], 
                                       key=lambda x: x['code'], reverse=True):
                    print(f"  {file_info['path']:<50} {file_info['code']:>6} lines")


def main(argv=None):
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description='Count lines of code in tribute-pipeline repository'
    )
    parser.add_argument(
        '--detailed',
        action='store_true',
        help='Show detailed file-by-file breakdown'
    )
    parser.add_argument(
        '--json',
        action='store_true',
        help='Output results as JSON'
    )
    
    args = parser.parse_args(argv)
    
    # Determine repository root
    script_dir = Path(__file__).resolve().parent
    root_dir = script_dir.parent
    
    # Count files
    python_stats = count_python_files(root_dir)
    all_stats = count_all_files(root_dir)
    
    if args.json:
        # JSON output
        output = {
            'python_breakdown': {
                cat: {
                    'files': stats['files'],
                    'code': stats['code'],
                    'blank': stats['blank'],
                    'comment': stats['comment'],
                    'total': stats['total']
                } for cat, stats in python_stats.items()
            },
            'all_languages': {
                lang: {
                    'files': stats['files'],
                    'code': stats['code'],
                    'blank': stats['blank'],
                    'comment': stats['comment'],
                    'total': stats['total']
                } for lang, stats in all_stats.items()
            }
        }
        print(json.dumps(output, indent=2))
    else:
        # Human-readable output
        print_summary(python_stats, all_stats, args.detailed)
    
    return 0


if __name__ == '__main__':
    sys.exit(main())
