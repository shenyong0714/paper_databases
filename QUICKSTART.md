# Quick Start Guide - Research Desk

Get your independent Research Desk running in 15 minutes.

## Prerequisites

- GitHub account
- Supabase account (free tier)
- Local directory: `/Users/shenyongye/Documents/GitHub/paper_databases`

## 5-Step Setup

### 1. Supabase Setup (5 min)

```bash
# 1. Create account at supabase.com
# 2. Create new project
# 3. In SQL Editor, run: docs/supabase_schema.sql
# 4. Copy from Project Settings → API:
#    - Project URL
#    - anon key (for frontend)
#    - service_role key (for GitHub Actions)
```

### 2. Local Setup (2 min)

```bash
cd /Users/shenyongye/Documents/GitHub/paper_databases

# Copy all files from Claude's workspace to here
# (Claude will provide the exact copy command)

# Initialize git if not done
git init
git add .
git commit -m "Initial commit: Research Desk"
```

### 3. GitHub Setup (3 min)

```bash
# Create repo on GitHub
# Push code
git remote add origin https://github.com/YOUR-USERNAME/paper_databases.git
git push -u origin main

# Add secrets in GitHub Settings → Secrets → Actions:
# - SUPABASE_URL: your Supabase project URL
# - SUPABASE_KEY: your Supabase service_role key
```

### 4. Configure Frontend (2 min)

Edit `frontend/index.html` lines 15-16:

```javascript
const SUPABASE_URL = 'https://xxxxx.supabase.co';  // Your URL
const SUPABASE_ANON_KEY = 'eyJ...';  // Your anon key
```

Commit and push:

```bash
git add frontend/index.html
git commit -m "Configure Supabase"
git push
```

### 5. Enable GitHub Pages (3 min)

```bash
# In GitHub repo:
# Settings → Pages
# Source: main branch, / (root)
# Save

# Your site will be at:
# https://YOUR-USERNAME.github.io/paper_databases/frontend/
```

## First Run

Trigger manually in GitHub Actions tab:

```
Actions → Daily arXiv Update → Run workflow
```

Wait 2-5 minutes, then visit your GitHub Pages URL to see papers!

## Migration (Optional)

If you have existing artifact data:

```bash
# In your old artifact session, ask Claude:
"Export all papers to migration_data.json"

# Then import:
export SUPABASE_URL='your-url'
export SUPABASE_KEY='your-service-role-key'
python scripts/import_to_supabase.py migration_data.json
```

## Daily Operation

- **Automated**: GitHub Actions fetches papers every weekday 10:00 UTC
- **Access**: Visit your GitHub Pages URL from any device
- **State**: Save/read state syncs automatically via Supabase
- **Claude**: Click "Ask in Claude" button on any paper

## Troubleshooting

| Problem | Solution |
|---------|----------|
| No papers appearing | Check GitHub Actions logs |
| Frontend not loading | Verify Supabase keys in index.html |
| Workflow fails | Check GitHub Secrets are set |
| Figures not showing | Check Supabase Storage → figures bucket |

## Files Overview

```
📁 .github/workflows/     # GitHub Actions automation
📁 scripts/              # Python scripts for fetching/extracting
📁 data/                 # keywords.json configuration
📁 docs/                 # Setup guides and SQL schema
📁 frontend/             # Static website (index.html)
📄 requirements.txt      # Python dependencies
📄 README.md            # Full documentation
📄 QUICKSTART.md        # This file
```

## Next Steps

1. Customize `data/keywords.json` with your research interests
2. Adjust schedule in `.github/workflows/daily-update.yml`
3. Customize frontend styling in `frontend/index.html`

For detailed instructions, see `README.md` and `docs/SETUP.md`.
