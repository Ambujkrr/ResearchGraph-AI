import { render, screen, fireEvent, waitFor, cleanup } from '@testing-library/react';
import { afterEach, expect, test, vi } from 'vitest';
import PapersPage from './PapersPage';
afterEach(()=>{cleanup();vi.unstubAllGlobals()});
test('searches and ingests selected external papers',async()=>{
 const paper={openalex_id:'https://openalex.org/W1',title:'Fixture paper',authors:[{name:'A. Author'}],publication_year:2020,abstract:null,citation_count:3,source_url:'https://openalex.org/W1'};
 const mock=vi.fn().mockImplementation(async (url:string, options?:RequestInit)=>({ok:true,json:async()=>url.includes('/openalex/search')?{results:[paper],total:1,page:1,per_page:10}:url.includes('/ingest')?{processed:1}:{results:options?[]:[],total:0,page:1,per_page:10}}));
 vi.stubGlobal('fetch',mock); render(<PapersPage/>);
 fireEvent.change(screen.getByLabelText('Research topic'),{target:{value:'graph'}}); fireEvent.click(screen.getByRole('button',{name:'Search'}));
 expect(await screen.findByText('Fixture paper')).toBeTruthy(); fireEvent.click(screen.getByLabelText('Select paper')); fireEvent.click(screen.getByRole('button',{name:'Ingest selected (1)'}));
 await waitFor(()=>expect(screen.getByText('Processed 1 selected paper(s).')).toBeTruthy());
 expect(mock.mock.calls.some(([url,options])=>url.includes('/papers/ingest') && JSON.parse(options.body).ids[0]===paper.openalex_id)).toBe(true);
});
