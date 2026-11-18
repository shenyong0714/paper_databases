-- Research Desk Database Schema for Supabase
-- Run this in your Supabase SQL Editor

-- Enable Row Level Security
ALTER DATABASE postgres SET statement_timeout = '60s';

-- Papers table
CREATE TABLE IF NOT EXISTS papers (
    arxiv_id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    authors TEXT[] NOT NULL,
    abstract TEXT,
    cat TEXT,
    matched TEXT[],
    score INTEGER DEFAULT 3,
    state TEXT DEFAULT 'week',
    week TEXT,
    saved_at TIMESTAMPTZ,
    figures JSONB,
    text_parts INTEGER DEFAULT 0,
    text_url TEXT,
    extract_error TEXT,
    extracted_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Fulltext table (stores paper text in chunks)
CREATE TABLE IF NOT EXISTS fulltext (
    id TEXT PRIMARY KEY,  -- format: {arxiv_id}__{part_number}
    arxiv_id TEXT NOT NULL,
    part INTEGER NOT NULL,
    text TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Runs table (daily update logs)
CREATE TABLE IF NOT EXISTS runs (
    date DATE PRIMARY KEY,
    at TIMESTAMPTZ NOT NULL,
    feeds_ok TEXT[],
    feeds_failed TEXT[],
    fetched INTEGER DEFAULT 0,
    kept INTEGER DEFAULT 0,
    added INTEGER DEFAULT 0,
    extracted INTEGER DEFAULT 0,
    updated INTEGER DEFAULT 0,
    errors JSONB
);

-- Q&A table (questions asked to papers)
CREATE TABLE IF NOT EXISTS qa (
    id TEXT PRIMARY KEY,  -- format: {arxiv_id}__{timestamp}
    arxiv_id TEXT NOT NULL,
    q TEXT NOT NULL,
    a TEXT,
    quote TEXT,
    verified BOOLEAN DEFAULT FALSE,
    at TIMESTAMPTZ DEFAULT NOW()
);

-- Library table (Zotero imports, if needed later)
CREATE TABLE IF NOT EXISTS library (
    zotero_key TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    authors TEXT[],
    abstract TEXT,
    year TEXT,
    journal TEXT,
    doi TEXT,
    url TEXT,
    collections TEXT[],
    zotero_tags TEXT[],
    annotations JSONB,
    source TEXT DEFAULT 'zotero',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Indexes for performance
CREATE INDEX IF NOT EXISTS idx_papers_state ON papers(state);
CREATE INDEX IF NOT EXISTS idx_papers_week ON papers(week);
CREATE INDEX IF NOT EXISTS idx_papers_score ON papers(score DESC);
CREATE INDEX IF NOT EXISTS idx_fulltext_arxiv ON fulltext(arxiv_id);
CREATE INDEX IF NOT EXISTS idx_qa_arxiv ON qa(arxiv_id);
CREATE INDEX IF NOT EXISTS idx_runs_date ON runs(date DESC);

-- Enable Row Level Security (RLS)
ALTER TABLE papers ENABLE ROW LEVEL SECURITY;
ALTER TABLE fulltext ENABLE ROW LEVEL SECURITY;
ALTER TABLE runs ENABLE ROW LEVEL SECURITY;
ALTER TABLE qa ENABLE ROW LEVEL SECURITY;
ALTER TABLE library ENABLE ROW LEVEL SECURITY;

-- Public read access (anyone can view)
CREATE POLICY "Public read access" ON papers FOR SELECT USING (true);
CREATE POLICY "Public read access" ON fulltext FOR SELECT USING (true);
CREATE POLICY "Public read access" ON runs FOR SELECT USING (true);
CREATE POLICY "Public read access" ON qa FOR SELECT USING (true);
CREATE POLICY "Public read access" ON library FOR SELECT USING (true);

-- Service role can write (for GitHub Actions)
CREATE POLICY "Service role write" ON papers FOR ALL USING (auth.role() = 'service_role');
CREATE POLICY "Service role write" ON fulltext FOR ALL USING (auth.role() = 'service_role');
CREATE POLICY "Service role write" ON runs FOR ALL USING (auth.role() = 'service_role');
CREATE POLICY "Service role write" ON qa FOR ALL USING (auth.role() = 'service_role');
CREATE POLICY "Service role write" ON library FOR ALL USING (auth.role() = 'service_role');

-- Authenticated users can save/unsave papers and ask questions
CREATE POLICY "Users can update paper state" ON papers FOR UPDATE
    USING (auth.role() = 'authenticated')
    WITH CHECK (auth.role() = 'authenticated');

CREATE POLICY "Users can insert QA" ON qa FOR INSERT
    WITH CHECK (auth.role() = 'authenticated');

-- Storage bucket for figures
-- Run this in Supabase Storage settings or via SQL:
INSERT INTO storage.buckets (id, name, public)
VALUES ('figures', 'figures', true)
ON CONFLICT DO NOTHING;

-- Storage policies
CREATE POLICY "Public read figures" ON storage.objects FOR SELECT
    USING (bucket_id = 'figures');

CREATE POLICY "Service role upload figures" ON storage.objects FOR INSERT
    WITH CHECK (bucket_id = 'figures' AND auth.role() = 'service_role');

-- Auto-update timestamp trigger
CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER papers_updated_at
    BEFORE UPDATE ON papers
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at();

-- 2026-11-17: arXiv listing date (US Eastern) used to group "This week" by day and to prune
alter table papers add column if not exists announced date;
create index if not exists papers_announced_idx on papers (announced);

-- 2026-11-17: papers added by link (journal / DOI). Key is the arXiv id when a preprint exists,
-- otherwise 'doi:<doi>'. Edge function: supabase/functions/add-paper
alter table papers
  add column if not exists doi text,
  add column if not exists journal text,
  add column if not exists year int,
  add column if not exists url text,
  add column if not exists pdf_url text,
  add column if not exists source text not null default 'digest';

-- 2026-11-17: locked to the owner's account (see migration lock_to_owner in Supabase):
-- is_owner() = auth.uid() of the owner; owner-only select/update policies on papers, fulltext,
-- runs, qa, library; ask_paper(p_id, p_key) security-definer RPC for the Ask userscript,
-- key hash in app_keys (RLS on, no policies). Pipeline + add-paper use the service role.
