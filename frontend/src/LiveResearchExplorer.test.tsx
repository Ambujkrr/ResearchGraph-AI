import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';
import { afterEach, expect, test, vi } from 'vitest';
import LiveResearchExplorer from './LiveResearchExplorer';

afterEach(() => { cleanup(); vi.unstubAllGlobals(); vi.useRealTimers(); });
const work = { id:'https://openalex.org/W123', display_name:'Real paper title', authorships:[{author:{display_name:'A. Researcher'}}], publication_year:2020, cited_by_count:12, doi:'https://doi.org/10.1234/example' };
const ok = (results: unknown[] = [work], count = 25) => ({ok:true,status:200,json:async()=>({results,meta:{count}})});
function submit() { fireEvent.change(screen.getByLabelText('Research topic'), {target:{value:'drug discovery'}}); fireEvent.click(screen.getByRole('button',{name:'Search OpenAlex'})); }

test('searches by topic and publication year, displaying real response metadata and bounded pagination', async () => {
  const mock=vi.fn().mockResolvedValue(ok()); vi.stubGlobal('fetch',mock); render(<LiveResearchExplorer/>);
  expect(mock).not.toHaveBeenCalled();
  fireEvent.change(screen.getByLabelText('Publication year (optional)'),{target:{value:'2020'}}); submit();
  expect(await screen.findByText('Real paper title')).toBeTruthy();
  expect(screen.getByText('A. Researcher')).toBeTruthy(); expect(screen.getByText('2020 · 12 citations')).toBeTruthy();
  expect(screen.getByRole('link',{name:'OpenAlex ↗'}).getAttribute('href')).toBe(work.id);
  const url=new URL(mock.mock.calls[0][0]); expect(url.searchParams.get('filter')).toBe('publication_year:2020'); expect(url.searchParams.get('per_page')).toBe('10');
  fireEvent.click(screen.getByRole('button',{name:'Next'}));
  await waitFor(()=>expect(mock).toHaveBeenCalledTimes(2));
  expect(new URL(mock.mock.calls[1][0]).searchParams.get('page')).toBe('2');
  expect(await screen.findByText(/Page 2 of up to 3/)).toBeTruthy();
});
test('handles empty results, missing metadata and unsafe links', async () => {
  const mock=vi.fn().mockResolvedValueOnce(ok([],0)).mockResolvedValueOnce(ok([{display_name:null,id:'javascript:alert(1)',authorships:null}],1)); vi.stubGlobal('fetch',mock); render(<LiveResearchExplorer/>);
  submit(); expect(await screen.findByText(/No matching papers/)).toBeTruthy();
  fireEvent.click(screen.getByRole('button',{name:'Search OpenAlex'}));
  expect(await screen.findByText('Title unavailable')).toBeTruthy(); expect(screen.getByText('Authors unavailable')).toBeTruthy();
  expect(screen.queryByRole('link',{name:'OpenAlex ↗'})).toBeNull();
});
test.each([[429,/rate limit/],[503,/HTTP 503/]])('reports OpenAlex HTTP %s', async (status,message) => {
  vi.stubGlobal('fetch',vi.fn().mockResolvedValue({ok:false,status})); render(<LiveResearchExplorer/>); submit();
  expect(await screen.findByRole('alert')).toHaveTextContent(message);
});
test('reports network and malformed response errors', async () => {
  const mock=vi.fn().mockRejectedValueOnce(new TypeError('network')).mockResolvedValueOnce({ok:true,status:200,json:async()=>({})}); vi.stubGlobal('fetch',mock); render(<LiveResearchExplorer/>);
  submit(); expect(await screen.findByRole('alert')).toHaveTextContent(/Unable to reach/);
  fireEvent.click(screen.getByRole('button',{name:'Search OpenAlex'})); expect(await screen.findByRole('alert')).toHaveTextContent(/unexpected response/);
});
test('cancels an in-flight search on input change and ignores stale results', async () => {
  let resolve!: (value: ReturnType<typeof ok>) => void;
  const mock=vi.fn().mockImplementation(()=>new Promise(r=>{resolve=r;})); vi.stubGlobal('fetch',mock); render(<LiveResearchExplorer/>); submit();
  const signal=mock.mock.calls[0][1].signal as AbortSignal;
  fireEvent.change(screen.getByLabelText('Research topic'),{target:{value:'new topic'}}); expect(signal.aborted).toBe(true);
  resolve(ok()); await waitFor(()=>expect(screen.queryByText('Real paper title')).toBeNull());
});
test('aborts requests on unmount', () => {
  const mock=vi.fn().mockImplementation(()=>new Promise(()=>{})); vi.stubGlobal('fetch',mock); const view=render(<LiveResearchExplorer/>); submit();
  const signal=mock.mock.calls[0][1].signal as AbortSignal; view.unmount(); expect(signal.aborted).toBe(true);
});
test('reports a timeout when OpenAlex does not respond', async () => {
  vi.useFakeTimers();
  const mock=vi.fn().mockImplementation((_url, options: {signal: AbortSignal})=>new Promise((_resolve,reject)=>options.signal.addEventListener('abort',()=>reject(new DOMException('Aborted','AbortError')))));
  vi.stubGlobal('fetch',mock); render(<LiveResearchExplorer/>); submit();
  await act(async()=>{await vi.advanceTimersByTimeAsync(15000)});
  expect(screen.getByRole('alert')).toHaveTextContent(/timed out/);
});
