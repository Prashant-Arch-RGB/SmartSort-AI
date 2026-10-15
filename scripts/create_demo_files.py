"""
create_demo_files.py — Create a temporary demo folder with mixed file types.

Run from the project root:
    python scripts/create_demo_files.py

This creates a 'demo_files/Unorganised' folder in the project root with
synthetic files that can be safely scanned and organized without touching
any real user data.
"""

import sys
import os
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

DEMO_DIR = ROOT / "demo_files" / "Unorganised"


def create_demo_files() -> None:
    DEMO_DIR.mkdir(parents=True, exist_ok=True)
    print(f"Creating demo files in: {DEMO_DIR}")

    # Text documents
    (DEMO_DIR / "lecture_notes_algorithms.txt").write_text(
        "Lecture notes: Introduction to Algorithms\n"
        "Chapter 1: Sorting algorithms — bubble sort, merge sort, quicksort\n"
        "Chapter 2: Searching — binary search, hash tables\n"
        "Assignment due next week: implement merge sort in Python.\n",
        encoding="utf-8",
    )

    (DEMO_DIR / "invoice_2024_001.txt").write_text(
        "INVOICE #2024-001\n"
        "Vendor: Acme Corp\n"
        "Amount Due: $1,250.00\n"
        "Payment Terms: Net 30\n"
        "Description: Software license renewal\n",
        encoding="utf-8",
    )

    (DEMO_DIR / "project_proposal.txt").write_text(
        "Project Proposal: Website Redesign\n"
        "Client: BigCo Inc\n"
        "Timeline: 12 weeks\n"
        "Deliverables: wireframes, design mockups, development, testing\n"
        "Budget: $45,000\n",
        encoding="utf-8",
    )

    (DEMO_DIR / "personal_journal.txt").write_text(
        "Dear Diary,\n"
        "Today was a wonderful day. I went for a walk in the park,\n"
        "had coffee with Sarah, and finished reading my novel.\n"
        "Feeling grateful for good friends and sunny weather.\n",
        encoding="utf-8",
    )

    (DEMO_DIR / "bank_statement.txt").write_text(
        "Bank Statement - Account: 1234-5678\n"
        "Period: January 2024\n"
        "Opening Balance: $5,000.00\n"
        "Deposits: $3,200.00\n"
        "Withdrawals: $2,150.00\n"
        "Closing Balance: $6,050.00\n",
        encoding="utf-8",
    )

    (DEMO_DIR / "study_notes.md").write_text(
        "# Biology Study Notes\n\n"
        "## Chapter 3: Genetics\n"
        "- DNA double helix structure discovered by Watson and Crick\n"
        "- Chromosomes carry genetic information\n"
        "- Exam topics: meiosis, mitosis, Punnett squares\n\n"
        "## Chapter 4: Cell Biology\n"
        "- Organelles: mitochondria, nucleus, ribosomes\n",
        encoding="utf-8",
    )

    (DEMO_DIR / "script.py").write_text(
        "#!/usr/bin/env python3\n"
        "\"\"\"A simple Python script.\"\"\"\n\n"
        "def greet(name: str) -> str:\n"
        "    return f'Hello, {name}!'\n\n"
        "if __name__ == '__main__':\n"
        "    print(greet('World'))\n",
        encoding="utf-8",
    )

    (DEMO_DIR / "config.json").write_text(
        '{\n  "app": "MyApp",\n  "version": "1.0",\n  "debug": false\n}\n',
        encoding="utf-8",
    )

    # Simulated binary files by extension (empty content — just checking extension rules)
    (DEMO_DIR / "photo_vacation.jpg").write_bytes(b"\xff\xd8\xff\xe0" + b"\x00" * 16)
    (DEMO_DIR / "presentation.pptx").write_bytes(b"PK" + b"\x00" * 20)
    (DEMO_DIR / "music_track.mp3").write_bytes(b"ID3" + b"\x00" * 20)
    (DEMO_DIR / "backup.zip").write_bytes(b"PK\x03\x04" + b"\x00" * 20)
    (DEMO_DIR / "video_clip.mp4").write_bytes(b"\x00\x00\x00\x20ftyp" + b"\x00" * 20)

    # Create a duplicate pair
    content = b"This is a duplicate file content used for testing duplicate detection.\n"
    (DEMO_DIR / "report_draft.txt").write_bytes(content)
    (DEMO_DIR / "report_draft_copy.txt").write_bytes(content)

    # A deeply nested file (for recursive scan testing)
    nested = DEMO_DIR / "subfolder" / "nested"
    nested.mkdir(parents=True, exist_ok=True)
    (nested / "nested_document.txt").write_text(
        "This document is in a nested subfolder.\n"
        "Tax form W-2 income salary deductions annual return.\n",
        encoding="utf-8",
    )

    files = list(DEMO_DIR.rglob("*"))
    file_count = sum(1 for f in files if f.is_file())
    print(f"[OK] Created {file_count} demo files in {DEMO_DIR}")
    print("\nYou can now scan this folder in SmartSort AI:")
    print(f"  {DEMO_DIR}")
    print("\nTo delete demo files when done:")
    print(f"  Remove-Item -Recurse -Force \"{DEMO_DIR}\"")


if __name__ == "__main__":
    create_demo_files()
