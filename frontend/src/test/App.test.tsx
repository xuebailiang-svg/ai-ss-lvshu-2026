import {render,screen} from '@testing-library/react';import {MemoryRouter} from 'react-router-dom';import {vi,test,expect} from 'vitest';import App from '../App';
vi.mock('../api/client',()=>({listEvaluations:()=>Promise.resolve([])}));
test('renders new evaluation workflow',()=>{render(<MemoryRouter><App/></MemoryRouter>);expect(screen.getByText('候选地址')).toBeInTheDocument();expect(screen.getByText('1 定位地址')).toBeDisabled()});
test('renders history loading and empty-capable page',async()=>{render(<MemoryRouter initialEntries={['/history']}><App/></MemoryRouter>);expect(screen.getByRole('heading',{name:'历史评估'})).toBeInTheDocument();expect(await screen.findByText('暂无评估记录')).toBeInTheDocument()});
