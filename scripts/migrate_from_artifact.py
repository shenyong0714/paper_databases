#!/usr/bin/env python3
"""
Migrate data from Research Desk artifact database to JSON for Supabase import.

This script exports all papers from the artifact's database to a JSON file
that can be imported into Supabase.

Note: This script is designed to be run once during migration. After migration,
all data will live in Supabase and this script won't be needed.
"""

import json
import sys
from datetime import datetime

def main():
    print("Research Desk Migration Tool")
    print("=" * 60)
    print("\nThis script exports papers from the artifact database.")
    print("Note: This requires the artifact to still be accessible.\n")

    # This is a template script. In practice, you would:
    # 1. Run this in the claude.ai session that has the artifact
    # 2. Use ArtifactData tool to export all papers
    # 3. Save to migration_data.json

    print("INSTRUCTIONS:")
    print("=" * 60)
    print("\nSince this script runs locally but artifact data is in claude.ai,")
    print("you need to export the data manually:\n")

    print("1. Open your Research Desk artifact in claude.ai")
    print("2. Ask Claude: 'Export all papers from the database to JSON'")
    print("3. Claude will create a migration_data.json file")
    print("4. Download that file to this directory")
    print("5. Then you can import it to Supabase\n")

    print("ALTERNATIVE - If you have direct access to artifact:")
    print("=" * 60)
    print("\nIf running in a Claude session with ArtifactData tool:")
    print("```python")
    print("from artifact_data import read_all_papers")
    print("papers = read_all_papers()")
    print("with open('migration_data.json', 'w') as f:")
    print("    json.dump({'papers': papers, 'exported_at': datetime.utcnow().isoformat()}, f, indent=2)")
    print("```\n")

    # Template output structure
    template = {
        "exported_at": datetime.utcnow().isoformat(),
        "source": "Research Desk artifact",
        "papers": [
            {
                "arxiv_id": "2611.12345",
                "title": "Example Paper Title",
                "authors": ["Author One", "Author Two"],
                "abstract": "Paper abstract...",
                "cat": "cond-mat.mes-hall",
                "matched": ["keyword1", "keyword2"],
                "score": 5,
                "state": "saved",
                "week": "2024-11-11",
                "saved_at": "2024-11-11T10:00:00Z",
                "figures": [
                    {
                        "n": 1,
                        "caption": "Figure 1: ...",
                        "url": "https://supabase.co/storage/v1/object/public/figures/2611.12345/fig01.png"
                    }
                ],
                "text_parts": 0,
                "text_url": None,
                "extract_error": None,
                "extracted_at": None
            }
        ]
    }

    # Save template
    template_file = "migration_data_template.json"
    with open(template_file, 'w') as f:
        json.dump(template, f, indent=2)

    print(f"Created template file: {template_file}")
    print("\nEdit this template with your actual paper data,")
    print("or use the Claude session method described above.\n")

    return 0

if __name__ == '__main__':
    sys.exit(main())
