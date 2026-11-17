#!/usr/bin/env python3
"""
Export Research Desk artifact data to JSON for Supabase import.

This script should be run in a Claude session that has access to the
Research Desk artifact via the ArtifactData tool.

Usage:
    Ask Claude in the artifact session:
    "Run scripts/export_artifact_data.py to export all papers to migration_data.json"
"""

import json
import sys
from datetime import datetime

# This would be called via Claude's ArtifactData tool
# Example for Claude to execute:
#
# ArtifactData({
#   "action": "list",
#   "url": "https://claude.ai/artifact/YOUR_ARTIFACT_ID",
#   "collection": "data/papers",
#   "query": {"limit": 1000}
# })

def format_instructions():
    """Print instructions for manual export"""
    print("=" * 60)
    print("RESEARCH DESK DATA EXPORT")
    print("=" * 60)
    print("\nTo export your artifact data, in your Research Desk artifact session,")
    print("ask Claude to:\n")

    print("1. List all papers:")
    print("   'List all papers in the database and save to migration_data.json'\n")

    print("2. Claude will use ArtifactData tool to:")
    print("   - Read all papers from data/papers collection")
    print("   - Export figures metadata")
    print("   - Export fulltext if available")
    print("   - Save everything to migration_data.json\n")

    print("3. Download migration_data.json from that session\n")

    print("4. Import to Supabase:")
    print("   python scripts/import_to_supabase.py migration_data.json\n")

    print("=" * 60)
    print("\nExpected output format:")
    print("=" * 60)
    print("""
{
  "exported_at": "2024-11-17T10:00:00Z",
  "source": "Research Desk artifact",
  "total_papers": 20,
  "papers": [
    {
      "arxiv_id": "2611.12345",
      "title": "Paper Title",
      "authors": ["Author One", "Author Two"],
      "abstract": "Abstract text...",
      "cat": "cond-mat.mes-hall",
      "matched": ["keyword1", "keyword2"],
      "score": 5,
      "state": "saved",
      "week": "2024-11-11",
      "saved_at": "2024-11-11T10:00:00Z",
      "figures": [...],
      "text_parts": 0
    },
    ...
  ]
}
    """)

if __name__ == '__main__':
    format_instructions()
