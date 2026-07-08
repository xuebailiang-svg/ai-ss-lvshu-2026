import {cleanup, render, screen, waitFor} from '@testing-library/react';
import {MemoryRouter} from 'react-router-dom';
import {afterEach, beforeEach, expect, test, vi} from 'vitest';
import App from '../App';
import {friendlyError} from '../pages/NewEvaluation';

vi.mock('echarts-for-react', () => ({
  default: () => <div data-testid="echarts" />,
}));

const apiMocks = vi.hoisted(() => ({
  listEvaluations: vi.fn(() => Promise.resolve([])),
  poiTemplates: vi.fn(() => Promise.resolve({base_columns: [], categories: {}})),
  listPois: vi.fn(() => Promise.resolve({evaluation_id: 0, total: 0, counts: {}, items: [], statistics: {}})),
  configStatus: vi.fn(() => Promise.resolve({backend: {}, frontend: {}})),
  systemHealth: vi.fn(() => Promise.resolve({status: 'ok', warnings: [], config: {ENABLE_DEBUG_API: false}})),
  amapGeocodeTest: vi.fn(() => Promise.resolve({ok: true, result: {formatted_address: '测试地址'}})),
  runSiteSelectionAgent: vi.fn(() => Promise.resolve({steps: [], final_score: {total: 70, level: '建议进一步实地考察'}, report: {summary: 'ok'}})),
  getEvaluation: vi.fn(),
  deleteEvaluation: vi.fn(),
  report: vi.fn(),
  createEvaluation: vi.fn(),
  updateProperty: vi.fn(),
  geocode: vi.fn(),
  collectPois: vi.fn(),
  poiDiagnostics: vi.fn(),
  createManualPoi: vi.fn(),
  savePoiEnrichment: vi.fn(),
  importPoisCsv: vi.fn(),
  score: vi.fn(),
  saveCompetitorEnrichment: vi.fn(),
  competitorHistory: vi.fn(),
  compareEvaluations: vi.fn(),
  saveSiteFeedback: vi.fn(),
  getAgentTrace: vi.fn(),
}));

vi.mock('../api/client', () => ({
  ...apiMocks,
  exportPoisUrl: (id: number, category: string) => `/api/evaluations/${id}/pois/export?category=${category}`,
  isTimeoutError: (error: any) => error?.code === 'ECONNABORTED' || String(error?.message || '').includes('timeout'),
  friendlyTimeoutMessage: () => '请求超过预期时间，服务可能仍在处理中，请稍后重试。',
}));

const sampleEvaluation = {
  id: 7,
  name: '小寨地铁站测试',
  city: '西安市',
  address: '小寨地铁站',
  radius: 1000,
  site: {id: 7, property: {}, longitude: 108.9, latitude: 34.2},
  result: null,
};

beforeEach(() => {
  localStorage.clear();
  vi.clearAllMocks();
  apiMocks.getEvaluation.mockResolvedValue(sampleEvaluation);
  apiMocks.report.mockResolvedValue({sections: {}, hard_risk: false, disclaimer: ''});
});

afterEach(() => {
  cleanup();
});

test('renders new evaluation workflow', () => {
  render(<MemoryRouter><App /></MemoryRouter>);
  expect(screen.getByText('候选地址')).toBeInTheDocument();
  expect(screen.getByTestId('evaluation-name-input')).toBeEnabled();
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

test('shows restore prompt without locking new evaluation inputs', async () => {
  localStorage.setItem('m2a:current-evaluation-id', '7');
  render(<MemoryRouter><App /></MemoryRouter>);
  expect(await screen.findByTestId('restore-evaluation-alert')).toBeInTheDocument();
  expect(screen.getByTestId('evaluation-name-input')).toBeEnabled();
  expect(apiMocks.getEvaluation).not.toHaveBeenCalled();
});

test('shows locked notice for saved evaluation route', async () => {
  render(<MemoryRouter initialEntries={['/evaluations/7']}><App /></MemoryRouter>);
  expect(await screen.findByTestId('saved-evaluation-locked-alert')).toBeInTheDocument();
  await waitFor(() => expect(screen.getByTestId('evaluation-name-input')).toBeDisabled());
});

test('shows friendly report timeout with retry actions', async () => {
  apiMocks.report.mockRejectedValueOnce({code: 'ECONNABORTED', message: 'timeout of 20000ms exceeded'});
  render(<MemoryRouter initialEntries={['/reports/7']}><App /></MemoryRouter>);
  expect(await screen.findByText('报告加载超时')).toBeInTheDocument();
  expect(screen.getByText('报告生成或加载超过预期时间，可能仍在处理中，请稍后重试。')).toBeInTheDocument();
  expect(screen.getByRole('button', {name: '重试加载报告'})).toBeInTheDocument();
  expect(screen.getByRole('button', {name: '返回评估页面'})).toBeInTheDocument();
  expect(screen.getByRole('button', {name: '返回历史评估'})).toBeInTheDocument();
});

test('shows score first message when report is missing', async () => {
  apiMocks.report.mockRejectedValueOnce({response: {status: 409, data: {detail: 'Please score the evaluation first'}}});
  render(<MemoryRouter initialEntries={['/reports/7']}><App /></MemoryRouter>);
  expect(await screen.findByText('请先生成评分/报告')).toBeInTheDocument();
  expect(screen.getByText('请先回到新地址评估页，点击“3 生成评分/报告”。')).toBeInTheDocument();
});

test('renders report export actions when report is available', async () => {
  apiMocks.getEvaluation.mockResolvedValueOnce({
    ...sampleEvaluation,
    result: {
      total_score: 76,
      recommendation: '建议进一步实地考察',
      dimensions: {},
      positive_evidence: [],
      negative_evidence: [],
      hard_risks: [],
      review_items: [],
      completeness: 80,
      confidence: 70,
      model_version: 'test',
    },
  });
  render(<MemoryRouter initialEntries={['/reports/7']}><App /></MemoryRouter>);
  expect(await screen.findByRole('button', {name: '导出 HTML'})).toBeInTheDocument();
  expect(screen.getByRole('button', {name: '打印 / 另存 PDF'})).toBeInTheDocument();
});
