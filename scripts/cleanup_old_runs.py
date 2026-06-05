#!/usr/bin/env python3
"""
Utility script to clean up old generated runs, temporary configs, and uploaded files
from FXplorer to save disk space and keep the project organized.

Usage:
    # Dry run - see what would be deleted
    python scripts/cleanup_old_runs.py --dry-run

    # Keep last 5 runs
    python scripts/cleanup_old_runs.py --keep-runs 5

    # Keep runs from last 7 days
    python scripts/cleanup_old_runs.py --keep-days 7

    # Clean temp files older than 7 days
    python scripts/cleanup_old_runs.py --clean-temps

    # Full cleanup with confirmation
    python scripts/cleanup_old_runs.py --keep-runs 5 --clean-temps --keep-days 7

Safety:
    - Always runs in dry-run mode by default unless --execute flag is provided
    - Creates backup list of deleted items
    - Preserves the most recent runs automatically
"""

import argparse
import shutil
from pathlib import Path
from datetime import datetime, timedelta
import json


def get_run_timestamp(run_dir: Path) -> datetime:
    """Extract timestamp from run directory name or use mtime as fallback."""
    try:
        # Run dirs are named like: run_20251210_123456
        timestamp_str = run_dir.name.split('_', 1)[1]  # Get everything after 'run_'
        return datetime.strptime(timestamp_str, '%Y%m%d_%H%M%S')
    except (ValueError, IndexError):
        # Fallback to modification time
        return datetime.fromtimestamp(run_dir.stat().st_mtime)


def format_size(size_bytes: int) -> str:
    """Format bytes as human-readable size."""
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if size_bytes < 1024.0:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.1f} PB"


def get_dir_size(path: Path) -> int:
    """Calculate total size of directory."""
    total = 0
    for item in path.rglob('*'):
        if item.is_file():
            total += item.stat().st_size
    return total


def cleanup_old_runs(outputs_dir: Path, keep_count: int = None, keep_days: int = None, dry_run: bool = True):
    """
    Clean up old run directories from _outputs/.

    Args:
        outputs_dir: Path to _outputs directory
        keep_count: Number of most recent runs to keep (by timestamp)
        keep_days: Keep runs from last N days
        dry_run: If True, only print what would be deleted
    """
    if not outputs_dir.exists():
        print(f"Outputs directory not found: {outputs_dir}")
        return []

    # Get all run directories
    run_dirs = [d for d in outputs_dir.iterdir() if d.is_dir()]

    if not run_dirs:
        print("No run directories found.")
        return []

    # Sort by timestamp (newest first)
    run_dirs_with_time = [(d, get_run_timestamp(d)) for d in run_dirs]
    run_dirs_with_time.sort(key=lambda x: x[1], reverse=True)

    # Determine which runs to keep
    runs_to_keep = set()

    if keep_count is not None:
        # Keep N most recent runs
        for run_dir, _ in run_dirs_with_time[:keep_count]:
            runs_to_keep.add(run_dir)

    if keep_days is not None:
        # Keep runs from last N days
        cutoff_date = datetime.now() - timedelta(days=keep_days)
        for run_dir, timestamp in run_dirs_with_time:
            if timestamp >= cutoff_date:
                runs_to_keep.add(run_dir)

    # Default: keep at least the 3 most recent if no criteria specified
    if keep_count is None and keep_days is None:
        for run_dir, _ in run_dirs_with_time[:3]:
            runs_to_keep.add(run_dir)
        print(f"ℹ No criteria specified, keeping 3 most recent runs by default")

    # Determine what to delete
    runs_to_delete = [d for d, _ in run_dirs_with_time if d not in runs_to_keep]

    if not runs_to_delete:
        print("No old runs to clean up.")
        return []

    # Calculate space that will be freed
    total_size = sum(get_dir_size(d) for d in runs_to_delete)

    print(f"\n{'DRY RUN - ' if dry_run else ''}Run Cleanup Summary:")
    print(f"Total runs: {len(run_dirs)}")
    print(f"Runs to keep: {len(runs_to_keep)}")
    print(f"Runs to delete: {len(runs_to_delete)}")
    print(f"Space to free: {format_size(total_size)}\n")

    deleted_items = []
    for run_dir in runs_to_delete:
        size = get_dir_size(run_dir)
        timestamp = get_run_timestamp(run_dir)

        if dry_run:
            print(f"[DRY RUN] Would delete: {run_dir.name} ({timestamp.strftime('%Y-%m-%d %H:%M')}, {format_size(size)})")
        else:
            print(f"Deleting: {run_dir.name} ({timestamp.strftime('%Y-%m-%d %H:%M')}, {format_size(size)})")
            shutil.rmtree(run_dir)

        deleted_items.append({
            'path': str(run_dir),
            'name': run_dir.name,
            'timestamp': timestamp.isoformat(),
            'size_bytes': size
        })

    return deleted_items


