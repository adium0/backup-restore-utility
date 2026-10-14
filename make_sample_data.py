#!/usr/bin/env python3
"""Creates a small 'sample_data' folder to use during the live demo."""

import os

FILES = {
    "Documents/notes.txt": "OS Lab notes\n- backups are versioned\n- unchanged files are hard-linked\n",
    "Documents/report_draft.txt": "Chapter 1: Introduction\nData loss is common...\n",
    "Projects/hello.py": "print('Hello from the backup demo')\n",
    "Projects/config.json": '{"theme": "dark", "autosave": true}\n',
    "Photos/holiday.jpg": None,   # binary placeholder
    ".DS_Store": "macOS junk file (should be skipped)",
    "temp_file.tmp": "temporary file (should be skipped)",
}


def main(root="sample_data"):
    for rel, content in FILES.items():
        path = os.path.join(root, rel)
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        if content is None:
            with open(path, "wb") as fh:
                fh.write(os.urandom(150_000))
        else:
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(content)
    print(f"Created demo folder '{root}' with {len(FILES)} files.")


if __name__ == "__main__":
    main()
