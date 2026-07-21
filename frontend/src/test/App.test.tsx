import {cleanup, fireEvent, render, screen, waitFor} from '@testing-library/react';
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
  listProjects: vi.fn(() => Promise.resolve({items: []})),
  createProject: vi.fn(() => Promise.resolve({project_id: 'proj_new'})),
  getProject: vi.fn(() => Promise.resolve({project: {project_id: 'proj_1', name: '测试项目', city: '西安市', address: '小寨地铁站', radius_meters: 1000, business_type: '电竞馆'}, stats: {}})),
  getProjectDataset: vi.fn(() => Promise.resolve({project: {project_id: 'proj_1'}, pois: [], competitors: [], food_businesses: [], entertainments: [], rent_data: {}, population_data: {}, supplements: []})),
  getProjectDataQuality: vi.fn(() => Promise.resolve({project_id: 'proj_1', quality_score: 60, missing: ['真实租金'], warnings: []})),
  getProjectMissingData: vi.fn(() => Promise.resolve({project_id: 'proj_1', missing: []})),
  collectProjectAmap: vi.fn(() => Promise.resolve({success: true, collected: {poi_count: 1, competitor_count: 0, food_count: 0, entertainment_count: 0}})),
  collectProjectCompetitors: vi.fn(() => Promise.resolve({success: true, discovered_count: 1})),
  collectProjectSupporting: vi.fn(() => Promise.resolve({success: true, food_count: 1, entertainment_count: 1, night_business_count: 0})),
  listProjectCompetitors: vi.fn(() => Promise.resolve({items: [], total: 0})),
  listProjectSupporting: vi.fn(() => Promise.resolve({items: [], total: 0, effective_count: 0, stats: {}})),
  listProjectRent: vi.fn(() => Promise.resolve({items: [], total: 0, incomplete_count: 0, confirmed_count: 0, detail_completed_count: 0})),
  getDataSourceStatus: vi.fn(() => Promise.resolve({items: [
    {name: 'amap', display_name: '高德 POI', status: 'available', description: '高德地图基础数据', capabilities: ['poi'], check_supported: true},
    {name: 'manual', display_name: '人工上传', status: 'available', description: '人工补充数据', capabilities: ['manual'], check_supported: true},
  ]})),
  checkDataSourceConnectivity: vi.fn(() => Promise.resolve({name: 'amap', configured: true, reachable: true, status: 'ok', message: 'ok', latency_ms: 10, checked_at: 'now'})),
  getScoringConfig: vi.fn(() => Promise.resolve({dimensions: [
    {key: 'redline_compliance', name: '红线合规', description: '红线检查', weight: 10, enabled: true, data_sources: ['amap'], sort_order: 0, factors: []},
    {key: 'competitor_operation', name: '竞品经营', description: '竞品经营信息', weight: 10, enabled: true, data_sources: ['manual'], sort_order: 1, factors: []},
  ], total_weight: 20, normalized: false})),
  updateScoringConfig: vi.fn(() => Promise.resolve({dimensions: [], total_weight: 0, normalized: false})),
  resetScoringConfig: vi.fn(() => Promise.resolve({dimensions: [], total_weight: 0, normalized: false})),
  listMemory: vi.fn(() => Promise.resolve({items: [], total: 0})),
  createMemory: vi.fn(() => Promise.resolve({id: 1})),
  reviewMemory: vi.fn(() => Promise.resolve({id: 1})),
  submitManualInput: vi.fn(() => Promise.resolve({success: true})),
  listManualInputs: vi.fn(() => Promise.resolve({items: []})),
  scoreProject: vi.fn(() => Promise.resolve({total_score: 70, level: '推荐', confidence: 0.8, dimensions: {population: {score: 20, max: 30}}})),
  generateAiReport: vi.fn(() => Promise.resolve({success: true, content: '# 电竞馆选址分析报告', model: 'deepseek-chat'})),
  createProjectChatSession: vi.fn(() => Promise.resolve({session_id: '1', project_id: 'proj_1'})),
  sendProjectChatMessage: vi.fn(() => Promise.resolve({answer: '基于评分和竞品数据回答。', references: ['score_result']})),
  listProjectChatMessages: vi.fn(() => Promise.resolve({session_id: '1', project_id: 'proj_1', messages: []})),
}));

