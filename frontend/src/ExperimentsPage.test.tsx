import {render,screen,fireEvent,waitFor,cleanup} from '@testing-library/react';
import {afterEach,expect,test,vi} from 'vitest';
import ExperimentsPage from './ExperimentsPage';
afterEach(()=>{cleanup();vi.unstubAllGlobals()});
test('shows limitations and starts an experiment',async()=>{
 const mock=vi.fn().mockImplementation(async (_url:string,options?:RequestInit)=>({ok:true,json:async()=>options?.method==='POST'?{id:1,status:'running'}:{results:[]}}));vi.stubGlobal('fetch',mock);render(<ExperimentsPage/>);
 expect(screen.getByText(/not a historical forecast/i)).toBeTruthy();fireEvent.click(screen.getByRole('button',{name:'Start CPU experiment'}));
 await waitFor(()=>expect(mock.mock.calls.some(([,options])=>options?.method==='POST')).toBe(true));
});
