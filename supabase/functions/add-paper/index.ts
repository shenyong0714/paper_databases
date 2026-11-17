// Research Desk: add a paper by link (arXiv, DOI, or a journal article URL) straight into the Archive.
// Resolves metadata via Semantic Scholar, Crossref and the arXiv API; prefers the arXiv id as the key
// so the daily pipeline can extract figures and full text from the preprint.
import { createClient } from "jsr:@supabase/supabase-js@2";

const UA = "research-desk/1.0 (+https://github.com/shenyong0714/paper_databases)";
const cors = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers": "authorization, x-client-info, apikey, content-type",
  "Access-Control-Allow-Methods": "POST, OPTIONS",
};
const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { ...cors, "Content-Type": "application/json" } });

const ARXIV_RE = /(?:arxiv\.org\/(?:abs|pdf|html)\/|arxiv:\s*|^)(\d{4}\.\d{4,5})(?:v\d+)?/i;
const DOI_RE = /\b(10\.\d{4,9}\/[^\s"'<>#?]+)/;

type Meta = {
  title?: string; abstract?: string; authors?: string[]; doi?: string; journal?: string;
  year?: number; arxiv?: string; pdf_url?: string; cat?: string; url?: string;
};

async function getJSON(url: string, timeoutMs = 15000) {
  // Semantic Scholar's shared pool answers 429 under load: retry a few times
  for (let i = 0; ; i++) {
    const r = await fetch(url, { headers: { "User-Agent": UA }, signal: AbortSignal.timeout(timeoutMs) });
    if (r.ok) return r.json();
    if (i < 3 && (r.status === 429 || r.status >= 500)) { await new Promise((z) => setTimeout(z, 1500 * (i + 1))); continue; }
    throw new Error(`${new URL(url).host} ${r.status}`);
  }
}
async function getText(url: string, timeoutMs = 15000) {
  const r = await fetch(url, { headers: { "User-Agent": UA }, signal: AbortSignal.timeout(timeoutMs) });
  if (!r.ok) throw new Error(`${new URL(url).host} ${r.status}`);
  return r.text();
}
const clean = (s?: string) => (s || "").replace(/<[^>]+>/g, " ").replace(/\s+/g, " ").trim();
const norm = (s: string) => s.toLowerCase().replace(/\$[^$]*\$/g, "").replace(/[^a-z0-9]+/g, " ").trim();

// ---------- turn whatever was pasted into an arXiv id or a DOI
async function parseInput(raw: string): Promise<{ arxiv?: string; doi?: string }> {
  const s = decodeURIComponent(raw.trim());
  const a = s.match(ARXIV_RE);
  if (a && (/arxiv/i.test(s) || /^\d{4}\.\d{4,5}(v\d+)?$/.test(s))) return { arxiv: a[1] };
  const d = s.match(DOI_RE);
  if (d) return { doi: d[1].replace(/(\.pdf|\/(full|abstract|epdf|pdf))$/i, "").replace(/[.,;)]+$/, "") };
  const nat = s.match(/nature\.com\/articles\/([a-z0-9.\-]+)/i);
  if (nat) return { doi: `10.1038/${nat[1]}` };
  if (/^https?:\/\//i.test(s)) {           // last resort: read the page's citation meta tags
    try {
      const html = await getText(s);
      const m = html.match(/<meta[^>]+name=["'](?:citation_doi|dc\.identifier|prism\.doi)["'][^>]+content=["'](?:doi:)?([^"']+)["']/i);
      if (m && DOI_RE.test(m[1])) return { doi: m[1].match(DOI_RE)![1] };
      const ax = html.match(/<meta[^>]+name=["']citation_arxiv_id["'][^>]+content=["']([^"']+)["']/i);
      if (ax) return { arxiv: ax[1].replace(/v\d+$/, "") };
    } catch (_) { /* fall through */ }
  }
  throw new Error("Could not find an arXiv id or DOI in that link");
}

// ---------- metadata sources
async function semanticScholar(key: string): Promise<Meta> {
  const f = "title,abstract,authors,externalIds,venue,year,openAccessPdf,journal";
  const p = await getJSON(`https://api.semanticscholar.org/graph/v1/paper/${encodeURI(key)}?fields=${f}`);
  return {
    title: p.title, abstract: p.abstract || undefined, authors: (p.authors || []).map((a: any) => a.name),
    doi: p.externalIds?.DOI, arxiv: p.externalIds?.ArXiv, journal: p.journal?.name || p.venue || undefined,
    year: p.year || undefined, pdf_url: p.openAccessPdf?.url || undefined,
  };
}
async function crossref(doi: string): Promise<Meta> {
  const m = (await getJSON(`https://api.crossref.org/works/${encodeURIComponent(doi)}`)).message;
  return {
    title: clean((m.title || [])[0]), abstract: clean(m.abstract) || undefined,
    authors: (m.author || []).map((a: any) => [a.given, a.family].filter(Boolean).join(" ")),
    journal: (m["container-title"] || [])[0], year: m.issued?.["date-parts"]?.[0]?.[0], doi: m.DOI,
    url: m.URL,
  };
}
async function arxivById(id: string): Promise<Meta> {
  const x = await getText(`https://export.arxiv.org/api/query?id_list=${id}&max_results=1`);
  const entry = x.split("<entry>")[1];
  if (!entry) throw new Error(`arXiv:${id} not found`);
  const tag = (t: string) => clean((entry.match(new RegExp(`<${t}[^>]*>([\\s\\S]*?)</${t}>`)) || [])[1]);
  return {
    title: tag("title"), abstract: tag("summary"),
    authors: [...entry.matchAll(/<name>([\s\S]*?)<\/name>/g)].map((m) => clean(m[1])),
    cat: (entry.match(/arxiv:primary_category[^>]*term="([^"]+)"/) || [])[1], arxiv: id,
    doi: tag("arxiv:doi") || undefined, journal: tag("arxiv:journal_ref") || undefined,
    year: +(tag("published").slice(0, 4)) || undefined,
  };
}
// Journal titles often differ from the preprint's, so match on title words *and* authors.
async function arxivByTitle(title: string, authors: string[] = []): Promise<string | undefined> {
  const words = norm(title).split(" ").filter((w) => w.length > 3);
  if (words.length < 2) return;
  const surname = (a: string) => norm(a).split(" ").pop() || "";
  const sur = authors.map(surname).filter(Boolean);
  const queries = [words.slice(0, 8).map((w) => `ti:${w}`).join("+AND+")];
  if (sur[0]) queries.push(`au:${sur[0]}+AND+(${words.slice(0, 6).map((w) => `ti:${w}`).join("+OR+")})`);
  const tw = new Set(words);
  let best: [number, string] | undefined;
  for (const q of queries) {
    const x = await getText(`https://export.arxiv.org/api/query?search_query=${q}&max_results=10`).catch(() => "");
    for (const e of x.split("<entry>").slice(1)) {
      const t = clean((e.match(/<title>([\s\S]*?)<\/title>/) || [])[1]);
      const id = (e.match(/arxiv\.org\/abs\/(\d{4}\.\d{4,5})/) || [])[1];
      if (!id) continue;
      const ew = new Set(norm(t).split(" ").filter((w) => w.length > 3));
      const inter = [...tw].filter((w) => ew.has(w)).length;
      const tsim = inter / Math.max(1, Math.min(tw.size, ew.size));
      const ea = [...e.matchAll(/<name>([\s\S]*?)<\/name>/g)].map((m) => surname(clean(m[1])));
      const asim = sur.length ? sur.filter((s) => ea.includes(s)).length / sur.length : 0;
      const score = norm(t) === norm(title) ? 2 : (asim >= 0.5 && tsim >= 0.4 ? tsim + asim : 0);
      if (score && (!best || score > best[0])) best = [score, id];
    }
    if (best) return best[1];
    await new Promise((z) => setTimeout(z, 1000));    // arXiv API asks for gaps between calls
  }
}

async function resolve(raw: string): Promise<Meta> {
  const inp = await parseInput(raw);
  let m: Meta = {};
  const merge = (o: Meta) => { for (const [k, v] of Object.entries(o)) if (v && !(m as any)[k]) (m as any)[k] = v; };
  if (inp.doi) {
    m.doi = inp.doi;
    // Semantic Scholar first (it knows the arXiv twin), then Crossref fills the gaps
    await semanticScholar(`DOI:${inp.doi}`).then(merge).catch(() => {});
    // Crossref is authoritative for where/when it was published (Semantic Scholar often has the preprint year)
    await crossref(inp.doi).then((c) => { merge(c); if (c.year) m.year = c.year; if (c.journal) m.journal = c.journal; }).catch(() => {});
    if (!m.title) throw new Error(`No paper found for DOI ${inp.doi}`);
    if (!m.arxiv) m.arxiv = await arxivByTitle(m.title, m.authors).catch(() => undefined);
    if (m.arxiv) {               // the preprint has the cleanest abstract and a PDF we can always fetch
      const a = await arxivById(m.arxiv).catch(() => ({} as Meta));
      m.cat = a.cat; if (a.abstract) m.abstract = m.abstract || a.abstract;
    }
  } else {
    m = await arxivById(inp.arxiv!);
    const s = await semanticScholar(`ARXIV:${inp.arxiv}`).catch(() => ({} as Meta));
    if (s.doi) { m.doi = s.doi; m.journal = s.journal || m.journal; m.year = s.year || m.year; }
  }
  return m;
}

function todayET() {
  return new Date().toLocaleDateString("en-CA", { timeZone: "America/New_York" }); // YYYY-MM-DD
}
function isoWeek(d = new Date()) {
  const t = new Date(Date.UTC(d.getFullYear(), d.getMonth(), d.getDate()));
  const day = (t.getUTCDay() + 6) % 7; t.setUTCDate(t.getUTCDate() - day + 3);
  const y = t.getUTCFullYear(); const jan4 = new Date(Date.UTC(y, 0, 4));
  const w = 1 + Math.round(((t.getTime() - jan4.getTime()) / 864e5 - 3 + ((jan4.getUTCDay() + 6) % 7)) / 7);
  return `${y}-W${String(w).padStart(2, "0")}`;
}

Deno.serve(async (req) => {
  if (req.method === "OPTIONS") return new Response("ok", { headers: cors });
  if (req.method !== "POST") return json({ error: "POST only" }, 405);
  try {
    const { link, dry } = await req.json();
    if (typeof link !== "string" || !link.trim() || link.length > 2000) return json({ error: "Paste a link or DOI" }, 400);

    const m = await resolve(link);
    const id = m.arxiv || `doi:${m.doi!.toLowerCase()}`;
    if (dry) return json({ id, meta: m });               // preview only, nothing written
    const sb = createClient(Deno.env.get("SUPABASE_URL")!, Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!);
    const now = new Date().toISOString();

    const { data: old } = await sb.from("papers").select("arxiv_id,state,doi,journal").eq("arxiv_id", id).maybeSingle();
    if (old) {
      const patch: Record<string, unknown> = { state: "saved" };
      if (old.state !== "saved") patch.saved_at = now;
      if (!old.doi && m.doi) patch.doi = m.doi;
      if (!old.journal && m.journal) patch.journal = m.journal;
      const { data, error } = await sb.from("papers").update(patch).eq("arxiv_id", id).select().single();
      if (error) throw error;
      return json({ paper: data, existed: true });
    }

    const row = {
      arxiv_id: id, title: m.title, abstract: m.abstract || "", authors: m.authors || [],
      cat: m.cat || m.journal || "", score: 0, matched: [], state: "saved", saved_at: now,
      week: isoWeek(), announced: todayET(), source: "manual",
      doi: m.doi || null, journal: m.journal || null, year: m.year || null,
      url: m.doi ? `https://doi.org/${m.doi}` : `https://arxiv.org/abs/${m.arxiv}`,
      pdf_url: m.arxiv ? null : (m.pdf_url || null),
    };
    const { data, error } = await sb.from("papers").insert(row).select().single();
    if (error) throw error;
    return json({ paper: data, existed: false });
  } catch (e) {
    return json({ error: (e as Error).message || String(e) }, 422);
  }
});