vi.mock('../api/client', () => ({
  ...apiMocks,
  exportPoisUrl: (id: number, category: string) => `/api/evaluations/${id}/pois/export?category=${category}`,
  isTimeoutError: (error: any) => error?.code === 'ECONNABORTED' || String(error?.message || '').includes('timeout'),
  friendlyTimeoutMessage: () => '请求超过预期时间，服务可能仍在处理中，请稍后重试。',
}));

vi.mock('../api/projects', () => ({
  listProjects: apiMocks.listProjects,
  createProject: apiMocks.createProject,
  getProject: apiMocks.getProject,
  getProjectDataset: apiMocks.getProjectDataset,
  getProjectDataQuality: apiMocks.getProjectDataQuality,
  getProjectMissingData: apiMocks.getProjectMissingData,
  collectProjectAmap: apiMocks.collectProjectAmap,
  collectProjectCompetitors: apiMocks.collectProjectCompetitors,
  collectProjectSupporting: apiMocks.collectProjectSupporting,
  listProjectCompetitors: apiMocks.listProjectCompetitors,
  listProjectSupporting: apiMocks.listProjectSupporting,
  listProjectRent: apiMocks.listProjectRent,
  reviewProjectCompetitor: vi.fn(() => Promise.resolve({})),
  getProjectCompetitor: vi.fn(() => Promise.resolve({})),
  updateProjectCompetitor: vi.fn(() => Promise.resolve({})),
  reviewProjectSupporting: vi.fn(() => Promise.resolve({})),
  getProjectSupportingDetail: vi.fn(() => Promise.resolve({manual_detail: {}})),
  updateProjectSupportingDetail: vi.fn(() => Promise.resolve({})),
  reviewProjectRent: vi.fn(() => Promise.resolve({})),
  getProjectRentDetail: vi.fn(() => Promise.resolve({manual_detail: {}})),
  updateProjectRentDetail: vi.fn(() => Promise.resolve({})),
}));

vi.mock('../api/dataSources', () => ({
  getDataSourceStatus: apiMocks.getDataSourceStatus,
  checkDataSourceConnectivity: apiMocks.checkDataSourceConnectivity,
}));

vi.mock('../api/scoringConfig', () => ({
  getScoringConfig: apiMocks.getScoringConfig,
  updateScoringConfig: apiMocks.updateScoringConfig,
  resetScoringConfig: apiMocks.resetScoringConfig,
}));

vi.mock('../api/memory', () => ({
  listMemory: apiMocks.listMemory,
  createMemory: apiMocks.createMemory,
  reviewMemory: apiMocks.reviewMemory,
}));

vi.mock('../api/data', () => ({
  submitManualInput: apiMocks.submitManualInput,
  listManualInputs: apiMocks.listManualInputs,
}));

vi.mock('../api/score', () => ({
  scoreProject: apiMocks.scoreProject,
}));

vi.mock('../api/report', () => ({
  generateAiReport: apiMocks.generateAiReport,
}));

