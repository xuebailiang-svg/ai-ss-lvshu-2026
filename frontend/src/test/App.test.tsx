import {cleanup, fireEvent, render, screen, waitFor} from '@testing-library/react';
import {MemoryRouter} from 'react-router-dom';
import {afterEach, beforeEach, expect, test, vi} from 'vitest';
import App from '../App';

const mocks = vi.hoisted(() => ({
  listProjects: vi.fn(),
  deleteProject: vi.fn(),
  getProject: vi.fn(),
  getProjectDataset: vi.fn(),
  getProjectDataQuality: vi.fn(),
  listProjectCompetitors: vi.fn(),
  listProjectSupporting: vi.fn(),
  listProjectRent: vi.fn(),
  generateProjectAiQuestions: vi.fn(),
  saveProjectAiQuestionAnswers: vi.fn(),
  generateAiReport: vi.fn(),
  getManagedSystemConfig: vi.fn(),
}));

vi.mock('../api/projects', async () => {
  const actual = await vi.importActual<typeof import('../api/projects')>('../api/projects');
  return {
    ...actual,
    listProjects: mocks.listProjects,
    deleteProject: mocks.deleteProject,
    getProject: mocks.getProject,
    getProjectDataset: mocks.getProjectDataset,
    getProjectDataQuality: mocks.getProjectDataQuality,
    listProjectCompetitors: mocks.listProjectCompetitors,
    listProjectSupporting: mocks.listProjectSupporting,
    listProjectRent: mocks.listProjectRent,
    generateProjectAiQuestions: mocks.generateProjectAiQuestions,
    saveProjectAiQuestionAnswers: mocks.saveProjectAiQuestionAnswers,
  };
});

vi.mock('../api/client', async () => {
  const actual = await vi.importActual<typeof import('../api/client')>('../api/client');
  return {...actual, getManagedSystemConfig: mocks.getManagedSystemConfig};
});

vi.mock('../api/report', () => ({generateAiReport: mocks.generateAiReport}));

