import { useEffect, useRef, useState, type FormEvent } from 'react';

const PAGE_SIZE = 10;
const MAX_PAGES = 10;
const TIMEOUT_MS = 15000;
type Work = { id?: unknown; display_name?: unknown; title?: unknown; publication_year?: unknown; cited_by_count?: unknown; authorships?: unknown; doi?: unknown; primary_location?: unknown };
type SearchResult = { results: Work[]; count: number };

function safeLink(value: unknown): string | undefined {
  if (typeof value !== 'string') return undefined;
  try { const url = new URL(value); return url.protocol === 'https:' && !url.username && !url.password ? url.href : undefined; } catch { return undefined; }
}
function authors(value: unknown): string {
  if (!Array.isArray(value)) return 'Authors unavailable';
  const names = value.slice(0, 20).flatMap(item => typeof item?.author?.display_name === 'string' ? [item.author.display_name] : []);
  return names.length ? `${names.join(', ')}${value.length > 20 ? ', …' : ''}` : 'Authors unavailable';
}

export default function LiveResearchExplorer() {
  const [topic, setTopic] = useState('');
  const [year, setYear] = useState('');
  const [active, setActive] = useState<{ topic: string; year: string } | null>(null);
  const [page, setPage] = useState(1);
  const [data, setData] = useState<SearchResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const request = useRef<AbortController | null>(null);
  const sequence = useRef(0);

  function cancel() { sequence.current += 1; request.current?.abort(); request.current = null; }
  useEffect(() => () => cancel(), []);
  function changeInput() { cancel(); setLoading(false); setError(''); setActive(null); setData(null); }

  async function search(searchTopic: string, searchYear: string, nextPage: number) {
    cancel();
    const current = sequence.current;
    const controller = new AbortController(); request.current = controller;
    let timedOut = false;
    const timeout = window.setTimeout(() => { timedOut = true; controller.abort(); }, TIMEOUT_MS);
    setLoading(true); setError(''); setData(null);
    try {
      const params = new URLSearchParams({ search: searchTopic, page: String(nextPage), per_page: String(PAGE_SIZE), select: 'id,display_name,publication_year,cited_by_count,authorships,doi,primary_location' });
      if (searchYear) params.set('filter', `publication_year:${searchYear}`);
      const response = await fetch(`https://api.openalex.org/works?${params}`, { signal: controller.signal, credentials: 'omit' });
      if (response.status === 429) throw new Error('OpenAlex rate limit or anonymous daily budget reached. Please wait and try again later.');
      if (!response.ok) throw new Error(`OpenAlex is unavailable (HTTP ${response.status}). Please try again later.`);
      const payload: unknown = await response.json();
      if (!payload || typeof payload !== 'object' || !('results' in payload) || !Array.isArray(payload.results) || !('meta' in payload) || !payload.meta || typeof payload.meta !== 'object' || !('count' in payload.meta) || typeof payload.meta.count !== 'number') throw new Error('OpenAlex returned an unexpected response. Please try again later.');
      if (sequence.current !== current) return;
      setData({ results: payload.results.filter((item): item is Work => !!item && typeof item === 'object').slice(0, PAGE_SIZE), count: payload.meta.count });
      setPage(nextPage); setActive({ topic: searchTopic, year: searchYear });
    } catch (err) {
      if (sequence.current !== current) return;
      setError(timedOut ? 'The OpenAlex request timed out. Please try again.' : controller.signal.aborted ? '' : err instanceof TypeError ? 'Unable to reach OpenAlex. Check your connection or try again later.' : err instanceof Error ? err.message : 'Unable to search OpenAlex. Please try again.');
    } finally {
      window.clearTimeout(timeout);
      if (sequence.current === current) { setLoading(false); request.current = null; }
    }
  }
  function submit(event: FormEvent) {
    event.preventDefault();
    const clean = topic.trim();
    if (clean.length < 2 || clean.length > 160) { setError('Enter a topic between 2 and 160 characters.'); return; }
    if (year && (!/^\d{4}$/.test(year) || Number(year) < 1800 || Number(year) > new Date().getFullYear() + 1)) { setError('Enter a valid publication year from 1800 to next year.'); return; }
    void search(clean, year, 1);
  }
  return <section aria-label="Live Research Explorer"><h1 className="page-title">Live Research Explorer</h1><p className="page-sub">Search real works directly from OpenAlex. These live results are separate from the precomputed snapshot.</p><form className="paper-controls" onSubmit={submit}><label>Research topic<input value={topic} maxLength={160} onChange={e => { changeInput(); setTopic(e.target.value); }} placeholder="e.g. graph neural networks for drug discovery" /></label><label>Publication year (optional)<input type="number" min="1800" max={new Date().getFullYear() + 1} value={year} onChange={e => { changeInput(); setYear(e.target.value); }} placeholder="Any year" /></label><button type="submit" disabled={loading}>{loading ? 'Searching…' : 'Search OpenAlex'}</button></form><p className="demo-note">Requests are sent directly to OpenAlex without an API key. Anonymous usage is limited and may be shared by your network. Up to {MAX_PAGES} pages of {PAGE_SIZE} results are available per search. No embeddings, GraphSAGE inference, gap detection, or new hypotheses are generated.</p>{loading && <p role="status">Searching OpenAlex…</p>}{error && <p role="alert" className="notice error">{error}</p>}{data && <section className="papers-section"><p role="status">{data.count.toLocaleString()} matching works · Page {page} of up to {Math.min(MAX_PAGES, Math.max(1, Math.ceil(data.count / PAGE_SIZE)))}</p>{data.results.length ? data.results.map((work, index) => {
    const openalex = safeLink(work.id); const doi = safeLink(work.doi);
    const location = work.primary_location && typeof work.primary_location === 'object' && 'landing_page_url' in work.primary_location ? safeLink(work.primary_location.landing_page_url) : undefined;
    const title = typeof work.display_name === 'string' && work.display_name.trim() ? work.display_name : typeof work.title === 'string' && work.title.trim() ? work.title : 'Title unavailable';
    return <article className="paper-card" key={openalex || index}><h3>{title}</h3><p>{authors(work.authorships)}</p><p>{typeof work.publication_year === 'number' ? work.publication_year : 'Year unavailable'} · {typeof work.cited_by_count === 'number' ? `${work.cited_by_count.toLocaleString()} citations` : 'Citation count unavailable'}</p>{openalex && <a href={openalex} target="_blank" rel="noreferrer">OpenAlex ↗</a>}{(location || doi) && <> · <a href={location || doi} target="_blank" rel="noreferrer">Original source ↗</a></>}</article>;
  }) : <p>No matching papers. Try another topic or year.</p>}<div className="paper-controls"><button type="button" disabled={loading || page <= 1 || !active} onClick={() => active && void search(active.topic, active.year, page - 1)}>Previous</button><button type="button" disabled={loading || !active || page >= MAX_PAGES || page * PAGE_SIZE >= data.count || data.results.length === 0} onClick={() => active && void search(active.topic, active.year, page + 1)}>Next</button></div></section>}<p className="demo-note">Data provided by <a href="https://openalex.org" target="_blank" rel="noreferrer">OpenAlex</a>.</p></section>;
}
