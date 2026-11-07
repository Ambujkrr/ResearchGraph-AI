import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import SemanticSearch from './SemanticSearch';

const status = (running: boolean, embedded: number, papers = 1502, error: string | null = null) => ({running, embedded, papers, error, processed: 0, model: 'model', revision: 'revision', dimensions: 384});
const response = (data: unknown, statusCode = 200) => ({ok: statusCode >= 200 && statusCode < 300, status: statusCode, json: async () => data});
const waitReady = async () => { await waitFor(() => expect((screen.getByRole('button', {name: 'Generate embeddings'}) as HTMLButtonElement).disabled).toBe(false)); };

describe('SemanticSearch embedding status', () => {
  beforeEach(() => vi.useFakeTimers({ shouldAdvanceTime: true }));
  afterEach(() => { cleanup(); vi.clearAllTimers(); vi.useRealTimers(); vi.unstubAllGlobals(); });

  it('loads live corpus counts and accessible progress', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(response(status(false,1502))));
    render(<SemanticSearch />);
    expect(await screen.findByText('All papers embedded (1502 of 1502 papers).')).toBeTruthy();
    const bar=screen.getByRole('progressbar');
    expect(bar.getAttribute('aria-valuenow')).toBe('100');
    expect(bar.getAttribute('aria-valuetext')).toBe('1502 of 1502 papers embedded');
  });

  it('starts one job, polls at 2.5 seconds, and reports a partial batch', async () => {
    let checks=0;
    const fetchMock=vi.fn().mockImplementation(async (url:string,init?:RequestInit) => {
      if (url.includes('/generate')) return response({status:'started'});
      if (url.includes('/status')) { checks++; return response(checks===1?status(false,100,500):checks===2?status(true,120,500):status(false,200,500)); }
      return response({results:[]});
    });
    vi.stubGlobal('fetch',fetchMock);render(<SemanticSearch />);await waitReady();
    const button=screen.getByRole('button',{name:'Generate embeddings'});fireEvent.click(button);fireEvent.click(button);
    await waitFor(()=>expect(screen.getByRole('progressbar').getAttribute('aria-valuenow')).toBe('24'));
    expect((screen.getByRole('button',{name:/Generating embeddings/}) as HTMLButtonElement).disabled).toBe(true);
    await act(async()=>{await vi.advanceTimersByTimeAsync(2000)});expect(checks).toBe(2);
    await act(async()=>{await vi.advanceTimersByTimeAsync(600)});
    expect(await screen.findByText('Current batch completed. 200 of 500 papers embedded (300 remaining).')).toBeTruthy();
    expect(fetchMock.mock.calls.filter(([url])=>url.includes('/generate'))).toHaveLength(1);
  });

  it('reattaches to a running job returned by initial status', async () => {
    let checks=0;vi.stubGlobal('fetch',vi.fn().mockImplementation(async()=>response(++checks===1?status(true,1400):status(false,1502))));
    render(<SemanticSearch />);expect(await screen.findByRole('button',{name:/Generating embeddings/})).toBeTruthy();
    await act(async()=>{await vi.advanceTimersByTimeAsync(2501)});
    expect(await screen.findByText('All papers embedded (1502 of 1502 papers).')).toBeTruthy();
  });

  it('handles HTTP 409 by checking the running job, regardless of message wording', async () => {
    let checks=0;vi.stubGlobal('fetch',vi.fn().mockImplementation(async(url:string)=>url.includes('/generate')?response({detail:'Embedding generation already running'},409):response(++checks===1?status(false,100,500):status(true,120,500))));
    render(<SemanticSearch />);await waitReady();fireEvent.click(screen.getByRole('button',{name:'Generate embeddings'}));
    await waitFor(()=>expect((screen.getByRole('button',{name:/Generating embeddings/}) as HTMLButtonElement).disabled).toBe(true));
    expect(screen.queryByRole('alert')).toBeNull();
  });

  it('shows backend errors without leaving a false success message', async () => {
    let checks=0;vi.stubGlobal('fetch',vi.fn().mockImplementation(async(url:string)=>url.includes('/generate')?response({status:'started'}):response(++checks===1?status(false,10,100):status(false,10,100,'Encoding failed'))));
    render(<SemanticSearch />);await waitReady();fireEvent.click(screen.getByRole('button',{name:'Generate embeddings'}));
    expect((await screen.findByRole('alert')).textContent).toContain('Encoding failed');
    expect(screen.queryByText(/Current batch completed/)).toBeNull();
  });

  it('reports non-JSON server failures and network errors', async () => {
    const mock=vi.fn().mockImplementation(async(url:string)=>url.includes('/generate')?{ok:false,status:503,json:async()=>{throw new Error('not JSON')}}:response(status(false,0,100)));
    vi.stubGlobal('fetch',mock);render(<SemanticSearch />);await waitReady();fireEvent.click(screen.getByRole('button',{name:'Generate embeddings'}));
    expect((await screen.findByRole('alert')).textContent).toContain('503');
  });

  it('aborts pending requests and clears polling on unmount', async () => {
    let pendingSignal:AbortSignal|undefined;
    const mock=vi.fn().mockImplementation((_url:string,init?:RequestInit)=>{pendingSignal=init?.signal??undefined;return new Promise(()=>{});});
    vi.stubGlobal('fetch',mock);const {unmount}=render(<SemanticSearch />);
    await waitFor(()=>expect(mock).toHaveBeenCalledTimes(1));unmount();expect(pendingSignal?.aborted).toBe(true);
    await act(async()=>{await vi.advanceTimersByTimeAsync(5000)});expect(mock).toHaveBeenCalledTimes(1);
  });

  it('ignores a stale status response after a newer job starts', async () => {
    let resolveStale!: (value: unknown)=>void;let checks=0;
    const mock=vi.fn().mockImplementation((url:string)=>{
      if(url.includes('/generate'))return Promise.resolve(response({status:'started'}));
      if(url.includes('/status')) { checks++; if(checks===2)return new Promise(resolve=>{resolveStale=resolve}); return Promise.resolve(response(checks===1?status(false,100,500):status(true,120,500))); }
      return Promise.resolve(response({results:[]}));
    });
    vi.stubGlobal('fetch',mock);render(<SemanticSearch />);await waitReady();
    fireEvent.click(screen.getByRole('button',{name:'Check embedding status'}));
    await waitFor(()=>expect(checks).toBe(2));fireEvent.click(screen.getByRole('button',{name:'Generate embeddings'}));
    await waitFor(()=>expect(screen.getByRole('progressbar').getAttribute('aria-valuenow')).toBe('24'));
    await act(async()=>{resolveStale(response(status(false,100,500)))});
    expect(screen.getByRole('progressbar').getAttribute('aria-valuenow')).toBe('24');
    expect((screen.getByRole('button',{name:/Generating embeddings/}) as HTMLButtonElement).disabled).toBe(true);
  });
});