beforeEach(() => {
  mocks.listProjects.mockResolvedValue({items: []});
  mocks.deleteProject.mockResolvedValue({});
  mocks.getProject.mockResolvedValue({
    project: {
      project_id: 'proj_1',
      name: '小寨电竞馆选址',
      city: '西安市',
      district: '雁塔区',
      address: '小寨地铁站',
      longitude: 108.95,
      latitude: 34.22,
      radius_meters: 1000,
      business_type: '电竞馆',
      status: 'confirmed',
    },
    stats: {poi_count: 20, competitor_count: 3, food_count: 5, entertainment_count: 4},
  });
  mocks.getProjectDataset.mockResolvedValue({
    project: {project_id: 'proj_1'},
    pois: [],
    competitors: [],
    food_businesses: [],
    entertainments: [],
    rent_data: {},
    population_data: {},
    supplements: [],
  });
  mocks.getProjectDataQuality.mockResolvedValue({quality_score: 0, missing: [], warnings: []});
  mocks.listProjectCompetitors.mockResolvedValue({items: [], total: 0});
  mocks.listProjectSupporting.mockResolvedValue({items: [], total: 0, effective_count: 0, stats: {}});
  mocks.listProjectRent.mockResolvedValue({items: [], total: 0, incomplete_count: 0, confirmed_count: 0});
  mocks.generateProjectAiQuestions.mockResolvedValue({
    success: true,
    status: 'questions_ready',
    round: 1,
    asked_count: 1,
    remaining_candidate_count: 2,
    message: '请回答以下重要问题',
    questions: [{
      question_id: 'q_1',
      field_key: 'property:primary:address',
      target_type: 'property',
      target_id: 'primary',
      title: '候选物业的详细地址是什么？',
      help_text: '填写实际考察物业地址。',
      answer_type: 'text',
      unit: null,
      options: [],
      round: 1,
    }],
  });
  mocks.saveProjectAiQuestionAnswers.mockResolvedValue({
    success: true,
    saved_count: 1,
    unknown_count: 0,
    skipped_count: 0,
    can_continue: false,
    message: '回答已保存到当前项目',
  });
  mocks.generateAiReport.mockResolvedValue({
    success: true,
    report_id: 'report_1',
    model: 'deepseek-chat',
    validation_status: 'passed',
    snapshot_version: 'final-project-snapshot-v1',
    content: '# 电竞馆选址分析报告\n\n## 一、项目概况\n只使用最终快照。\n\n## 二、核心结论\n谨慎。\n\n## 三、交通环境\n无法判断。\n\n## 四、竞争环境\n无法判断。',
  });
  mocks.getManagedSystemConfig.mockResolvedValue({
    management_enabled: true,
    deepseek: {configured: true, source: 'database', masked: 'sk-***'},
    amap: {configured: true, source: 'database', masked: 'amap-***'},
    deepseek_base_url: 'https://api.deepseek.com',
    deepseek_model: 'deepseek-chat',
    warnings: [],
  });
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

test('根路由只展示项目与配置两个主入口', async () => {
  render(<MemoryRouter initialEntries={['/']}><App /></MemoryRouter>);

  expect(await screen.findByRole('heading', {name: '选址项目'})).toBeInTheDocument();
  expect(screen.getByRole('link', {name: '选址项目'})).toBeInTheDocument();
  expect(screen.getByRole('link', {name: '系统配置'})).toBeInTheDocument();
  expect(screen.queryByText('Agent')).not.toBeInTheDocument();
  expect(screen.queryByText('历史评估')).not.toBeInTheDocument();
});

test('旧功能路由会安全回到项目列表', async () => {
  render(<MemoryRouter initialEntries={['/agent']}><App /></MemoryRouter>);
  expect(await screen.findByRole('heading', {name: '选址项目'})).toBeInTheDocument();
});

test('旧项目详情路由会进入收敛后的六步项目流程', async () => {
  render(<MemoryRouter initialEntries={['/legacy/projects/proj_1/data-center']}><App /></MemoryRouter>);

  expect(await screen.findByRole('heading', {name: '项目工作台'})).toBeInTheDocument();
  expect(screen.getByText('输入地址和范围')).toBeInTheDocument();
  expect(screen.getAllByText('获取高德 POI').length).toBeGreaterThan(0);
  expect(screen.getByText('查看与人工补充')).toBeInTheDocument();
  expect(screen.getAllByText('数据检查').length).toBeGreaterThan(0);
  expect(screen.getByText('确认重要信息')).toBeInTheDocument();
  expect(screen.getByText('生成 AI 选址报告')).toBeInTheDocument();
  expect(screen.queryByText('爬虫补充')).not.toBeInTheDocument();
  expect(screen.queryByText('评分分析')).not.toBeInTheDocument();
});

test('项目数据检查按四类业务准备度展示', async () => {
  mocks.getProjectDataQuality.mockResolvedValue({
    quality_score: 40,
    missing: ['高德基础采集'],
    warnings: [],
    readiness: {
      status: 'blocked',
      completion_percent: 40,
      score_explanation: '准备度按固定检查项权重汇总，不代表项目推荐概率。',
      summary: {complete: 2, missing: 2, blocked: 1},
      groups: {
        technical_prerequisites: [{id: 'amap_collection', label: '高德基础采集', status: 'blocked', summary: '尚未执行高德采集。'}],
        key_unknowns: [{id: 'candidate_property', label: '候选物业核心条件', status: 'missing', summary: '地址、面积和月租待补充。'}],
        recommended: [],
        optional: [{id: 'optional_sales', label: '竞品营业额', status: 'optional', summary: '不影响数据准备度。'}],
      },
    },
  });
  render(<MemoryRouter initialEntries={['/projects/proj_1']}><App /></MemoryRouter>);

  fireEvent.click(await screen.findByRole('button', {name: '检查数据准备度'}));

  expect(await screen.findByText('技术前置条件未完成')).toBeInTheDocument();
  expect(screen.getByText('技术前置条件')).toBeInTheDocument();
  expect(screen.getByText('关键未知')).toBeInTheDocument();
  expect(screen.getByText('建议补充')).toBeInTheDocument();
  expect(screen.getByText('可选信息')).toBeInTheDocument();
  expect(screen.getByText('竞品营业额')).toBeInTheDocument();
});

test('重要信息由 AI 选择问题且只保存用户明确回答', async () => {
  render(<MemoryRouter initialEntries={['/projects/proj_1']}><App /></MemoryRouter>);

  fireEvent.click(await screen.findByRole('button', {name: '生成重要问题'}));
  expect(await screen.findByText('候选物业的详细地址是什么？')).toBeInTheDocument();
  fireEvent.change(screen.getByPlaceholderText('请输入实际核实信息'), {target: {value: '小寨东路 100 号'}});
  fireEvent.click(screen.getByRole('button', {name: '保存本轮回答'}));

  await waitFor(() => expect(mocks.saveProjectAiQuestionAnswers).toHaveBeenCalledWith('proj_1', [{
    question_id: 'q_1',
    value: '小寨东路 100 号',
    unknown: false,
    skip: false,
  }]));
  await waitFor(() => expect(mocks.getProjectDataQuality).toHaveBeenCalled());
});

test('真实性校验通过的报告显示来源边界和打印入口', async () => {
  render(<MemoryRouter initialEntries={['/projects/proj_1']}><App /></MemoryRouter>);

  fireEvent.click(await screen.findByRole('button', {name: '检查数据准备度'}));
  await waitFor(() => expect(mocks.getProjectDataQuality).toHaveBeenCalled());
  fireEvent.click(await screen.findByRole('button', {name: '生成 AI 报告'}));

  expect(await screen.findByText('真实性校验已通过')).toBeInTheDocument();
  expect(screen.getByText(/报告只读取高德事实、用户人工提供信息和确定性计算/)).toBeInTheDocument();
  expect(screen.getAllByRole('button', {name: /打印 \/ PDF/})).toHaveLength(2);
  expect(screen.getAllByRole('button', {name: /导出 HTML/})).toHaveLength(2);
});

test('项目列表使用紧凑卡片展示进度并分离打开删除操作', async () => {
  mocks.listProjects.mockResolvedValue({items: [{
    project_id: 'proj_card', name: '西部电子社区', city: '西安市', district: '雁塔区', address: '西部电子社区',
    longitude: 108.9, latitude: 34.2, status: 'confirmed', stats: {poi_count: 12, missing_fields: ['真实租金']},
  }]});
  render(<MemoryRouter initialEntries={['/']}><App /></MemoryRouter>);

  expect(await screen.findByTestId('project-list-card')).toBeInTheDocument();
  expect(screen.getByText('Step 3 / 6')).toBeInTheDocument();
  expect(screen.getByRole('button', {name: /打开/})).toBeInTheDocument();
  expect(screen.getByRole('button', {name: /删除/})).toBeInTheDocument();
});

test('新建项目的面积、预算和分析范围单位与输入框一体展示', async () => {
  render(<MemoryRouter initialEntries={['/projects/create']}><App /></MemoryRouter>);

  expect(await screen.findByRole('heading', {name: '创建选址项目'})).toBeInTheDocument();
  expect(screen.getByText('㎡')).toBeInTheDocument();
  expect(screen.getByText('元')).toBeInTheDocument();
  expect(screen.getByText('米')).toBeInTheDocument();
});

test('配置页只保留 DeepSeek 与高德 Web Service', async () => {
  render(<MemoryRouter initialEntries={['/settings']}><App /></MemoryRouter>);

  expect(await screen.findByRole('heading', {name: '系统配置'})).toBeInTheDocument();
  expect(screen.getByText('DeepSeek')).toBeInTheDocument();
  expect(screen.getByText('高德地图 Web Service')).toBeInTheDocument();
  await waitFor(() => expect(mocks.getManagedSystemConfig).toHaveBeenCalled());
  expect(screen.queryByText(/爬虫数据源/)).not.toBeInTheDocument();
  expect(screen.queryByText(/政府公开数据/)).not.toBeInTheDocument();
  expect(screen.queryByText(/评分维度/)).not.toBeInTheDocument();
  expect(screen.queryByText(/Memory/)).not.toBeInTheDocument();
});
