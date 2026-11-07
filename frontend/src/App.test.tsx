import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { afterEach, expect, test, vi } from 'vitest';
import { cleanup } from '@testing-library/react';
import App from './App';

afterEach(() => { cleanup(); vi.unstubAllGlobals(); });
test('shows real health response and navigates to an empty library', async () => {
  vi.stubGlobal('fetch', vi.fn().mockImplementation(async (url: string) => ({ok:true, json: async () => url.includes('/health') ? ({status:'ok'}) : ({results:[],total:0,page:1,per_page:10})})));
  render(<App />);
  await waitFor(() => expect(screen.getAllByText('API online').length).toBeGreaterThan(0));
  fireEvent.click(screen.getByRole('button', {name:'Papers'}));
  await waitFor(() => expect(screen.getByText('No saved papers match these filters.')).toBeTruthy());
});
test('reports an unavailable API', async () => {
  vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('offline')));
  render(<App />);
  await waitFor(() => expect(screen.getAllByText('API unavailable').length).toBeGreaterThan(0));
});
