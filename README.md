# Research Desk - arXiv Paper Digest

Automated daily digest of arXiv papers based on your research interests. Completely independent system running on GitHub Actions + Supabase + GitHub Pages.

## Features

- 📅 **Daily Updates**: Automated fetch from arXiv RSS feeds every weekday at 10:00 UTC
- 🎯 **Smart Filtering**: Keyword-based paper matching across multiple arXiv categories
- 🖼️ **Figure Extraction**: Automatic extraction of figures and full text from PDFs
- 💾 **Persistent State**: Save/read state synced across all devices via Supabase
- 🌐 **Public Access**: View your digest from any device via GitHub Pages
- 🤖 **Claude Integration**: "Ask in Claude" button for each paper
- 🔄 **Real-time Updates**: Live sync when papers are saved/read

## Quick Start

### 1. Set Up Supabase (5 minutes)

1. Go to [supabase.com](https://supabase.com) and create a free account
2. Create a new project
3. In the SQL Editor, paste and run the entire contents of `docs/supabase_schema.sql`
4. Go to Project Settings → API and copy:
   - Project URL (e.g., `https://xxxxx.supabase.co`)
   - `anon` public key (starts with `eyJ...`)

### 2. Configure GitHub Repository

1. Push this code to your GitHub repository
2. Go to Settings → Secrets and variables → Actions
3. Add two secrets:
   - `SUPABASE_URL`: Your Supabase project URL
   - `SUPABASE_KEY`: Your Supabase **service_role** key (from Project Settings → API, under "service_role")

### 3. Configure Frontend

Edit `frontend/index.html` and replace the placeholder values:

```javascript
const SUPABASE_URL = 'YOUR_SUPABASE_URL';  // Replace with your project URL
const SUPABASE_ANON_KEY = 'YOUR_SUPABASE_ANON_KEY';  // Replace with anon key
```

### 4. Enable GitHub Pages

1. Go to Settings → Pages
2. Source: Deploy from a branch
3. Branch: `main`, folder: `/ (root)`
4. Save

Your site will be available at: `https://[your-username].github.io/paper_databases/frontend/`

### 5. Import Existing Data (Optional)

If you have existing papers from the old artifact system:

```bash
python scripts/migrate_from_artifact.py
```

This will export your data to `migration_data.json` which you can then import to Supabase.

### 6. Manual First Run (Optional)

Trigger the workflow manually to test:

1. Go to Actions tab
2. Click "Daily arXiv Update"
3. Click "Run workflow"

Or wait for the next scheduled run (weekdays 10:00 UTC).

## Project Structure

```
paper_databases/
├── .github/workflows/
│   └── daily-update.yml      # GitHub Actions workflow
├── scripts/
│   ├── fetcher.py            # Fetch papers from arXiv RSS
│   ├── extract_figs.py       # Extract figures from PDFs
│   ├── digest.py             # Plan extraction work
│   ├── run_daily.py          # Main orchestration script
│   └── migrate_from_artifact.py  # Data migration tool
├── data/
│   └── keywords.json         # Your keyword filters
├── docs/
│   ├── supabase_schema.sql   # Database schema
│   └── SETUP.md              # Detailed setup guide
├── frontend/
│   └── index.html            # Static web interface
└── requirements.txt          # Python dependencies
```

## How It Works

1. **GitHub Actions** runs `scripts/run_daily.py` every weekday at 10:00 UTC
2. **Fetcher** downloads papers from arXiv RSS feeds matching your keywords
3. **Extractor** downloads PDFs and extracts figures + full text using PyMuPDF
4. **Storage**: 
   - Figures uploaded to Supabase Storage bucket `figures/`
   - Full text stored in `fulltext` table (chunked if large)
   - Paper metadata in `papers` table
5. **Frontend** loads papers from Supabase and displays them
6. **State** (saved/week/read) persists to Supabase when you interact with papers

## Customization

### Add/Remove Keywords

Edit `data/keywords.json`:

```json
{
  "cond-mat.mes-hall": {
    "must": ["graphene", "bilayer"],
    "any": ["moiré", "magic angle"],
    "not": ["simulation"]
  }
}
```

### Change Schedule

Edit `.github/workflows/daily-update.yml`:

```yaml
schedule:
  - cron: '0 10 * * 1-5'  # 10:00 UTC Mon-Fri
```

### Adjust Figure Extraction

Edit `scripts/extract_figs.py` to change:
- Minimum figure size
- DPI settings
- Text chunk size

## Troubleshooting

### No papers appearing?

1. Check Actions tab for workflow errors
2. Verify Supabase secrets are set correctly
3. Check if arXiv RSS feeds are accessible

### Frontend not loading?

1. Verify `SUPABASE_URL` and `SUPABASE_ANON_KEY` are set in `index.html`
2. Check browser console for CORS errors
3. Ensure GitHub Pages is enabled

### Figures not showing?

1. Check Supabase Storage → `figures` bucket exists
2. Verify bucket is set to public access
3. Check GitHub Actions logs for upload errors

## Support

For detailed setup instructions, see `docs/SETUP.md`.

## License

MIT License - feel free to modify and use for your research.