vi.mock('../api/chat', () => ({
  createProjectChatSession: apiMocks.createProjectChatSession,
  sendProjectChatMessage: apiMocks.sendProjectChatMessage,
  listProjectChatMessages: apiMocks.listProjectChatMessages,
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
  expect(screen.getByText('聊天式工作区')).toBeInTheDocument();
  expect(screen.getByText('新建选址项目')).toBeInTheDocument();
  expect(screen.getByText('选址维度')).toBeInTheDocument();
  expect(screen.getByRole('button', {name: /采集高德 POI/})).toBeInTheDocument();
});

test('renders history loading and empty-capable page', async () => {
  render(<MemoryRouter initialEntries={['/history']}><App /></MemoryRouter>);
  expect(screen.getByRole('heading', {name: '历史评估'})).toBeInTheDocument();
  expect(await screen.findByText('暂无评估记录')).toBeInTheDocument();
});

test('renders system config page', async () => {
  render(<MemoryRouter initialEntries={['/system-config']}><App /></MemoryRouter>);
  expect(screen.getByRole('heading', {name: '配置'})).toBeInTheDocument();
  expect(await screen.findByText('Key 和模型配置')).toBeInTheDocument();
  expect(screen.getByText('评分维度和权重')).toBeInTheDocument();
});

test('renders agent analysis page', () => {
  render(<MemoryRouter initialEntries={['/agent']}><App /></MemoryRouter>);
  expect(screen.getByRole('heading', {name: '选址 Agent 分析'})).toBeInTheDocument();
  expect(screen.getByRole('button', {name: '启动 Agent 分析'})).toBeInTheDocument();
});

test('renders projects page and empty list', async () => {
  render(<MemoryRouter initialEntries={['/projects']}><App /></MemoryRouter>);
  expect(screen.getByRole('heading', {name: '选址项目'})).toBeInTheDocument();
  expect(await screen.findByText('创建项目')).toBeInTheDocument();
  expect(apiMocks.listProjects).toHaveBeenCalled();
});

test('submits create project form', async () => {
  render(<MemoryRouter><App /></MemoryRouter>);
  fireEvent.change(screen.getByPlaceholderText('例如：小寨电竞馆选址'), {target: {value: '西安小寨电竞馆'}});
  fireEvent.change(screen.getByPlaceholderText('例如：小寨地铁站'), {target: {value: '小寨地铁站'}});
  fireEvent.click(screen.getByRole('button', {name: /创建项目/}));
  await waitFor(() => expect(apiMocks.createProject).toHaveBeenCalled());
});

test('renders v1.1 workbench with selected project context', async () => {
  apiMocks.listProjects.mockResolvedValueOnce({items: [{
    project_id: 'proj_1',
    name: '测试项目',
    city: '西安市',
    address: '小寨地铁站',
    radius_meters: 1000,
    business_type: '电竞馆',
  }]} as any);
  render(<MemoryRouter><App /></MemoryRouter>);
  expect((await screen.findAllByText('测试项目')).length).toBeGreaterThan(0);
  expect(screen.getByText('聊天式工作区')).toBeInTheDocument();
  expect(screen.getByText('选址维度')).toBeInTheDocument();
  expect(screen.getByText('已确认记忆')).toBeInTheDocument();
});

test('v1.1 workbench action buttons call APIs', async () => {
  apiMocks.listProjects.mockResolvedValueOnce({items: [{
    project_id: 'proj_1',
    name: '测试项目',
    city: '西安市',
    address: '小寨地铁站',
    radius_meters: 1000,
    business_type: '电竞馆',
  }]} as any);
  render(<MemoryRouter><App /></MemoryRouter>);
  expect((await screen.findAllByText('测试项目')).length).toBeGreaterThan(0);
  fireEvent.click(screen.getByText('采集高德 POI'));
  fireEvent.click(screen.getByText('评分分析'));
  fireEvent.click(screen.getByText('生成报告'));
  await waitFor(() => expect(apiMocks.collectProjectAmap).toHaveBeenCalledWith('proj_1'));
  await waitFor(() => expect(apiMocks.scoreProject).toHaveBeenCalledWith('proj_1'));
  await waitFor(() => expect(apiMocks.generateAiReport).toHaveBeenCalledWith('proj_1'));
});

test('renders project chat page', async () => {
  render(<MemoryRouter initialEntries={['/projects/proj_1/chat']}><App /></MemoryRouter>);
  expect(await screen.findByText('AI 聊天助手')).toBeInTheDocument();
  expect(await screen.findByText('项目 ID：proj_1')).toBeInTheDocument();
  expect(apiMocks.createProjectChatSession).toHaveBeenCalledWith('proj_1');
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
  render(<MemoryRouter initialEntries={['/legacy/new-evaluation']}><App /></MemoryRouter>);
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
