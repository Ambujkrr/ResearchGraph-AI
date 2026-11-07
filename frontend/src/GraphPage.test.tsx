import {render,screen,fireEvent,waitFor,cleanup} from '@testing-library/react';
import {test,expect,vi,afterEach} from 'vitest';
import GraphPage from './GraphPage';
afterEach(()=>{cleanup();vi.unstubAllGlobals()});
test('explores persisted neighbors and filters relationships',async()=>{
 vi.stubGlobal('fetch',vi.fn().mockImplementation(async (url:string)=>({ok:true,json:async()=>url.includes('neighborhood')?{nodes:[{id:'paper:1',type:'paper',label:'Paper',source_url:null},{id:'author:1',type:'author',label:'Author',source_url:null}],edges:[{source:'paper:1',target:'author:1',type:'authored_by',provenance:'openalex'}]}:{results:[{id:1,title:'Paper'}]}})));
 render(<GraphPage/>);await screen.findByRole('option',{name:'Paper'});fireEvent.change(screen.getByLabelText('Starting paper'),{target:{value:'1'}});fireEvent.click(screen.getByRole('button',{name:'Explore'}));
 await screen.findByRole('button',{name:'Author'});fireEvent.click(screen.getByRole('button',{name:'Author'}));expect(screen.getByText('Selected node')).toBeTruthy();fireEvent.change(screen.getByLabelText('Node type'),{target:{value:'topic'}});await waitFor(()=>expect(screen.getByText('No relationships match these filters.')).toBeTruthy());
});
