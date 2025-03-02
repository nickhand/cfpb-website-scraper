from pathlib import Path

from loguru import logger


def search_and_replace(
    root_dir, old_string, new_string, dry_run=False, count_only=False
):
    """Search and replace a string in all files in a directory."""

    # Make sure the root dir is a Path object
    if isinstance(root_dir, str):
        root_dir = Path(root_dir)

    # Count instances
    count = 0

    # Iterate over all files in the root directory
    for file_path in root_dir.rglob("*html"):
        if file_path.is_file():
            try:
                # Read the content of the file
                content = file_path.read_text(encoding="utf-8")

                # Count the number of instances of the old string
                if old_string in content:
                    count += 1

                if not dry_run and not count_only:
                    new_content = content.replace(old_string, new_string)
                    file_path.write_text(new_content, encoding="utf-8")
            except Exception as e:
                logger.warning(f"Skipping {file_path} due to error: {e}")

    # Log and return
    logger.info(f"Found '{old_string}' in {count} files")

    return count
