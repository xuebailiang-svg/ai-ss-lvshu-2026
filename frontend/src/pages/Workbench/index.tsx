import {useEffect, useMemo, useState} from 'react';
import {
  Alert,
  Button,
  Card,
  Col,
  Divider,
  Form,
  Input,
  InputNumber,
  List,
  Popconfirm,
  Progress,
  Row,
  Space,
  Statistic,
  Steps,
  Tag,
  Typography,
  message,
} from 'antd';
import {
  CloudDownloadOutlined,
  DeleteOutlined,
  FileTextOutlined,
  PlusOutlined,
  ReloadOutlined,
  RobotOutlined,
  SendOutlined,
} from '@ant-design/icons';
import {
  collectProjectAmap,
  collectProjectCompetitors,
  collectProjectSupporting,
  createProject,
  deleteProject,
  generateProjectAiReview,
  getProjectDataQuality,
  listProjects,
  type ProjectCreatePayload,
} from '../../api/projects';
import {scoreProject} from '../../api/score';
import {generateAiReport} from '../../api/report';
import {createProjectChatSession, sendProjectChatMessage} from '../../api/chat';
import {getDataSourceStatus, type DataSourceStatus} from '../../api/dataSources';
import {getScoringConfig, type ScoringDimensionConfig} from '../../api/scoringConfig';
import {listMemory, type MemoryItem} from '../../api/memory';
import MarkdownReport from '../../components/MarkdownReport';
import {useNavigate} from 'react-router-dom';

type ProjectItem = {
  project_id: string;
  name?: string;
  project_name?: string;
  city?: string;
  district?: string;
  address?: string;
  longitude?: number | null;
  latitude?: number | null;
  radius_meters?: number;
  business_type?: string;
  status?: string;
  created_at?: string | null;
  stats?: Record<string, unknown>;
};

type ChatMessage = {
  role: 'user' | 'assistant' | 'system';
  content: string;
};

type ActionResult = {
  type: 'success' | 'warning' | 'error' | 'info';
  title: string;
  content: string;
};

const QUICK_MESSAGES = [
  '西安市小寨地铁站 1000 米，电竞馆，帮我做一次选址分析',
  '这个项目当前缺哪些关键数据？',
  '竞品压力和夜间消费环境怎么样？',
  '生成一份适合投资人看的报告',
];

const STATUS_TEXT: Record<string, string> = {
  draft: '初始化',
  pending_review: '待确认',
  confirmed: '已创建',
  collecting: '数据采集中',
  data_ready: '数据已就绪',
  supplementing: '数据补充中',
  scored: '分析完成',
  reported: '已生成报告',
};

function projectTitle(project?: ProjectItem | null) {
  if (!project) return '未选择项目';
  return project.name || project.project_name || project.address || project.project_id;
}

function statusText(status?: string) {
  return STATUS_TEXT[status || ''] || '初始化';
}

function errorText(error: any, fallback: string) {
  const detail = error?.response?.data?.detail;
  if (typeof detail === 'string') return detail;
  if (detail?.message) return detail.message;
  return error?.message || fallback;
}

function countText(value: unknown) {
  if (value === undefined || value === null || value === '') return '--';
  return String(value);
}

function shortProjectId(projectId: string) {
  return projectId.length > 6 ? projectId.slice(-6) : projectId;
}

