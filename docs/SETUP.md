# Detailed Setup Guide

This guide walks through every step to get Research Desk running from scratch.

## Prerequisites

- GitHub account
- Supabase account (free tier is sufficient)
- Git installed locally

## Part 1: Supabase Setup (10 minutes)

### 1.1 Create Supabase Project

1. Go to [supabase.com](https://supabase.com)
2. Click "Start your project"
3. Sign in with GitHub (recommended) or email
4. Click "New project"
5. Fill in:
   - **Name**: `research-desk` (or any name)
   - **Database Password**: Generate a strong password (save it somewhere safe)
   - **Region**: Choose closest to you
   - **Pricing Plan**: Free
6. Click "Create new project"
7. Wait 2-3 minutes for database provisioning

### 1.2 Run Database Schema

1. In your Supabase project, go to **SQL Editor** (left sidebar)
2. Click "New query"
3. Open `docs/supabase_schema.sql` from this repository
4. Copy the **entire file** (all ~142 lines)
5. Paste into the SQL Editor
6. Click "Run" (or press Ctrl+Enter / Cmd+Enter)
7. You should see: "Success. No rows returned"

**What this creates:**
- 5 tables: `papers`, `fulltext`, `runs`, `qa`, `library`
- Indexes for performance
- Row Level Security policies
- Storage bucket for figures
- Automatic timestamp triggers

### 1.3 Get API Credentials

1. Go to **Project Settings** (gear icon, bottom left)
2. Click **API** in the left menu
3. Copy these values (you'll need them later):

   **For GitHub Actions (backend):**
   - Project URL: `https://xxxxx.supabase.co`
   - `service_role` key: Under "Project API keys" → service_role (click "Reveal" to see it)
     - ⚠️ This is a secret key - never commit it to git!

   **For Frontend (browser):**
   - Project URL: Same as above
   - `anon` public key: Under "Project API keys" → anon public
     - ✅ This key is safe to put in public HTML

### 1.4 Verify Storage Bucket

1. Go to **Storage** (left sidebar)
2. You should see a bucket named `figures`
3. Click on it → Click "Policies" tab
4. Verify these policies exist:
   - "Public read figures" (SELECT for everyone)
   - "Service role upload figures" (INSERT for service_role)

If the bucket doesn't exist, the SQL script didn't run completely. Re-run it.

## Part 2: GitHub Repository Setup

### 2.1 Create Repository

1. Go to [github.com](https://github.com)
2. Click "+" → "New repository"
3. Name: `paper_databases` (or any name)
4. Visibility: Can be Public or Private (both work)
5. **Don't** initialize with README (we have one)
6. Click "Create repository"

### 2.2 Push Code

In your terminal, in the directory `/Users/shenyongye/Documents/GitHub/paper_databases`:

```bash
# Initialize git (if not already done)
git init

# Add all files
git add .

# Commit
git commit -m "Initial commit: Research Desk system"

# Add remote (replace YOUR-USERNAME with your GitHub username)
git remote add origin https://github.com/YOUR-USERNAME/paper_databases.git

# Push
git branch -M main
git push -u origin main
```

### 2.3 Add Secrets

1. In your GitHub repository, go to **Settings** tab
2. In left sidebar, expand **Secrets and variables** → Click **Actions**
3. Click "New repository secret"
4. Add first secret:
   - Name: `SUPABASE_URL`
   - Value: Your Supabase project URL (from Part 1.3)
   - Click "Add secret"
5. Click "New repository secret" again
6. Add second secret:
   - Name: `SUPABASE_KEY`
   - Value: Your Supabase **service_role** key (from Part 1.3)
   - Click "Add secret"

**Security Note**: These secrets are only accessible to GitHub Actions. They're never exposed in logs or to the public.

### 2.4 Enable GitHub Actions

1. Go to **Actions** tab
2. If you see "Workflows aren't being run on this forked repository", click "I understand my workflows, go ahead and enable them"
3. You should see "Daily arXiv Update" workflow listed

## Part 3: Configure Frontend

### 3.1 Edit HTML File

Open `frontend/index.html` in a text editor and find these lines (around line 15):

```javascript
const SUPABASE_URL = 'YOUR_SUPABASE_URL';
const SUPABASE_ANON_KEY = 'YOUR_SUPABASE_ANON_KEY';
```

Replace with your actual values:

```javascript
const SUPABASE_URL = 'https://xxxxx.supabase.co';  // From Part 1.3
const SUPABASE_ANON_KEY = 'eyJhbGc...';  // From Part 1.3 (anon key)
```

Save the file.

### 3.2 Commit Changes

```bash
git add frontend/index.html
git commit -m "Configure Supabase connection"
git push
```

### 3.3 Enable GitHub Pages

1. Go to **Settings** tab
2. In left sidebar, click **Pages**
3. Under "Build and deployment":
   - Source: "Deploy from a branch"
   - Branch: `main`
   - Folder: `/ (root)`
4. Click "Save"
5. Wait 1-2 minutes, then refresh the page
6. You should see: "Your site is live at https://YOUR-USERNAME.github.io/paper_databases/"

**Access your site:**
```
https://YOUR-USERNAME.github.io/paper_databases/frontend/
```

(Note the `/frontend/` at the end)

## Part 4: Test the System

### 4.1 Manual Workflow Run

1. Go to **Actions** tab
2. Click "Daily arXiv Update" workflow
3. Click "Run workflow" dropdown (on the right)
4. Click green "Run workflow" button
5. Refresh the page after a few seconds
6. Click on the running workflow to see live logs

**What it does:**
1. Fetches today's papers from arXiv RSS feeds
2. Downloads PDFs and extracts figures
3. Uploads figures to Supabase Storage
4. Writes paper metadata to database

**Expected duration:** 2-5 minutes depending on number of papers

### 4.2 Check Database

1. Go to Supabase → **Table Editor**
2. Select `papers` table
3. You should see new rows with today's papers

### 4.3 Check Frontend

1. Open your GitHub Pages URL: `https://YOUR-USERNAME.github.io/paper_databases/frontend/`
2. You should see the papers appear
3. Try clicking "Save" on a paper - it should change to "Saved ✓"
4. Refresh the page - saved state should persist

### 4.4 Check Figures

1. Click "Show" on a paper to expand it
2. Figures should load from Supabase Storage
3. If figures don't show:
   - Check browser console for errors (F12 → Console tab)
   - Go to Supabase → Storage → figures bucket
   - Verify files were uploaded (you should see folders like `2611.12345/`)

## Part 5: Import Existing Data (Optional)

If you have papers from the old artifact system:

### 5.1 Run Migration Script

```bash
# In your project directory
python scripts/migrate_from_artifact.py
```

This creates `migration_data.json` with all your papers.

### 5.2 Manual Import to Supabase

**Option A: Use Supabase SQL Editor**

1. Open `migration_data.json`
2. For each paper, run in SQL Editor:

```sql
INSERT INTO papers (arxiv_id, title, authors, abstract, cat, matched, score, state, week, saved_at, figures, text_parts)
VALUES (
  '2611.12345',
  'Paper Title',
  ARRAY['Author One', 'Author Two'],
  'Abstract text...',
  'cond-mat.mes-hall',
  ARRAY['graphene', 'bilayer'],
  5,
  'saved',
  '2024-11-11',
  '2024-11-11T10:00:00Z',
  '[{"n": 1, "caption": "Figure 1", "url": "..."}]'::jsonb,
  0
);
```

**Option B: Use Python Script** (easier for many papers)

Create `scripts/import_to_supabase.py`:

```python
import json
import os
from supabase import create_client

SUPABASE_URL = os.environ['SUPABASE_URL']
SUPABASE_KEY = os.environ['SUPABASE_KEY']
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

with open('migration_data.json') as f:
    data = json.load(f)

for paper in data['papers']:
    supabase.table('papers').upsert(paper).execute()
    print(f"Imported {paper['arxiv_id']}")
```

Run it:

```bash
export SUPABASE_URL='your-url'
export SUPABASE_KEY='your-service-role-key'
python scripts/import_to_supabase.py
```

## Part 6: Customize

### 6.1 Modify Keywords

Edit `data/keywords.json`:

```json
{
  "cond-mat.mes-hall": {
    "must": ["keyword1", "keyword2"],
    "any": ["keyword3", "keyword4"],
    "not": ["exclude1"]
  },
  "cond-mat.str-el": {
    "must": ["correlated"],
    "any": ["superconductor", "mott"]
  }
}
```

**Matching logic:**
- `must`: All keywords must appear
- `any`: At least one must appear
- `not`: None can appear

Commit and push:

```bash
git add data/keywords.json
git commit -m "Update keywords"
git push
```

### 6.2 Change Schedule

Edit `.github/workflows/daily-update.yml`:

```yaml
schedule:
  # Run at 10:00 UTC (06:00 Boston time) Mon-Fri
  - cron: '0 10 * * 1-5'
```

Cron syntax: `minute hour day-of-month month day-of-week`

Examples:
- `0 14 * * 1-5` = 14:00 UTC Mon-Fri (10:00 Boston)
- `0 6 * * *` = 06:00 UTC every day
- `30 8,14 * * 1-5` = 08:30 and 14:30 UTC Mon-Fri

Commit and push to activate new schedule.

### 6.3 Customize Frontend Styling

Edit `frontend/index.html` CSS section (look for `<style>` tag).

Key CSS variables:

```css
:root {
  --bg: #ffffff;
  --fg: #1a1a1a;
  --border: #e5e5e5;
  --accent: #2563eb;
  --saved: #16a34a;
}

@media (prefers-color-scheme: dark) {
  :root {
    --bg: #0a0a0a;
    --fg: #ededed;
    --border: #262626;
  }
}
```

## Troubleshooting

### Workflow fails with "SUPABASE_URL not found"

- Go to Settings → Secrets and variables → Actions
- Verify both secrets exist and are spelled exactly: `SUPABASE_URL` and `SUPABASE_KEY`

### Papers not appearing in frontend

1. Check GitHub Actions logs - did the workflow succeed?
2. Check Supabase Table Editor - are papers in the database?
3. Open browser console (F12) - any JavaScript errors?
4. Verify `SUPABASE_URL` and `SUPABASE_ANON_KEY` in `index.html` are correct

### Figures not loading

1. Check Supabase Storage → figures bucket
2. Verify "Public read figures" policy exists
3. Check browser console for CORS errors
4. Try accessing a figure URL directly in browser

### Database write fails with permission error

- Verify you're using `service_role` key (not `anon` key) in GitHub Secrets
- Check Row Level Security policies in Supabase

### "No papers to process" every day

- Check `data/keywords.json` - are keywords too restrictive?
- Verify arXiv RSS feeds are accessible (check workflow logs)
- Try expanding keywords or adding more categories

## Daily Operation

Once set up, the system runs automatically:

1. **Every weekday 10:00 UTC**: GitHub Actions fetches new papers
2. **Within 5 minutes**: Papers appear in your database
3. **Instant**: Frontend shows new papers on next page load
4. **Real-time**: Saved state syncs across devices via Supabase

You can:
- Access from any device at your GitHub Pages URL
- Save papers to review later
- Mark papers as "read" to hide them
- Click "Ask in Claude" to open a paper in claude.ai

## Support

If you encounter issues:

1. Check GitHub Actions logs for error messages
2. Check Supabase logs (Logs Explorer in dashboard)
3. Check browser console for frontend errors
4. Verify all credentials are correct

## Next Steps

- Set up email notifications for failed workflows (GitHub Actions settings)
- Add more arXiv categories to `data/keywords.json`
- Customize frontend styling to match your preferences
- Set up backup exports of your Supabase database
