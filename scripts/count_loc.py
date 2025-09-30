#!/usr/bin/env python
"""Count lines of code in the tribute-pipeline repository.

Provides a breakdown by directory and file type.

Usage:
  python scripts/count_loc.py
  python scripts/count_loc.py --json
  python scripts/count_loc.py --detail
"""
from __future__ import annotations
import argparse
import json
import os
import sys
from collections import defaultdict
from pathlib import Path


def count_lines(file_path: Path) -> dict[str, int]:
    """Count total, code, comment, and blank lines in a file."""
    try:
        with file_path.open('r', encoding='utf-8', errors='ignore') as f:
            lines = f.readlines()
    except Exception:
        return {'total': 0, 'code': 0, 'comment': 0, 'blank': 0}
    
    total = len(lines)
    blank = sum(1 for line in lines if not line.strip())
    comment = sum(1 for line in lines if line.strip().startswith('#'))
    code = total - blank - comment
    
    return {
        'total': total,
        'code': code,
        'comment': comment,
        'blank': blank
    }


def scan_repository(root: Path, extensions: list[str], exclude_dirs: set[str]) -> dict:
    """Scan repository for files with given extensions."""
    results = {
        'by_directory': defaultdict(lambda: {'total': 0, 'code': 0, 'comment': 0, 'blank': 0, 'files': 0}),
        'by_extension': defaultdict(lambda: {'total': 0, 'code': 0, 'comment': 0, 'blank': 0, 'files': 0}),
        'files': []
    }
    
    for file_path in root.rglob('*'):
        # Skip excluded directories
        if any(exclude in file_path.parts for exclude in exclude_dirs):
            continue
        
        # Check if file has one of the target extensions
        if file_path.is_file() and file_path.suffix in extensions:
            counts = count_lines(file_path)
            
            # Get relative path and directory
            rel_path = file_path.relative_to(root)
            directory = str(rel_path.parts[0]) if len(rel_path.parts) > 1 else '.'
            
            # Update by directory
            for key in ['total', 'code', 'comment', 'blank']:
                results['by_directory'][directory][key] += counts[key]
            results['by_directory'][directory]['files'] += 1
            
            # Update by extension
            ext = file_path.suffix
            for key in ['total', 'code', 'comment', 'blank']:
                results['by_extension'][ext][key] += counts[key]
            results['by_extension'][ext]['files'] += 1
            
            # Store file info
            results['files'].append({
                'path': str(rel_path),
                'directory': directory,
                'extension': ext,
                **counts
            })
    
    return results


def build_parser():
    p = argparse.ArgumentParser(description='Count lines of code in the repository.')
    p.add_argument('--json', action='store_true', help='Output as JSON')
    p.add_argument('--detail', action='store_true', help='Show per-file breakdown')
    p.add_argument('--extensions', default='.py', help='Comma-separated file extensions (default: .py)')
    p.add_argument('--include-docs', action='store_true', help='Include markdown files in count')
    return p


def main(argv=None):
    args = build_parser().parse_args(argv)
    
    # Set up paths and extensions
    root = Path(__file__).parents[1]
    extensions = [ext if ext.startswith('.') else f'.{ext}' 
                  for ext in args.extensions.split(',')]
    
    if args.include_docs:
        extensions.extend(['.md', '.rst', '.txt'])
    
    exclude_dirs = {'.git', '__pycache__', '.pytest_cache', 'node_modules', 
                    '.venv', 'venv', 'dist', 'build', '.egg-info'}
    
    # Scan repository
    results = scan_repository(root, extensions, exclude_dirs)
    
    # Calculate totals
    totals = {
        'total': sum(f['total'] for f in results['files']),
        'code': sum(f['code'] for f in results['files']),
        'comment': sum(f['comment'] for f in results['files']),
        'blank': sum(f['blank'] for f in results['files']),
        'files': len(results['files'])
    }
    
    # Prepare output
    summary = {
        'repository': 'tribute-pipeline',
        'totals': totals,
        'by_directory': dict(results['by_directory']),
        'by_extension': dict(results['by_extension'])
    }
    
    if args.detail:
        summary['files'] = results['files']
    
    if args.json:
        print(json.dumps(summary, indent=2))
    else:
        # Human-readable output
        print('=' * 60)
        print('Lines of Code Summary: tribute-pipeline')
        print('=' * 60)
        print()
        print(f"Total Files:       {totals['files']:>8}")
        print(f"Total Lines:       {totals['total']:>8}")
        print(f"  Code:            {totals['code']:>8}")
        print(f"  Comments:        {totals['comment']:>8}")
        print(f"  Blank:           {totals['blank']:>8}")
        print()
        
        print('By Directory:')
        print('-' * 60)
        sorted_dirs = sorted(results['by_directory'].items(), 
                            key=lambda x: x[1]['total'], reverse=True)
        for dir_name, counts in sorted_dirs:
            print(f"  {dir_name:<20} {counts['files']:>4} files  "
                  f"{counts['total']:>6} lines  ({counts['code']:>5} code)")
        print()
        
        if len(results['by_extension']) > 1:
            print('By Extension:')
            print('-' * 60)
            sorted_ext = sorted(results['by_extension'].items(), 
                               key=lambda x: x[1]['total'], reverse=True)
            for ext, counts in sorted_ext:
                print(f"  {ext:<10} {counts['files']:>4} files  "
                      f"{counts['total']:>6} lines  ({counts['code']:>5} code)")
            print()
        
        if args.detail:
            print('Detailed File Breakdown:')
            print('-' * 60)
            sorted_files = sorted(results['files'], 
                                 key=lambda x: x['total'], reverse=True)
            for f in sorted_files[:20]:  # Top 20 files
                print(f"  {f['path']:<50} {f['total']:>6} lines")
            if len(results['files']) > 20:
                print(f"  ... and {len(results['files']) - 20} more files")


if __name__ == '__main__':
    main()