def cleanup_temp_files(uploads_dir: Path, tmp_configs_dir: Path, keep_days: int = 7, dry_run: bool = True):
    """
    Clean up temporary uploaded files and generated configs older than N days.

    Args:
        uploads_dir: Path to uploads/ directory
        tmp_configs_dir: Path to tmp_configs/ directory
        keep_days: Delete files older than this many days
        dry_run: If True, only print what would be deleted
    """
    cutoff_time = datetime.now() - timedelta(days=keep_days)
    deleted_items = []

    for temp_dir in [uploads_dir, tmp_configs_dir]:
        if not temp_dir.exists():
            continue

        files = [f for f in temp_dir.iterdir() if f.is_file()]
        old_files = [f for f in files if datetime.fromtimestamp(f.stat().st_mtime) < cutoff_time]

        if not old_files:
            print(f"No old files to clean in {temp_dir.name}/")
            continue

        total_size = sum(f.stat().st_size for f in old_files)

        print(f"\n{'DRY RUN - ' if dry_run else ''}{temp_dir.name}/ Cleanup:")
        print(f"Total files: {len(files)}")
        print(f"Old files (>{keep_days} days): {len(old_files)}")
        print(f"Space to free: {format_size(total_size)}\n")

        for file in old_files:
            age_days = (datetime.now() - datetime.fromtimestamp(file.stat().st_mtime)).days
            size = file.stat().st_size

            if dry_run:
                print(f"[DRY RUN] Would delete: {file.name} ({age_days} days old, {format_size(size)})")
            else:
                print(f"Deleting: {file.name} ({age_days} days old, {format_size(size)})")
                file.unlink()

            deleted_items.append({
                'path': str(file),
                'name': file.name,
                'age_days': age_days,
                'size_bytes': size
            })

    return deleted_items


def save_cleanup_log(deleted_items: list, log_file: Path):
    """Save list of deleted items for recovery reference."""
    log_data = {
        'cleanup_timestamp': datetime.now().isoformat(),
        'deleted_items': deleted_items,
        'total_items': len(deleted_items),
        'total_size_bytes': sum(item['size_bytes'] for item in deleted_items)
    }

    with open(log_file, 'w') as f:
        json.dump(log_data, f, indent=2)

    print(f"\nCleanup log saved to: {log_file}")


def main():
    parser = argparse.ArgumentParser(
        description='Clean up old FXplorer runs and temporary files',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )

    parser.add_argument(
        '--keep-runs',
        type=int,
        help='Number of most recent runs to keep in _outputs/'
    )

    parser.add_argument(
        '--keep-days',
        type=int,
        help='Keep runs from last N days (alternative to --keep-runs)'
    )

    parser.add_argument(
        '--clean-temps',
        action='store_true',
        help='Clean temporary files (uploads/ and tmp_configs/) older than 7 days'
    )

    parser.add_argument(
        '--temp-age-days',
        type=int,
        default=7,
        help='Age threshold for temp file cleanup (default: 7 days)'
    )

    parser.add_argument(
        '--dry-run',
        action='store_true',
        default=True,
        help='Show what would be deleted without actually deleting (default: True)'
    )

    parser.add_argument(
        '--execute',
        action='store_true',
        help='Actually delete files (disables dry-run mode)'
    )

    parser.add_argument(
        '--outputs-dir',
        type=Path,
        default=Path(__file__).parent.parent / '_outputs',
        help='Path to _outputs directory (default: ./_outputs)'
    )

    parser.add_argument(
        '--uploads-dir',
        type=Path,
        default=Path(__file__).parent.parent / 'uploads',
        help='Path to uploads directory (default: ./uploads)'
    )

    parser.add_argument(
        '--tmp-configs-dir',
        type=Path,
        default=Path(__file__).parent.parent / 'tmp_configs',
        help='Path to tmp_configs directory (default: ./tmp_configs)'
    )

    args = parser.parse_args()

    # Override dry_run if --execute is specified
    dry_run = not args.execute

    if dry_run:
        print("Dry run mode. No files will be deleted.")
        print("Use --execute flag to actually delete files")
        print("")

    deleted_items = []

    # Cleanup old runs
    if args.keep_runs is not None or args.keep_days is not None:
        print("Cleaning up old run directories...")
        deleted_items.extend(
            cleanup_old_runs(
                args.outputs_dir,
                keep_count=args.keep_runs,
                keep_days=args.keep_days,
                dry_run=dry_run
            )
        )

    # Cleanup temp files
    if args.clean_temps:
        print("\nCleaning up temporary files...")
        deleted_items.extend(
            cleanup_temp_files(
                args.uploads_dir,
                args.tmp_configs_dir,
                keep_days=args.temp_age_days,
                dry_run=dry_run
            )
        )

    # Save cleanup log if files were actually deleted
    if deleted_items and not dry_run:
        log_file = Path(__file__).parent.parent / f"cleanup_log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        save_cleanup_log(deleted_items, log_file)

    if dry_run:
        print("\nDry run complete. No files were deleted.")
        print("Review the output above, then run with --execute to proceed")
    else:
        print("\nCleanup complete.")
        total_freed = sum(item['size_bytes'] for item in deleted_items)
        print(f"Deleted {len(deleted_items)} items")
        print(f"Freed {format_size(total_freed)} of disk space")


if __name__ == '__main__':
    main()
