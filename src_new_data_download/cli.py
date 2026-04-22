import argparse
import logging
from pathlib import Path

from .jobs.update_incremental import run_incremental


def main():
    parser = argparse.ArgumentParser(description="Tushare Data Download and Compact Framework")
    parser.add_argument("--project-root", type=str, default=".", help="Project root directory")
    parser.add_argument("--max-task-workers", type=int, default=4, help="Max task workers per dataset")
    parser.add_argument("--max-dataset-workers", type=int, default=10, help="Max parallel datasets")
    
    subparsers = parser.add_subparsers(dest="command")
    
    # update-incremental
    update_parser = subparsers.add_parser("update-incremental", help="Run incremental update")
    update_parser.add_argument("--datasets", type=str, help="Comma separated dataset names")
    
    args = parser.parse_args()
    
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
    
    project_root = Path(args.project_root).absolute()
    
    if args.command == "update-incremental":
        dataset_names = args.datasets.split(",") if args.datasets else None
        run_incremental(
            project_root=project_root,
            dataset_names=dataset_names,
            max_dataset_workers=args.max_dataset_workers,
            max_task_workers=args.max_task_workers
        )
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
