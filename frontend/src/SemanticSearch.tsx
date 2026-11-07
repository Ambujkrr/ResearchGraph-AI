import { useCallback, useEffect, useRef, useState } from 'react';

const base = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';

class ApiError extends Error {
  constructor(message: string, public readonly status: number) { super(message); }
}

export interface EmbeddingStatus {
  running: boolean;
  error: string | null;
  processed: number;
  papers: number;
  embedded: number;
  model: string;
  revision: string;
  dimensions: number;
}

interface SearchResult {
  id: number;
  title: string;
  score: number;
  source_url: string | null;
}

export default function SemanticSearch() {
  const [q, setQ] = useState('');
  const [results, setResults] = useState<SearchResult[] | null>(null);
  const [busy, setBusy] = useState(false);
  const [searchError, setSearchError] = useState<string | null>(null);

  const [status, setStatus] = useState<EmbeddingStatus | null>(null);
  const [isGenerating, setIsGenerating] = useState(false);
  const [jobError, setJobError] = useState<string | null>(null);
  const [completionMessage, setCompletionMessage] = useState<string | null>(null);

  const isGeneratingRef = useRef(false);
  const startingRef = useRef(false);
  const mountedRef = useRef(false);
  const statusVersionRef = useRef(0);
  const statusControllerRef = useRef<AbortController | null>(null);
  const requestsRef = useRef(new Set<AbortController>());
  const [tracking, setTracking] = useState(false);
  const [initialCheck, setInitialCheck] = useState(true);

  const request = useCallback(async (path: string, options: RequestInit = {}) => {
    const controller = new AbortController();
    requestsRef.current.add(controller);
    const abort = () => controller.abort();
    options.signal?.addEventListener('abort', abort, { once: true });
    if (options.signal?.aborted) controller.abort();
    try {
      const res = await fetch(`${base}/api/v1${path}`, { ...options, signal: controller.signal });
      let data: unknown;
      try { data = await res.json(); } catch { data = null; }
      if (!res.ok) {
        const detail = data && typeof data === 'object' && 'detail' in data && typeof data.detail === 'string' ? data.detail : `Request failed with status ${res.status}`;
        throw new ApiError(detail, res.status);
      }
      if (data === null) throw new Error('The backend returned an invalid response.');
      return data;
    } finally {
      options.signal?.removeEventListener('abort', abort);
      requestsRef.current.delete(controller);
    }
  }, []);

  const checkStatus = useCallback(async (isPollingCall = false): Promise<EmbeddingStatus | null> => {
    statusControllerRef.current?.abort();
    const controller = new AbortController();
    statusControllerRef.current = controller;
    const version = ++statusVersionRef.current;
    try {
      const data = await request('/embeddings/status', { signal: controller.signal }) as EmbeddingStatus;
      if (!mountedRef.current || version !== statusVersionRef.current) return null;
      if (typeof data.running !== 'boolean' || !Number.isInteger(data.papers) || !Number.isInteger(data.embedded) || data.papers < 0 || data.embedded < 0) {
        throw new Error('The backend returned an invalid embedding status.');
      }
      setStatus(data);
      if (data.error) {
        setJobError(`Embedding error: ${data.error}`);
        setIsGenerating(false); isGeneratingRef.current = false; setTracking(false);
      } else if (data.running) {
        setJobError(null); setCompletionMessage(null);
        setIsGenerating(true); isGeneratingRef.current = true; setTracking(true);
      } else {
        setJobError(null);
        const wasRunning = isGeneratingRef.current;
        isGeneratingRef.current = false; setIsGenerating(false); setTracking(false);
        const remaining = Math.max(0, data.papers - data.embedded);
        if (data.papers > 0 && data.embedded >= data.papers) {
          setCompletionMessage(`All papers embedded (${data.embedded} of ${data.papers} papers).`);
        } else if (wasRunning) {
          setCompletionMessage(`Current batch completed. ${data.embedded} of ${data.papers} papers embedded (${remaining} remaining).`);
        } else if (!isPollingCall) {
          setCompletionMessage(`${data.embedded} of ${data.papers} papers embedded (${remaining} remaining). Ready to generate.`);
        }
      }
      return data;
    } catch (err) {
      if (!mountedRef.current || version !== statusVersionRef.current || controller.signal.aborted) return null;
      setJobError(err instanceof Error ? err.message : 'Failed to check embedding status.');
      setCompletionMessage(null); setIsGenerating(false); isGeneratingRef.current = false; setTracking(false);
      return null;
    } finally {
      if (statusControllerRef.current === controller) statusControllerRef.current = null;
    }
  }, [request]);

  useEffect(() => {
    mountedRef.current = true;
    const initial = checkStatus(false);
    const version = statusVersionRef.current;
    void initial.finally(() => { if (mountedRef.current && version === statusVersionRef.current) setInitialCheck(false); });
    return () => {
      mountedRef.current = false; statusVersionRef.current += 1;
      statusControllerRef.current?.abort();
      requestsRef.current.forEach(controller => controller.abort());
    };
  }, [checkStatus]);

  useEffect(() => {
    if (!tracking) return;
    const timer = window.setTimeout(() => { void checkStatus(true); }, 2500);
    return () => window.clearTimeout(timer);
  }, [tracking, status, checkStatus]);

  async function generate() {
    if (startingRef.current || isGeneratingRef.current || initialCheck) return;
    startingRef.current = true;
    statusVersionRef.current += 1; statusControllerRef.current?.abort();
    setTracking(false); setCompletionMessage(null); setJobError(null);
    setIsGenerating(true); isGeneratingRef.current = true;
    try {
      await request('/embeddings/generate?limit=100', { method: 'POST' });
      if (mountedRef.current) await checkStatus(true);
    } catch (err) {
      if (!mountedRef.current) return;
      if (err instanceof ApiError && err.status === 409) {
        await checkStatus(true);
      } else {
        setJobError(err instanceof Error ? err.message : 'Failed to start embedding generation.');
        setIsGenerating(false); isGeneratingRef.current = false; setTracking(false);
      }
    } finally { startingRef.current = false; }
  }

  async function search() {
    setBusy(true); setSearchError(null);
    try {
      const data = await request(`/semantic-search?query=${encodeURIComponent(q)}&limit=10`) as { results: SearchResult[] };
      if (mountedRef.current) setResults(data.results);
    } catch (err) {
      if (mountedRef.current) setSearchError(err instanceof Error ? err.message : 'Search failed.');
    } finally { if (mountedRef.current) setBusy(false); }
  }

  const papers = status?.papers ?? 0;
  const embedded = status?.embedded ?? 0;
  const pct = papers > 0 ? Math.min(100, Math.round((embedded / papers) * 100)) : 0;
  const remaining = Math.max(0, papers - embedded);

  return (
    <section className="papers-section">
      <h2>Semantic search</h2>
      <p>Search saved papers using local embeddings.</p>

      <div className="paper-controls">
        <label>
          Search meaning
          <input
            value={q}
            onChange={(e) => setQ(e.target.value)}
            maxLength={1000}
            placeholder="e.g. graph neural networks"
          />
        </label>
        <button
          type="button"
          disabled={!q.trim() || busy}
          onClick={() => void search()}
        >
          {busy ? 'Searching…' : 'Search saved papers'}
        </button>
        <button
          type="button"
          disabled={isGenerating || initialCheck}
          onClick={() => void generate()}
        >
          {isGenerating ? (
            <>
              <span className="spinner" aria-hidden="true" />
              Generating embeddings...
            </>
          ) : (
            'Generate embeddings'
          )}
        </button>
        <button
          type="button"
          disabled={isGenerating || initialCheck}
          onClick={() => void checkStatus(false)}
        >
          Check embedding status
        </button>
      </div>

      {isGenerating && (
        <p role="status" className="notice">
          <span className="spinner" aria-hidden="true" />
          Generating embeddings...
        </p>
      )}

      {jobError && (
        <p role="alert" className="notice error">
          {jobError}
        </p>
      )}

      {completionMessage && (
        <p role="status" className="notice success">
          {completionMessage}
        </p>
      )}

      {status && (
        <div className="embedding-status-panel">
          <div className="embedding-meta">
            <span>
              {isGenerating && <span className="spinner" aria-hidden="true" />}
              <strong>{embedded}</strong> of <strong>{papers}</strong> papers ({pct}%)
            </span>
            <span>
              <strong>{remaining}</strong> remaining
            </span>
          </div>
          <div
            className="progress-track"
            role="progressbar"
            aria-valuenow={pct}
            aria-valuemin={0}
            aria-valuemax={100}
            aria-label="Embedding progress"
            aria-valuetext={`${embedded} of ${papers} papers embedded`}
          >
            <div className="progress-fill" style={{ width: `${pct}%` }} />
          </div>
        </div>
      )}

      {searchError && (
        <p role="alert" className="notice error">
          {searchError}
        </p>
      )}

      {results &&
        (results.length ? (
          results.map((p) => (
            <article key={p.id} className="paper-card">
              <h3>{p.title}</h3>
              <p>Similarity: {p.score.toFixed(3)}</p>
              {p.source_url && (
                <a href={p.source_url} target="_blank" rel="noreferrer">
                  Original source ↗
                </a>
              )}
            </article>
          ))
        ) : (
          <p>No embedded papers found.</p>
        ))}
    </section>
  );
}
