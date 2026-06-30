import {render, screen} from '@testing-library/react';
import {MemoryRouter} from 'react-router-dom';
import {vi, test, expect} from 'vitest';
import App from '../App';
import {friendlyError} from '../pages/NewEvaluation';

vi.mock('../api/client', () => ({
  listEvaluations: () => Promise.resolve([]),
  poiTemplates: () => Promise.resolve({base_columns: [], categories: {}}),
  listPois: () => Promise.resolve({evaluation_id: 0, total: 0, counts: {}, items: []}),
  configStatus: () => Promise.resolve({backend: {}, frontend: {}}),
  systemHealth: () => Promise.resolve({status: 'ok', warnings: [], config: {ENABLE_DEBUG_API: false}}),
  amapGeocodeTest: () => Promise.resolve({ok: true, result: {formatted_address: '测试地址'}}),
  runSiteSelectionAgent: () => Promise.resolve({steps: [], final_score: {total: 70, level: '建议进一步实地考察'}, report: {summary: 'ok'}}),
}));

test('renders new evaluation workflow', () => {
  render(<MemoryRouter><App /></MemoryRouter>);
  expect(screen.getByText('候选地址')).toBeInTheDocument();
  expect(screen.getByRole('button', {name: '1 定位地址'})).toBeDisabled();
  expect(screen.getByRole('button', {name: '4 查看报告'})).toBeDisabled();
});

test('renders history loading and empty-capable page', async () => {
  render(<MemoryRouter initialEntries={['/history']}><App /></MemoryRouter>);
  expect(screen.getByRole('heading', {name: '历史评估'})).toBeInTheDocument();
  expect(await screen.findByText('暂无评估记录')).toBeInTheDocument();
});

test('renders system config page', async () => {
  render(<MemoryRouter initialEntries={['/system-config']}><App /></MemoryRouter>);
  expect(screen.getByRole('heading', {name: '系统配置'})).toBeInTheDocument();
  expect(await screen.findByText('/etc/esports-site-selection/backend.env')).toBeInTheDocument();
});

test('renders agent analysis page', () => {
  render(<MemoryRouter initialEntries={['/agent']}><App /></MemoryRouter>);
  expect(screen.getByRole('heading', {name: '选址 Agent 分析'})).toBeInTheDocument();
  expect(screen.getByRole('button', {name: '启动 Agent 分析'})).toBeInTheDocument();
});

test('renders rate limit message instead of key permission message', () => {
  const text = friendlyError({
    error_code: 'AMAP_RATE_LIMIT',
    infocode: '10021',
    info: 'CUQPS_HAS_EXCEEDED_THE_LIMIT',
    message: '高德接口请求过快，已触发限流。',
  });
  expect(text).toContain('限流');
  expect(text).not.toContain('Key 类型');
});
