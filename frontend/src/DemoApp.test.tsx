import { cleanup, fireEvent, render, screen, within } from '@testing-library/react';
import { afterEach, expect, test, vi } from 'vitest';
import DemoApp from './DemoApp';
import snapshot from './demo-data.json';

afterEach(() => { cleanup(); vi.unstubAllGlobals(); });
test('searches paper snapshot and explores actual citations without any API requests', () => {
  const fetchMock = vi.fn(); vi.stubGlobal('fetch', fetchMock);
  render(<DemoApp/>);
  fireEvent.click(screen.getByRole('button', { name: 'Papers' }));
  fireEvent.change(screen.getByLabelText('Search titles or year'), {target:{value:'no-such-paper-xyz'}});
  expect(screen.getByText('No papers match this search.')).toBeTruthy();
  fireEvent.change(screen.getByLabelText('Search titles or year'), {target:{value:snapshot.papers[0].title}});
  expect(screen.getByText(snapshot.papers[0].title)).toBeTruthy();
  fireEvent.click(screen.getByRole('button', { name: 'Knowledge Graph' }));
  expect(screen.getByRole('img', {name:/Citation graph/})).toBeTruthy();
  const nodeList = screen.getByLabelText('Paper nodes');
  fireEvent.click(within(nodeList).getByRole('button', {name:snapshot.papers[1].title}));
  expect(screen.getByText('Selected paper').nextElementSibling?.textContent).toBe(snapshot.papers[1].title);
  expect(fetchMock).not.toHaveBeenCalled();
});
test('shows cited evidence, abstention, and selectable recorded metrics without network calls', () => {
  const fetchMock = vi.fn(); vi.stubGlobal('fetch', fetchMock);
  render(<DemoApp/>);
  fireEvent.click(screen.getByRole('button', {name:'Research Gaps'}));
  fireEvent.click(screen.getByRole('button', {name:'Inspect supporting evidence'}));
  expect(screen.getByRole('link', {name:/MolGpKa/}).getAttribute('href')).toBe('https://openalex.org/W3181755904');
  expect(screen.getByText(/No hypothesis was generated/)).toBeTruthy();
  fireEvent.click(screen.getByRole('button', {name:'Experiments'}));
  fireEvent.change(screen.getByLabelText('Metric'), {target:{value:'Precision@10'}});
  expect(screen.getByText('0.0591')).toBeTruthy();
  expect(fetchMock).not.toHaveBeenCalled();
});
test('every snapshot edge has known endpoints and source provenance', () => {
  const ids = new Set(snapshot.papers.map(p => p.id));
  expect(snapshot.citations.length).toBeGreaterThan(0);
  for (const edge of snapshot.citations) {
    expect(ids.has(edge.source) && ids.has(edge.target)).toBe(true);
    expect(edge.provenance).toBe('openalex');
  }
});