function formatDateTime(value?: string | null) {
  if (!value) return '创建时间未知';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return '创建时间未知';
  return date.toLocaleString('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  });
}

function numberFromStats(project: ProjectItem, key: string) {
  const value = project.stats?.[key];
  return typeof value === 'number' ? value : 0;
}

type WorkflowStep = {
  title: string;
  description: string;
  status: 'wait' | 'process' | 'finish';
};

type SupplementSuggestion = {
  focus: 'competitor' | 'rent' | 'support' | 'population' | 'property' | 'general';
  category: string;
  priority: '高' | '中' | '低';
  reason: string;
  fields: string[];
};

function hasProjectLocation(project?: ProjectItem | null) {
  return typeof project?.longitude === 'number' && typeof project?.latitude === 'number';
}

function buildWorkflowSteps(
  project: ProjectItem | null,
  quality: any,
  score: any,
  reportContent: string,
): WorkflowStep[] {
  const hasProject = Boolean(project);
  const poiCount = project ? numberFromStats(project, 'poi_count') : 0;
  const competitorCount = project ? numberFromStats(project, 'competitor_count') : 0;
  const foodCount = project ? numberFromStats(project, 'food_count') : 0;
  const entertainmentCount = project ? numberFromStats(project, 'entertainment_count') : 0;
  const rentCount = project ? numberFromStats(project, 'rent_count') : 0;
  const hasBaseData = poiCount > 0 || competitorCount > 0 || foodCount > 0 || entertainmentCount > 0;
  const hasSupplementData = competitorCount > 0 || rentCount > 0;
  const qualityScore = Number(quality?.quality_score) || 0;

  return [
    {
      title: '新建或选择项目',
      description: hasProject ? `当前项目：${projectTitle(project)}` : '先在左侧新建项目，或选择已有项目。',
      status: hasProject ? 'finish' : 'process',
    },
    {
      title: '确认地址和范围',
      description: hasProject
        ? hasProjectLocation(project)
          ? '项目已有经纬度，可直接采集周边数据。'
          : '项目暂缺经纬度，采集高德 POI 时会先尝试根据城市和地址解析坐标。'
        : '创建项目时填写城市、详细地址、分析半径、经营类型。',
      status: !hasProject ? 'wait' : hasProjectLocation(project) ? 'finish' : 'process',
    },
    {
      title: '采集基础数据',
      description: hasBaseData
        ? `已采集：POI ${poiCount}、竞品 ${competitorCount}、餐饮 ${foodCount}、娱乐 ${entertainmentCount}。`
        : '点击采集高德 POI、获取竞品、获取配套，建立基础数据底座。',
      status: hasBaseData ? 'finish' : hasProject ? 'process' : 'wait',
    },
    {
      title: '人工确认和补充',
      description: hasSupplementData
        ? '已有部分竞品或租金数据，建议继续确认有效性并补充经营信息。'
        : '确认疑似竞品、配套是否真实有效，并补充租金、价格、配置、上座率等人工数据。',
      status: hasSupplementData ? 'finish' : hasBaseData ? 'process' : 'wait',
    },
    {
      title: '数据核验',
      description: quality
        ? `当前完整度 ${qualityScore}%，缺失 ${Array.isArray(quality.missing) ? quality.missing.length : 0} 项。`
        : '点击 AI 数据核验，系统会先检查已有数据和缺失数据，再给出 AI 初审结论和补充建议。',
      status: quality ? 'finish' : hasBaseData ? 'process' : 'wait',
    },
    {
      title: '评分分析',
      description: score ? `综合评分 ${countText(score.total_score)}，评级 ${score.level || '--'}。` : '数据核验后执行评分，得到各维度得分和风险项。',
      status: score ? 'finish' : quality ? 'process' : 'wait',
    },
    {
      title: '生成报告和继续咨询',
      description: reportContent ? '报告已生成，可导出 HTML 或打印为 PDF。' : '生成客户可读报告，并围绕项目继续向 AI 咨询。',
      status: reportContent ? 'finish' : score ? 'process' : 'wait',
    },
  ];
}

function buildSupplementSuggestions(quality: any): SupplementSuggestion[] {
  const missing = Array.isArray(quality?.missing) ? quality.missing.map(String) : [];
  const warnings = Array.isArray(quality?.warnings) ? quality.warnings.map(String) : [];
  const combined = [...missing, ...warnings].join(' ');
  const suggestions: SupplementSuggestion[] = [];

  const add = (item: SupplementSuggestion) => {
    if (!suggestions.some(existing => existing.category === item.category)) suggestions.push(item);
  };

  if (/竞品|竞争|价格|上座率|配置|机器|显卡|GPU/i.test(combined)) {
    add({
      focus: 'competitor',
      category: '竞品经营信息',
      priority: '高',
      reason: '电竞馆选址需要判断周边竞品真实经营强度，只有名称和距离不足以支撑报告结论。',
      fields: ['竞品是否真实有效', '价格', '机器数量', 'CPU/GPU/显示器', '上座率', '营业时间', '充值活动'],
    });
  }

  if (/租金|成本|物业|转让|面积/i.test(combined)) {
    add({
      focus: 'rent',
      category: '租金成本信息',
      priority: '高',
      reason: '租金和面积会直接影响成本压力判断，缺失时报告只能提示风险，不能判断成本是否合理。',
      fields: ['月租金', '面积', '物业费', '转让费', '租金来源', '楼层/位置说明'],
    });
  }

  if (/夜间|营业时间|24|便利店|餐饮|娱乐|配套/i.test(combined)) {
    add({
      focus: 'support',
      category: '夜间消费和配套',
      priority: '中',
      reason: '电竞馆高度依赖夜间消费环境，需要人工确认商户是否真实夜间营业。',
      fields: ['餐饮营业时间', '是否夜间营业', '24小时便利店', 'KTV/酒吧/台球等娱乐配套', '夜间人流观察'],
    });
  }

  if (/人口|大学|技校|公寓|住宅|客群/i.test(combined)) {
    add({
      focus: 'population',
      category: '客群人口信息',
      priority: '中',
      reason: '年轻客群密度会影响潜在消费能力，需要补充学校、公寓、年轻住宅等现场观察信息。',
      fields: ['周边大学/高职/技校', '公寓数量', '年轻住宅/回迁房情况', '夜间年轻人流'],
    });
  }

  if (/物业|消防|供电|网络|停车|门头|层高/i.test(combined)) {
    add({
      focus: 'property',
      category: '物业条件',
      priority: '高',
      reason: '物业、消防、供电和网络条件属于开店落地风险，不能只靠 POI 判断。',
      fields: ['可用面积', '层高', '供电容量', '网络运营商', '消防条件', '停车条件', '门头可见度'],
    });
  }

  if (!suggestions.length && quality) {
    add({
      focus: 'general',
      category: '常规人工复核',
      priority: '低',
      reason: '当前结构化核验未发现明确缺失项，但正式报告前仍建议人工复核关键数据真实性。',
      fields: ['竞品真实性', '租金来源', '夜间营业情况', '物业落地条件'],
    });
  }

  return suggestions;
}

function summarizeAction(action: string, result: any) {
  if (result?.success === false) {
    return `${action}失败：${result.message || '服务暂时不可用，请检查配置或稍后重试。'}`;
  }

  if (action === '高德 POI 采集') {
    const collected = result?.collected || {};
    return [
      '高德 POI 采集完成。',
      `POI：${countText(collected.poi_count)}`,
      `疑似竞品：${countText(collected.competitor_count)}`,
      `餐饮：${countText(collected.food_count)}`,
      `娱乐：${countText(collected.entertainment_count)}`,
      '下一步建议：确认竞品和配套是否有效，再做数据核验。',
    ].join('\n');
  }

  if (action === '竞品采集') {
    const count = result?.discovered_count ?? result?.competitor_count ?? result?.saved_count ?? result?.imported_rows;
    return `竞品采集完成：发现 ${countText(count)} 个疑似竞品，请在后续流程中人工确认。`;
  }

  if (action === '周边配套采集') {
    return [
      '周边配套采集完成。',
      `餐饮：${countText(result?.food_count)}`,
      `娱乐：${countText(result?.entertainment_count)}`,
      `夜间商业候选：${countText(result?.night_business_count)}`,
    ].join('\n');
  }

  if (action === '数据核验') {
    const missing = Array.isArray(result?.missing) ? result.missing : [];
    const warnings = Array.isArray(result?.warnings) ? result.warnings : [];
    return [
      `数据核验完成：完整度 ${countText(result?.quality_score)}%。`,
      missing.length ? `仍缺少：${missing.join('、')}` : '关键数据暂未发现明显缺失。',
      warnings.length ? `风险提示：${warnings.join('、')}` : '暂无额外风险提示。',
    ].join('\n');
  }

  if (action === '评分分析') {
    return `评分分析完成：综合评分 ${countText(result?.total_score)} 分，评级 ${result?.level || '--'}。`;
  }

  if (action === 'AI 报告生成') {
    return 'AI 报告已生成，可在下方查看并导出。';
  }

  return `${action}完成。`;
}

function downloadHtml(filename: string, markdown: string) {
  const escaped = markdown
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;');
  const html = `<!doctype html><html lang="zh-CN"><head><meta charset="UTF-8"><title>${filename}</title><style>
body{font-family:-apple-system,BlinkMacSystemFont,"Microsoft YaHei",Arial,sans-serif;max-width:960px;margin:32px auto;color:#1f2937;line-height:1.8}
h1,h2,h3{color:#102033}.report{white-space:pre-wrap;background:#fff;padding:24px;border:1px solid #e5e7eb;border-radius:12px}
</style></head><body><article class="report">${escaped}</article></body></html>`;
  const blob = new Blob([html], {type: 'text/html;charset=utf-8'});
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = filename;
  anchor.click();
  URL.revokeObjectURL(url);
}

export default function WorkbenchPage() {
  const navigate = useNavigate();
  const [projectForm] = Form.useForm<ProjectCreatePayload>();
  const [projects, setProjects] = useState<ProjectItem[]>([]);
  const [selectedProjectId, setSelectedProjectId] = useState('');
  const [creating, setCreating] = useState(false);
  const [loadingProjects, setLoadingProjects] = useState(false);
  const [deletingProjectId, setDeletingProjectId] = useState('');
  const [actionLoading, setActionLoading] = useState('');
  const [quality, setQuality] = useState<any>(null);
  const [aiReview, setAiReview] = useState<any>(null);
  const [score, setScore] = useState<any>(null);
  const [report, setReport] = useState<any>(null);
  const [dataSources, setDataSources] = useState<DataSourceStatus[]>([]);
  const [dimensions, setDimensions] = useState<ScoringDimensionConfig[]>([]);
  const [memories, setMemories] = useState<MemoryItem[]>([]);
  const [sessionId, setSessionId] = useState('');
  const [chatInput, setChatInput] = useState('');
  const [actionResults, setActionResults] = useState<Record<string, ActionResult>>({});
  const [messages, setMessages] = useState<ChatMessage[]>([
    {
      role: 'system',
      content: '这是面向客户的选址工作台。先创建或选择项目，再按步骤采集数据、核验数据、评分和生成报告。',
    },
  ]);

  const selectedProject = useMemo(
    () => projects.find(item => item.project_id === selectedProjectId) || null,
    [projects, selectedProjectId],
  );

  const loadProjects = async (preferredProjectId?: string) => {
    setLoadingProjects(true);
    try {
      const result = await listProjects();
      const items: ProjectItem[] = Array.isArray(result?.items) ? result.items : [];
      setProjects(items);
      const nextId = preferredProjectId && items.some(item => item.project_id === preferredProjectId)
        ? preferredProjectId
        : items.some(item => item.project_id === selectedProjectId)
          ? selectedProjectId
          : items[0]?.project_id || '';
      setSelectedProjectId(nextId);
    } catch (error: any) {
      message.error(errorText(error, '项目列表加载失败'));
    } finally {
      setLoadingProjects(false);
    }
  };

  const loadSideContext = async (projectId?: string) => {
    try {
      const [sourceResult, configResult, memoryResult] = await Promise.all([
        getDataSourceStatus().catch(() => ({items: []})),
        getScoringConfig().catch(() => ({dimensions: [], total_weight: 0, normalized: false})),
        projectId
          ? listMemory({project_id: projectId, status: 'confirmed'}).catch(() => ({items: [], total: 0}))
          : Promise.resolve({items: [], total: 0}),
      ]);
      setDataSources(sourceResult.items || []);
      setDimensions(configResult.dimensions || []);
      setMemories(memoryResult.items || []);
    } catch {
      // 右侧上下文失败不阻断工作台主流程。
    }
  };

  useEffect(() => {
    void loadProjects();
    void loadSideContext();
  }, []);

  useEffect(() => {
    if (!selectedProjectId) return;
    setQuality(null);
    setAiReview(null);
    setScore(null);
    setReport(null);
    setSessionId('');
    setActionResults({});
    void loadSideContext(selectedProjectId);
    createProjectChatSession(selectedProjectId)
      .then(result => setSessionId(String(result.session_id)))
      .catch(() => setSessionId(''));
  }, [selectedProjectId]);

  const createNewProject = async (values: ProjectCreatePayload) => {
    setCreating(true);
    try {
      const result = await createProject(values);
      await loadProjects(result.project_id);
      setActionResults({
        create: {
          type: 'success',
          title: '项目已创建',
          content: `已创建项目：${values.name || values.address}\n下一步：采集高德 POI，获取周边基础数据。`,
        },
      });
      setMessages(previous => [
        ...previous,
        {
          role: 'system',
          content: `已创建项目：${values.name || values.address}\n下一步建议：点击“采集高德 POI”获取周边基础数据。`,
        },
      ]);
      projectForm.resetFields();
    } catch (error: any) {
      message.error(errorText(error, '创建项目失败'));
    } finally {
      setCreating(false);
    }
  };

  const removeProject = async (project: ProjectItem) => {
    setDeletingProjectId(project.project_id);
    try {
      await deleteProject(project.project_id);
      message.success('项目已删除');
      setMessages(previous => [...previous, {role: 'system', content: `已删除项目：${projectTitle(project)}`}]);
      await loadProjects(project.project_id === selectedProjectId ? undefined : selectedProjectId);
    } catch (error: any) {
      message.error(errorText(error, '删除项目失败'));
    } finally {
      setDeletingProjectId('');
    }
  };

  const runAction = async (loadingKey: string, actionName: string, fn: () => Promise<any>) => {
    if (!selectedProjectId) {
      message.warning('请先选择或创建项目');
      return null;
    }

    setActionLoading(loadingKey);
    try {
      const result = await fn();
      const summary = summarizeAction(actionName, result);
      setActionResults(previous => ({
        ...previous,
        [loadingKey]: {
          type: result?.success === false ? 'warning' : 'success',
          title: result?.success === false ? `${actionName}未完成` : `${actionName}完成`,
          content: summary,
        },
      }));
      if (result?.success === false) {
        message.warning(result.message || `${actionName}失败`);
      } else {
        message.success(`${actionName}完成`);
      }
      await loadProjects(selectedProjectId);
      await loadSideContext(selectedProjectId);
      return result;
    } catch (error: any) {
      const reason = errorText(error, `${actionName}失败`);
      setActionResults(previous => ({
        ...previous,
        [loadingKey]: {
          type: 'error',
          title: `${actionName}失败`,
          content: reason,
        },
      }));
      message.error(reason);
      return null;
    } finally {
      setActionLoading('');
    }
  };

  const checkQuality = async () => {
    const result = await runAction('quality', '数据核验', () => getProjectDataQuality(selectedProjectId));
    if (!result) return;
    setQuality(result);
    setActionLoading('ai-review');
    try {
      const review = await generateProjectAiReview(selectedProjectId);
      setAiReview(review);
      if (review?.success === false) {
        setMessages(previous => [
          ...previous,
          {role: 'system', content: `AI 数据审核暂未完成：${review.message || '请检查 DeepSeek 配置。'}\n已展示结构化数据核验结果。`},
        ]);
        setActionResults(previous => ({
          ...previous,
          aiReview: {
            type: 'warning',
            title: 'AI 数据审核暂未完成',
            content: `${review.message || '请检查 DeepSeek 配置。'}\n已展示结构化数据核验结果。`,
          },
        }));
        message.warning(review.message || 'AI 数据审核暂不可用，已展示结构化核验结果');
      } else {
        setMessages(previous => [...previous, {role: 'system', content: 'AI 数据审核完成：已生成已有数据、缺失数据和人工补充建议。'}]);
        setActionResults(previous => ({
          ...previous,
          aiReview: {
            type: 'success',
            title: 'AI 数据审核完成',
            content: '已生成已有数据、缺失数据和人工补充建议。请查看下方 AI 数据核验结论。',
          },
        }));
        message.success('AI 数据审核完成');
      }
    } catch (error: any) {
      const reason = errorText(error, 'AI 数据审核失败');
      setAiReview({success: false, message: reason});
      setActionResults(previous => ({
        ...previous,
        aiReview: {
          type: 'warning',
          title: 'AI 数据审核失败',
          content: `${reason}\n已展示结构化数据核验结果。`,
        },
      }));
      message.warning('AI 数据审核失败，已展示结构化核验结果');
    } finally {
      setActionLoading('');
    }
  };

  const runScore = async () => {
    const result = await runAction('score', '评分分析', () => scoreProject(selectedProjectId));
    if (result) setScore(result);
  };

  const runReport = async () => {
    const result = await runAction('report', 'AI 报告生成', () => generateAiReport(selectedProjectId));
    if (result?.success === false) {
      setReport(null);
      return;
    }
    if (result) setReport(result);
  };

  const sendMessage = async () => {
    const content = chatInput.trim();
    if (!content) return;
    setChatInput('');
    setMessages(previous => [...previous, {role: 'user', content}]);
    if (!selectedProjectId || !sessionId) {
      setMessages(previous => [...previous, {role: 'assistant', content: '请先选择或创建一个选址项目，再进行项目上下文问答。'}]);
      return;
    }
    setActionLoading('chat');
    try {
      const result = await sendProjectChatMessage(sessionId, content);
      setMessages(previous => [...previous, {role: 'assistant', content: result.answer || 'AI 暂无可展示回答。'}]);
    } catch (error: any) {
      setMessages(previous => [...previous, {role: 'assistant', content: `AI 助手暂时不可用：${errorText(error, '请求失败')}`}]);
    } finally {
      setActionLoading('');
    }
  };

  const qualityScore = Number(quality?.quality_score) || 0;
  const reportContent = String(report?.content || '');
  const scoreDimensions = score?.dimensions && typeof score.dimensions === 'object'
    ? Object.entries(score.dimensions as Record<string, any>)
    : [];
  const supplementSuggestions = buildSupplementSuggestions(quality);
  const workflowSteps = buildWorkflowSteps(selectedProject, quality, score, reportContent);
  const currentWorkflowIndex = Math.max(0, workflowSteps.findIndex(item => item.status !== 'finish'));
  const activeWorkflowStep = workflowSteps[currentWorkflowIndex] || workflowSteps[workflowSteps.length - 1];
  const projectPoiCount = selectedProject ? numberFromStats(selectedProject, 'poi_count') : 0;
  const projectCompetitorCount = selectedProject ? numberFromStats(selectedProject, 'competitor_count') : 0;
  const projectFoodCount = selectedProject ? numberFromStats(selectedProject, 'food_count') : 0;
  const projectEntertainmentCount = selectedProject ? numberFromStats(selectedProject, 'entertainment_count') : 0;
  const projectRentCount = selectedProject ? numberFromStats(selectedProject, 'rent_count') : 0;
  const inlineResult = (key: string) => {
    const item = actionResults[key];
    if (!item) return null;
    return (
      <Alert
        type={item.type}
        showIcon
        message={item.title}
        description={<Typography.Paragraph style={{whiteSpace: 'pre-wrap', marginBottom: 0}}>{item.content}</Typography.Paragraph>}
      />
    );
  };

  return (
    <div className="v11-workbench">
      <aside className="v11-left-panel">
        <Card title="项目" extra={<Button size="small" icon={<ReloadOutlined />} onClick={() => loadProjects()} loading={loadingProjects}>刷新</Button>}>
          <List
            size="small"
            dataSource={projects}
            locale={{emptyText: '暂无项目，请先新建'}}
            renderItem={item => {
              const isActive = item.project_id === selectedProjectId;
              const poiCount = numberFromStats(item, 'poi_count');
              const competitorCount = numberFromStats(item, 'competitor_count');
              const rentCount = numberFromStats(item, 'rent_count');
              const completionCount = [poiCount > 0, competitorCount > 0, rentCount > 0].filter(Boolean).length;
              return (
                <List.Item
                  className={isActive ? 'v11-project-item active' : 'v11-project-item'}
                  onClick={() => setSelectedProjectId(item.project_id)}
                  actions={[
                    <Button
                      key="open"
                      size="small"
                      type={isActive ? 'primary' : 'default'}
                      onClick={event => {
                        event.stopPropagation();
                        setSelectedProjectId(item.project_id);
                      }}
                    >
                      {isActive ? '已打开' : '打开'}
                    </Button>,
                    <Popconfirm
                      key="delete"
                      title="确认删除该项目？"
                      description="删除后默认不再显示，项目相关数据会保留在数据库中。"
                      okText="删除"
                      cancelText="取消"
                      okButtonProps={{danger: true}}
                      onConfirm={event => {
                        event?.stopPropagation?.();
                        return removeProject(item);
                      }}
                    >
                      <Button
                        size="small"
                        danger
                        icon={<DeleteOutlined />}
                        loading={deletingProjectId === item.project_id}
                        onClick={event => event.stopPropagation()}
                      >
                        删除
                      </Button>
                    </Popconfirm>,
                  ]}
                >
                  <List.Item.Meta
                    title={
                      <Space size={6} wrap className="v11-project-title-line">
                        <span className="v11-project-title-text">{projectTitle(item)}</span>
                        {isActive && <Tag color="blue">当前</Tag>}
                      </Space>
                    }
                    description={
                      <Space size={[4, 4]} wrap>
                        <Tag>{statusText(item.status)}</Tag>
                        <Tag color={completionCount >= 2 ? 'green' : completionCount === 1 ? 'orange' : 'default'}>
                          完成 {completionCount}/3
                        </Tag>
                        <Tag color={poiCount > 0 ? 'green' : 'default'}>POI {poiCount}</Tag>
                      </Space>
                    }
                  />
                </List.Item>
              );
            }}
          />
        </Card>

        <Card title="新建选址项目" className="v11-create-card">
          <Form
            form={projectForm}
            layout="vertical"
            initialValues={{city: '西安市', radius_meters: 1000, business_type: '电竞馆'}}
            onFinish={createNewProject}
          >
            <Form.Item name="name" label="项目名称" rules={[{required: true, message: '请输入项目名称'}]}>
              <Input placeholder="例如：小寨电竞馆选址" />
            </Form.Item>
            <Row gutter={8}>
              <Col span={12}><Form.Item name="city" label="城市" rules={[{required: true}]}><Input /></Form.Item></Col>
              <Col span={12}><Form.Item name="district" label="区域"><Input placeholder="例如：雁塔区" /></Form.Item></Col>
            </Row>
            <Form.Item name="address" label="详细地址" rules={[{required: true, message: '请输入地址'}]}>
              <Input placeholder="例如：小寨地铁站" />
            </Form.Item>
            <Row gutter={8}>
              <Col span={12}>
                <Form.Item name="radius_meters" label="分析范围（米）">
                  <InputNumber min={200} max={5000} addonAfter="米" style={{width: '100%'}} />
                </Form.Item>
              </Col>
              <Col span={12}><Form.Item name="business_type" label="经营类型"><Input /></Form.Item></Col>
            </Row>
            <Form.Item name="expected_area_sqm" label="预计面积（㎡）">
              <InputNumber min={0} addonAfter="㎡" style={{width: '100%'}} />
            </Form.Item>
            <Form.Item name="investment_budget" label="投资预算（万元）">
              <InputNumber min={0} addonAfter="万元" style={{width: '100%'}} />
            </Form.Item>
            <Button type="primary" icon={<PlusOutlined />} htmlType="submit" loading={creating} block>创建项目</Button>
          </Form>
        </Card>
      </aside>

      <main className="v11-center-panel">
        <Card className="v11-project-header">
          <Space direction="vertical" size={4}>
            <Typography.Title level={3} style={{margin: 0}}>{projectTitle(selectedProject)}</Typography.Title>
            <Typography.Text type="secondary">
              {selectedProject
                ? `${selectedProject.city || '-'} · ${selectedProject.address || '-'} · ${selectedProject.radius_meters || 1000} 米 · ${selectedProject.business_type || '电竞馆'} · ID ${shortProjectId(selectedProject.project_id)}`
                : '选择项目后开始分析'}
            </Typography.Text>
          </Space>
        </Card>

        <Card
          title="选址流程"
          className="v11-action-card"
          extra={<Tag color={activeWorkflowStep?.status === 'finish' ? 'green' : 'blue'}>{activeWorkflowStep?.title}</Tag>}
        >
          <Alert
            type="info"
            showIcon
            message="按步骤完成选址分析"
            description="系统会先采集和整理数据，再做 AI 数据核验、人工补充、评分分析和 AI 报告。数据核验会明确标记已有数据、缺失数据和建议补充项。"
            style={{marginBottom: 12}}
          />
          <Steps
            size="small"
            current={currentWorkflowIndex}
            items={workflowSteps.map(item => ({
              title: item.title,
              description: item.description,
              status: item.status,
            }))}
          />

          <Divider />

          <div className="v11-step-grid">
            <Card size="small" title="Step 1：新建或选择项目">
              <Space direction="vertical" size={8} style={{width: '100%'}}>
                <Alert
                  type={selectedProject ? 'success' : 'info'}
                  showIcon
                  message={selectedProject ? `当前项目：${projectTitle(selectedProject)}` : '请先选择或创建项目'}
                  description={selectedProject ? `${selectedProject.city || '-'} · ${selectedProject.address || '-'} · ${selectedProject.radius_meters || 1000} 米` : '左侧创建项目后会自动选中。'}
                />
                {inlineResult('create')}
              </Space>
            </Card>

            <Card size="small" title="Step 2：确认地址和范围">
              <Space direction="vertical" size={8} style={{width: '100%'}}>
                <Space size={[4, 4]} wrap>
                  <Tag>{selectedProject?.city || '城市未填'}</Tag>
                  <Tag>{selectedProject?.radius_meters || 1000} 米</Tag>
                  <Tag color={hasProjectLocation(selectedProject) ? 'green' : 'orange'}>
                    {hasProjectLocation(selectedProject) ? '已有经纬度' : '待地址解析'}
                  </Tag>
                </Space>
                <Typography.Text type="secondary">{selectedProject?.address || '创建项目时填写详细地址。'}</Typography.Text>
              </Space>
            </Card>

            <Card size="small" title="Step 3：采集基础数据">
                <Space direction="vertical" size={8} style={{width: '100%'}}>
                  <Space size={[4, 4]} wrap>
                    <Tag color={projectPoiCount > 0 ? 'green' : 'default'}>POI {projectPoiCount}</Tag>
                    <Tag color={projectCompetitorCount > 0 ? 'orange' : 'default'}>竞品 {projectCompetitorCount}</Tag>
                    <Tag color={projectFoodCount > 0 ? 'cyan' : 'default'}>餐饮 {projectFoodCount}</Tag>
                    <Tag color={projectEntertainmentCount > 0 ? 'blue' : 'default'}>娱乐 {projectEntertainmentCount}</Tag>
                  </Space>
                  <Button
                    icon={<CloudDownloadOutlined />}
                    loading={actionLoading === 'amap'}
                    onClick={() => runAction('amap', '高德 POI 采集', () => collectProjectAmap(selectedProjectId))}
                    block
                  >
                    采集高德 POI
                  </Button>
                  <Button
                    loading={actionLoading === 'competitor'}
                    onClick={() => runAction('competitor', '竞品采集', () => collectProjectCompetitors(selectedProjectId))}
                    block
                  >
                    获取竞品
                  </Button>
                  <Button
                    loading={actionLoading === 'supporting'}
                    onClick={() => runAction('supporting', '周边配套采集', () => collectProjectSupporting(selectedProjectId))}
                    block
                  >
                    获取配套
                  </Button>
                  {inlineResult('amap')}
                  {inlineResult('competitor')}
                  {inlineResult('supporting')}
                </Space>
            </Card>

            <Card size="small" title="Step 4：人工确认和补充">
                <Space direction="vertical" size={8} style={{width: '100%'}}>
                  <Alert
                    type="info"
                    showIcon
                    message="基于已采集数据补充"
                    description="人工补充页会优先带出已采集的竞品名称、距离等基础信息，再填写价格、配置、上座率、租金和夜间营业情况。"
                  />
                  <Button disabled={!selectedProjectId} onClick={() => navigate(`/projects/${selectedProjectId}/supplement?focus=general`)} block>
                    进入人工补充
                  </Button>
                  <Typography.Text type="secondary">
                    人工审核重点：竞品是否真实、价格/配置/上座率、真实租金、夜间营业情况。
                  </Typography.Text>
                </Space>
            </Card>

            <Card size="small" title="Step 5：AI 数据核验">
                <Space direction="vertical" size={8} style={{width: '100%'}}>
                  <Alert
                    type={quality ? (qualityScore >= 80 ? 'success' : 'warning') : 'info'}
                    showIcon
                    message={quality ? `数据完整度 ${qualityScore}%` : '尚未核验数据'}
                    description={quality
                      ? Array.isArray(quality.missing) && quality.missing.length > 0
                        ? `需要补充：${quality.missing.join('、')}`
                        : '关键数据暂未发现明显缺失。'
                      : `当前已有租金 ${projectRentCount} 条。建议先补充竞品经营、租金、夜间营业等人工数据。`}
                  />
                  <Button loading={actionLoading === 'quality' || actionLoading === 'ai-review'} onClick={checkQuality} block>
                    AI 数据核验
                  </Button>
                  {inlineResult('quality')}
                  {inlineResult('aiReview')}
                </Space>
            </Card>

            <Card size="small" title="Step 6：评分分析">
                <Space direction="vertical" size={8} style={{width: '100%'}}>
                  <Button type="primary" loading={actionLoading === 'score'} onClick={runScore} block>
                    开始评分分析
                  </Button>
                  <Alert
                    type={score ? 'success' : 'info'}
                    showIcon
                    message={score ? `评分 ${countText(score.total_score)}，${score.level || '未评级'}` : '评分后再生成报告更准确'}
                    description="评分会输出综合分、维度分、风险项和数据置信度。"
                  />
                  {inlineResult('score')}
                </Space>
            </Card>

            <Card size="small" title="Step 7：生成报告和继续咨询">
              <Space direction="vertical" size={8} style={{width: '100%'}}>
                <Button icon={<FileTextOutlined />} loading={actionLoading === 'report'} onClick={runReport} block>
                  生成 AI 报告
                </Button>
                <Alert
                  type={reportContent ? 'success' : 'info'}
                  showIcon
                  message={reportContent ? '报告已生成' : 'AI 报告会基于项目数据、评分结果和已确认记忆生成。'}
                  description={reportContent ? '可在下方结果区导出 HTML 或打印为 PDF。' : '建议先完成数据核验和评分后再生成正式报告。'}
                />
                {inlineResult('report')}
              </Space>
            </Card>
          </div>
        </Card>

        <Card title={<Space><RobotOutlined />聊天式工作区</Space>} className="v11-chat-card">
          <div className="v11-message-list">
            {messages.map((item, index) => (
              <div key={`${item.role}-${index}`} className={`v11-message ${item.role}`}>
                <Tag color={item.role === 'user' ? 'blue' : item.role === 'assistant' ? 'green' : 'default'}>
                  {item.role === 'user' ? '你' : item.role === 'assistant' ? 'AI助手' : '系统'}
                </Tag>
                <Typography.Paragraph style={{whiteSpace: 'pre-wrap', margin: '6px 0 0'}}>{item.content}</Typography.Paragraph>
              </div>
            ))}
          </div>
          <Space wrap style={{marginBottom: 10}}>
            {QUICK_MESSAGES.map(item => <Button key={item} size="small" onClick={() => setChatInput(item)}>{item}</Button>)}
          </Space>
          <Space.Compact style={{width: '100%'}}>
            <Input.TextArea
              value={chatInput}
              placeholder="输入地址、选址问题或报告要求，例如：为什么这个位置竞品风险高？"
              autoSize={{minRows: 2, maxRows: 5}}
              onChange={event => setChatInput(event.target.value)}
              onPressEnter={event => {
                if (!event.shiftKey) {
                  event.preventDefault();
                  void sendMessage();
                }
              }}
            />
            <Button type="primary" icon={<SendOutlined />} loading={actionLoading === 'chat'} onClick={sendMessage}>发送</Button>
          </Space.Compact>
        </Card>

        {(quality || aiReview || score || reportContent) && (
          <Card title="分析结果与报告" className="v11-result-card">
            <Row gutter={[12, 12]}>
              {quality && (
                <Col xs={24} md={8}>
                  <Card size="small">
                    <Statistic title="数据完整度" value={qualityScore} suffix="%" />
                    <Progress percent={qualityScore} status={qualityScore >= 80 ? 'success' : 'active'} />
                    <Typography.Text type="secondary">缺失：{Array.isArray(quality.missing) ? quality.missing.length : 0} 项</Typography.Text>
                    {Array.isArray(quality.missing) && quality.missing.length > 0 && (
                      <List
                        size="small"
                        dataSource={quality.missing}
                        renderItem={(item: string) => <List.Item>{item}</List.Item>}
                      />
                    )}
                    {Array.isArray(quality.warnings) && quality.warnings.length > 0 && (
                      <Alert style={{marginTop: 8}} type="warning" showIcon message={`风险提示：${quality.warnings.length} 项`} />
                    )}
                  </Card>
                </Col>
              )}
              {aiReview && (
                <Col xs={24} md={8}>
                  <Card size="small">
                    <Statistic title="AI 数据核验" value={aiReview.success === false ? '未完成' : '已完成'} />
                    <Alert
                      type={aiReview.success === false ? 'warning' : 'success'}
                      showIcon
                      message={aiReview.success === false ? 'AI 审核暂不可用' : '已生成补充建议'}
                      description={aiReview.message || '请查看下方 AI 数据核验结论。'}
                    />
                  </Card>
                </Col>
              )}
              {score && (
                <Col xs={24} md={8}>
                  <Card size="small">
                    <Statistic title="综合评分" value={score.total_score ?? '--'} suffix="分" />
                    <Typography.Text>等级：{score.level || '-'}</Typography.Text>
                    {scoreDimensions.length > 0 && (
                      <List
                        size="small"
                        dataSource={scoreDimensions.slice(0, 5)}
                        renderItem={([key, value]) => (
                          <List.Item>
                            <Typography.Text>{value?.label || value?.name || key}：{value?.score ?? '--'} / {value?.max ?? '--'}</Typography.Text>
                          </List.Item>
                        )}
                      />
                    )}
                  </Card>
                </Col>
              )}
              {reportContent && (
                <Col xs={24} md={8}>
                  <Card size="small">
                    <Statistic title="报告状态" value="已生成" />
                    <Space wrap>
                      <Button size="small" onClick={() => downloadHtml(`${projectTitle(selectedProject)}-选址报告.html`, reportContent)}>导出 HTML</Button>
                      <Button size="small" onClick={() => window.print()}>打印 / PDF</Button>
                    </Space>
                  </Card>
                </Col>
              )}
            </Row>
            {quality && supplementSuggestions.length > 0 && (
              <>
                <Divider />
                <Typography.Title level={4}>人工补充建议</Typography.Title>
                <Alert
                  type="warning"
                  showIcon
                  style={{marginBottom: 12}}
                  message="请先补齐关键数据，再生成正式投资报告"
                  description="AI 数据核验负责指出缺口，最终仍需要人工确认和补充。补充页面会按竞品、租金、人口、配套分类填写。"
                />
                <Row gutter={[12, 12]}>
                  {supplementSuggestions.map(item => (
                    <Col xs={24} md={12} key={item.category}>
                      <Card
                        size="small"
                        title={<Space><span>{item.category}</span><Tag color={item.priority === '高' ? 'red' : item.priority === '中' ? 'orange' : 'blue'}>{item.priority}优先级</Tag></Space>}
                        extra={selectedProjectId ? (
                          <Button size="small" type="primary" onClick={() => navigate(`/projects/${selectedProjectId}/supplement?focus=${item.focus}`)}>
                            去补充
                          </Button>
                        ) : null}
                      >
                        <Typography.Paragraph type="secondary">{item.reason}</Typography.Paragraph>
                        <Space size={[6, 6]} wrap>
                          {item.fields.map(field => <Tag key={field}>{field}</Tag>)}
                        </Space>
                      </Card>
                    </Col>
                  ))}
                </Row>
              </>
            )}
            {aiReview?.content && (
              <>
                <Divider />
                <Typography.Title level={4}>AI 数据核验结论</Typography.Title>
                <MarkdownReport content={String(aiReview.content)} />
              </>
            )}
            {reportContent && (
              <>
                <Divider />
                <MarkdownReport content={reportContent} />
              </>
            )}
          </Card>
        )}
      </main>

      <aside className="v11-right-panel">
        <Card title="当前项目状态">
          {selectedProject ? (
            <Space direction="vertical" size={8}>
              <Typography.Text>{statusText(selectedProject.status)}</Typography.Text>
              <Space size={[4, 4]} wrap>
                <Tag color={numberFromStats(selectedProject, 'poi_count') > 0 ? 'green' : 'default'}>POI {numberFromStats(selectedProject, 'poi_count')}</Tag>
                <Tag color={numberFromStats(selectedProject, 'competitor_count') > 0 ? 'orange' : 'default'}>竞品 {numberFromStats(selectedProject, 'competitor_count')}</Tag>
                <Tag color={numberFromStats(selectedProject, 'food_count') > 0 ? 'cyan' : 'default'}>餐饮 {numberFromStats(selectedProject, 'food_count')}</Tag>
                <Tag color={numberFromStats(selectedProject, 'entertainment_count') > 0 ? 'blue' : 'default'}>娱乐 {numberFromStats(selectedProject, 'entertainment_count')}</Tag>
                <Tag color={numberFromStats(selectedProject, 'rent_count') > 0 ? 'purple' : 'default'}>租金 {numberFromStats(selectedProject, 'rent_count')}</Tag>
              </Space>
              {Array.isArray(selectedProject.stats?.missing_fields) && selectedProject.stats.missing_fields.length > 0 && (
                <Alert
                  type="warning"
                  showIcon
                  message="仍需补充"
                  description={(selectedProject.stats.missing_fields as string[]).join('、')}
                />
              )}
            </Space>
          ) : (
            <Alert type="info" showIcon message="请先选择或创建项目" />
          )}
        </Card>

        <Card title="选址维度">
          <List
            size="small"
            dataSource={dimensions.filter(item => item.enabled)}
            locale={{emptyText: '暂无维度配置'}}
            renderItem={item => (
              <List.Item>
                <List.Item.Meta title={<Space><span>{item.name}</span><Tag>{item.weight}</Tag></Space>} description={item.description} />
              </List.Item>
            )}
          />
        </Card>

        <Card title="数据源">
          <List
            size="small"
            dataSource={dataSources}
            locale={{emptyText: '暂无数据源状态'}}
            renderItem={item => (
              <List.Item>
                <Space direction="vertical" size={2}>
                  <Space>
                    <Typography.Text strong>{item.display_name}</Typography.Text>
                    <Tag color={item.status === 'available' ? 'green' : item.status === 'disabled' ? 'default' : 'orange'}>
                      {item.status === 'available' ? '可用' : item.status === 'disabled' ? '停用' : '未配置'}
                    </Tag>
                  </Space>
                  <Typography.Text type="secondary">{item.capabilities?.join('、') || item.description}</Typography.Text>
                </Space>
              </List.Item>
            )}
          />
        </Card>

        <Card title="已确认记忆">
          {memories.length === 0 ? (
            <Alert type="info" showIcon message="当前项目暂无已确认记忆" />
          ) : (
            <List
              size="small"
              dataSource={memories.slice(0, 8)}
              renderItem={item => (
                <List.Item>
                  <List.Item.Meta title={item.title} description={`${item.memory_type} · ${(item.tags || []).join('、')}`} />
                </List.Item>
              )}
            />
          )}
        </Card>
      </aside>
    </div>
  );
}
