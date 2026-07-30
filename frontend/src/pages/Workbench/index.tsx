import {lazy, Suspense, useEffect, useMemo, useRef, useState} from 'react';
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
  Modal,
  Popconfirm,
  Progress,
  Row,
  Select,
  Space,
  Statistic,
  Tag,
  Typography,
  message,
} from 'antd';
import {
  CheckCircleOutlined,
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
  collectProjectGovernmentStats,
  collectProjectSupporting,
  createProject,
  createCrawlerManualUrlTask,
  deleteProject,
  enrichProjectCrawler,
  generateDemoData,
  generateProjectAiReview,
  getProjectDataQuality,
  getProjectCityInsight,
  listProjectCrawlTasks,
  listProjects,
  type ProjectCreatePayload,
  type CityInsight,
} from '../../api/projects';
import {scoreProject} from '../../api/score';
import {generateAiReport} from '../../api/report';
import {createProjectChatSession, sendProjectChatMessage} from '../../api/chat';
import {getDataSourceStatus, type DataSourceStatus} from '../../api/dataSources';
import {getScoringConfig, type ScoringDimensionConfig} from '../../api/scoringConfig';
import {listMemory, type MemoryItem} from '../../api/memory';
import {getManagedSystemConfig} from '../../api/client';
import MarkdownReport from '../../components/MarkdownReport';
import {useNavigate, useSearchParams} from 'react-router-dom';

const CityInsightPanel = lazy(() => import('../../components/CityInsightPanel'));

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

type CrawlTaskItem = {
  id: number;
  task_type: string;
  target_name?: string | null;
  target_address?: string | null;
  target_url?: string | null;
  status: string;
  error_message?: string | null;
};

const QUICK_MESSAGES = [
  '西安市小寨地铁站 1000 米，电竞馆，帮我做一次选址分析',
  '这个项目当前缺哪些关键数据？',
  '竞品压力和夜间消费环境怎么样？',
  '生成一份适合投资人看的报告',
];

const CRAWLER_SOURCE_LABELS: Record<string, string> = {
  competitor: '竞品',
  supporting: '配套',
  rent: '租金',
};

const CRAWLER_TASK_STATUS_LABELS: Record<string, string> = {
  pending: '待执行',
  running: '执行中',
  success: '已补充',
  partial: '部分补充',
  skipped: '未找到来源',
  failed: '失败',
};

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

function formatReportDate(value?: string | null) {
  if (!value) return new Date().toLocaleString('zh-CN');
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? String(value) : date.toLocaleString('zh-CN');
}

function providerStatusText(status: string) {
  if (status === 'available') return '可用';
  if (status === 'disabled') return '未启用';
  if (status === 'not_configured') return '未配置';
  return status;
}

function projectSearchText(project?: ProjectItem | null) {
  return [project?.city, project?.district, project?.address].filter(Boolean).join(' ');
}

function crawlSourcePresets(project: ProjectItem | null, taskType: string) {
  const location = projectSearchText(project) || '西安市 小寨地铁站';
  const encoded = (text: string) => encodeURIComponent(text);
  if (taskType === 'rent') {
    return [
      {label: '58同城商铺出租', url: 'https://xa.58.com/shangpucz/', name: `${location} 商铺出租`},
      {label: '安居客商铺出租', url: 'https://xian.anjuke.com/sp-zu/', name: `${location} 商铺出租`},
      {label: '房天下商铺出租', url: 'https://xian.shop.fang.com/zu/', name: `${location} 商铺出租`},
      {label: '公开搜索租金线索', url: `https://www.bing.com/search?q=${encoded(`${location} 商铺出租 月租 面积 转让费`)}`, name: `${location} 租金线索`},
    ];
  }
  if (taskType === 'supporting') {
    return [
      {label: '大众点评商户搜索', url: 'https://www.dianping.com/search/keyword/', name: `${location} 周边配套`},
      {label: '美团商户搜索', url: 'https://www.meituan.com/', name: `${location} 周边配套`},
      {label: '公开搜索营业时间', url: `https://www.bing.com/search?q=${encoded(`${location} 餐饮 娱乐 营业时间 评分`)}`, name: `${location} 配套线索`},
    ];
  }
  return [
    {label: '大众点评竞品搜索', url: 'https://www.dianping.com/search/keyword/', name: `${location} 电竞馆`},
    {label: '美团竞品搜索', url: 'https://www.meituan.com/', name: `${location} 电竞馆`},
    {label: '公开搜索竞品价格', url: `https://www.bing.com/search?q=${encoded(`${location} 电竞馆 网咖 价格 营业时间 机器配置`)}`, name: `${location} 电竞馆竞品`},
  ];
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

function doneTag(done: boolean, doing = false) {
  if (doing) return <Tag color="processing">进行中</Tag>;
  return done ? <Tag color="green" icon={<CheckCircleOutlined />}>已完成</Tag> : <Tag color="default">待处理</Tag>;
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

function projectProgress(project: ProjectItem) {
  const poiCount = numberFromStats(project, 'poi_count');
  const competitorCount = numberFromStats(project, 'competitor_count');
  const foodCount = numberFromStats(project, 'food_count');
  const entertainmentCount = numberFromStats(project, 'entertainment_count');
  const rentCount = numberFromStats(project, 'rent_count');
  const completed = [
    poiCount > 0,
    competitorCount > 0,
    foodCount > 0 || entertainmentCount > 0,
    rentCount > 0,
  ].filter(Boolean).length;
  if (completed === 0) return {completed, total: 4, text: '待采集', color: 'default'};
  if (completed >= 4) return {completed, total: 4, text: '基础数据已采集', color: 'green'};
  if (completed >= 3 && rentCount === 0) return {completed, total: 4, text: '缺租金', color: 'orange'};
  return {completed, total: 4, text: `进度 ${completed}/4`, color: completed >= 2 ? 'blue' : 'orange'};
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
  crawlerDone = false,
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
      title: '搜索并补充公开数据',
      description: crawlerDone
        ? '系统已尝试搜索并抓取公开网页中的竞品、配套或租金线索，结果需要人工确认。'
        : '基于名称、地址和项目位置，搜索允许访问的公开页面补充经营、配套和租金线索。',
      status: crawlerDone ? 'finish' : hasBaseData ? 'process' : 'wait',
    },
    {
      title: '人工确认和补充',
      description: hasSupplementData
        ? '已有部分竞品或租金数据，建议继续确认有效性并补充经营信息。'
        : '确认疑似竞品、配套是否真实有效，并补充租金、价格、配置、上座率等人工数据。',
      status: hasSupplementData ? 'finish' : crawlerDone ? 'process' : 'wait',
    },
    {
      title: '数据核验',
      description: quality
        ? `当前完整度 ${qualityScore}%，缺失 ${Array.isArray(quality.missing) ? quality.missing.length : 0} 项。`
        : '点击 AI 数据核验，系统会先检查已有数据和缺失数据，再给出 AI 初审结论和补充建议。',
      status: quality ? 'finish' : hasSupplementData ? 'process' : 'wait',
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

  if (Array.isArray(result?.task_ids) && result.task_ids.length > 0) {
    return [
      `${action}任务已创建。`,
      `任务数：${countText(result.task_count)}`,
      `任务ID：${result.task_ids.join('、')}`,
      '系统将在后台搜索公开网页并抓取线索。请查看本步骤下方任务中心，结果默认待人工确认。',
    ].join('\n');
  }

  if (action === '高德 POI 采集') {
    const collected = result?.collected || {};
    const diagnostics = result?.diagnostics || {};
    return [
      '高德 POI 采集完成。',
      `本次去重后 POI：${countText(collected.poi_count)}`,
      `竞品关键词命中（待专门筛选）：${countText(collected.competitor_count)}`,
      `餐饮：${countText(collected.food_count)}`,
      `娱乐：${countText(collected.entertainment_count)}`,
      Number(diagnostics.duplicate_count || 0) > 0
        ? `已合并重复 POI：${countText(diagnostics.duplicate_count)} 条`
        : '未发现重复 POI。',
      '下一步建议：点击“获取竞品”和“获取配套”进行专门分类；后续列表数量以专门筛选和去重后的结果为准。',
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

  if (action.startsWith('爬虫补充') || action.startsWith('搜索并补充')) {
    const saved = result?.saved || {};
    return [
      `${action}完成。`,
      `搜索到候选网页：${countText(result?.discovered_url_count)}`,
      `成功抓取：${countText(result?.completed_count)}`,
      `抽取到有效字段：${countText((saved.competitors || 0) + (saved.supporting || 0) + (saved.rent || 0))}`,
      `待人工确认：${countText((saved.competitors || 0) + (saved.supporting || 0) + (saved.rent || 0))}`,
      `失败：${countText(result?.failed_count)}`,
      `跳过：${countText(result?.skipped_count)}`,
      `补充竞品：${countText(saved.competitors)}`,
      `补充配套：${countText(saved.supporting)}`,
      `补充租金：${countText(saved.rent)}`,
      '下一步建议：进入 Step 5 人工确认，确认公开网页线索是否可信。',
    ].join('\n');
  }

  if (action === '演示数据生成') {
    const generated = result?.generated || {};
    const updated = result?.updated || {};
    return [
      '演示模拟数据已生成。',
      `补全竞品：${countText(updated.competitors)} 条，新增竞品样本：${countText(generated.competitors)} 条`,
      `补全配套：${countText(updated.supporting)} 条，新增配套样本：${countText(generated.supporting)} 条`,
      `新增租金样本：${countText(generated.rent)} 条`,
      '注意：这些数据仅用于演示流程，正式测试前仍需人工核实。下一步建议：执行 AI 数据核验和评分分析。',
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

function escapeHtml(value: string) {
  return value
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
}

function downloadReportHtml(filename: string, reportElement: HTMLElement) {
  const cloned = reportElement.cloneNode(true) as HTMLElement;
  cloned.querySelectorAll('[data-export-hidden="true"]').forEach(node => node.remove());
  const title = filename.replace(/\.html$/i, '');
  const html = `<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>${escapeHtml(title)}</title>
  <style>
    *{box-sizing:border-box}
    body{margin:0;background:#eef2f7;color:#263548;font-family:-apple-system,BlinkMacSystemFont,"Microsoft YaHei",Arial,sans-serif;line-height:1.8}
    .v11-report-print-root{max-width:980px;margin:32px auto;background:#fff;padding:44px 52px;box-shadow:0 14px 42px rgba(15,23,42,.10)}
    .v11-report-cover{padding-bottom:28px;margin-bottom:30px;border-bottom:3px solid #245b91}
    .v11-report-kicker{color:#245b91;font-size:13px;font-weight:700;letter-spacing:.16em}
    .v11-report-cover h1{font-size:32px;line-height:1.3;color:#102033;margin:10px 0}
    .v11-report-meta{color:#64748b;font-size:14px}
    .v11-report-badges{display:flex;flex-wrap:wrap;gap:8px;margin-top:18px}
    .v11-report-badge{display:inline-block;padding:4px 10px;border-radius:999px;background:#eaf4ff;color:#1d4f7a;font-size:13px}
    .v11-report-badge.warning{background:#fff4e5;color:#9a5b00}
    .v11-report-summary{display:grid;grid-template-columns:repeat(3,1fr);gap:12px;margin:22px 0 8px}
    .v11-report-summary-item{border:1px solid #dfe7ef;border-radius:10px;padding:14px;background:#f8fafc}
    .v11-report-summary-label{display:block;color:#64748b;font-size:12px;margin-bottom:4px}
    .v11-report-summary-value{display:block;color:#102033;font-size:20px;font-weight:700}
    .v11-report-summary-value.small{font-size:15px;line-height:1.5}
    .markdown-report{max-width:none;color:#263548}
    .v11-report-print-root .markdown-report>h1:first-of-type{display:none}
    .markdown-report h1{font-size:28px;color:#102033;margin:0 0 24px}
    .markdown-report h2{font-size:21px;color:#153b62;margin:32px 0 12px;padding-bottom:8px;border-bottom:1px solid #d9e4ef}
    .markdown-report h3{font-size:17px;color:#203c57;margin:24px 0 10px}
    .markdown-report h4,.markdown-report h5{color:#263548;margin:20px 0 8px}
    .markdown-report p{margin:8px 0 14px}
    .markdown-report ul,.markdown-report ol{padding-left:24px;margin:8px 0 16px}
    .markdown-report li{margin:5px 0}
    .markdown-report a{color:#1769aa;text-decoration:none}
    .markdown-report blockquote{margin:16px 0;padding:12px 16px;border-left:4px solid #4a86bd;background:#f5f9fd;color:#40566d}
    .markdown-report code{padding:2px 5px;border-radius:4px;background:#f1f5f9}
    .markdown-report hr{border:0;border-top:1px solid #d9e2ec;margin:24px 0}
    .markdown-table-wrap{overflow-x:auto;margin:14px 0 22px}
    .markdown-report table{width:100%;border-collapse:collapse;font-size:13px}
    .markdown-report th,.markdown-report td{border:1px solid #dce4ec;padding:9px 10px;text-align:left;vertical-align:top}
    .markdown-report th{background:#edf4fa;color:#173a5e;font-weight:700}
    .markdown-report tr:nth-child(even) td{background:#fafcfe}
    .markdown-report-toc{padding:18px 22px;margin:0 0 28px;border:1px solid #d9e6f2;border-radius:10px;background:#f7fbff}
    .markdown-report-toc ol{columns:2;column-gap:36px;margin:10px 0 0}
    .markdown-report-toc li{break-inside:avoid}
    .markdown-report-toc .subsection{margin-left:14px}
    .v11-report-footer{margin-top:36px;padding-top:18px;border-top:1px solid #d9e2ec;color:#64748b;font-size:12px}
    @page{size:A4;margin:14mm}
    @media print{
      body{background:#fff}
      .v11-report-print-root{max-width:none;margin:0;padding:0;box-shadow:none}
      .markdown-report h2,.markdown-report h3{break-after:avoid;page-break-after:avoid}
      .markdown-report table,.markdown-report blockquote,.v11-report-summary-item{break-inside:avoid;page-break-inside:avoid}
    }
    @media(max-width:700px){
      .v11-report-print-root{margin:0;padding:24px 18px;box-shadow:none}
      .v11-report-summary{grid-template-columns:1fr}
      .markdown-report-toc ol{columns:1}
    }
  </style>
</head>
<body>${cloned.outerHTML}</body>
</html>`;
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
  const [searchParams] = useSearchParams();
  const reportPrintRef = useRef<HTMLDivElement | null>(null);
  const [projectForm] = Form.useForm<ProjectCreatePayload>();
  const [manualUrlForm] = Form.useForm();
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
  const [cityInsight, setCityInsight] = useState<CityInsight | null>(null);
  const [dataSources, setDataSources] = useState<DataSourceStatus[]>([]);
  const [dimensions, setDimensions] = useState<ScoringDimensionConfig[]>([]);
  const [memories, setMemories] = useState<MemoryItem[]>([]);
  const [sideContextLoading, setSideContextLoading] = useState(false);
  const [crawlTasks, setCrawlTasks] = useState<CrawlTaskItem[]>([]);
  const [crawlTasksLoading, setCrawlTasksLoading] = useState(false);
  const [crawlerSearchEnabled, setCrawlerSearchEnabled] = useState(true);
  const [manualUrlOpen, setManualUrlOpen] = useState(false);
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
    setSideContextLoading(true);
    try {
      const [sourceResult, scoringResult, memoryResult, managedConfig] = await Promise.all([
        getDataSourceStatus().catch(() => ({items: []})),
        getScoringConfig().catch(() => ({dimensions: [], total_weight: 0, normalized: false})),
        projectId
          ? listMemory({project_id: projectId, status: 'confirmed'}).catch(() => ({items: [], total: 0}))
          : Promise.resolve({items: [], total: 0}),
        getManagedSystemConfig().catch(() => ({crawler_search_enabled: false})),
      ]);
      setDataSources(sourceResult.items || []);
      setDimensions(scoringResult.dimensions || []);
      setMemories(memoryResult.items || []);
      setCrawlerSearchEnabled(Boolean(managedConfig?.crawler_search_enabled));
    } catch {
      // 右侧上下文失败不阻断工作台主流程。
    } finally {
      setSideContextLoading(false);
    }
  };

  const loadCrawlTasks = async (projectId = selectedProjectId, silent = false) => {
    if (!projectId) {
      setCrawlTasks([]);
      return;
    }
    if (!silent) setCrawlTasksLoading(true);
    try {
      const result = await listProjectCrawlTasks(projectId);
      setCrawlTasks(Array.isArray(result?.items) ? result.items : []);
    } catch {
      if (!silent) message.warning('爬虫任务状态暂时不可用');
    } finally {
      if (!silent) setCrawlTasksLoading(false);
    }
  };

  const loadCityInsight = async (projectId = selectedProjectId, silent = false) => {
    if (!projectId) {
      setCityInsight(null);
      return;
    }
    try {
      setCityInsight(await getProjectCityInsight(projectId));
    } catch {
      setCityInsight(null);
      if (!silent) message.warning('城市公开数据暂时不可用，不影响其他选址流程');
    }
  };

  useEffect(() => {
    void loadProjects(searchParams.get('projectId') || undefined);
    void loadSideContext();
  }, []);

  useEffect(() => {
    if (!selectedProjectId) return;
    setQuality(null);
    setAiReview(null);
    setScore(null);
    setReport(null);
    setCityInsight(null);
    setSessionId('');
    setActionResults({});
    void loadSideContext(selectedProjectId);
    void loadCrawlTasks(selectedProjectId, true);
    void loadCityInsight(selectedProjectId, true);
    createProjectChatSession(selectedProjectId)
      .then(result => setSessionId(String(result.session_id)))
      .catch(() => setSessionId(''));
  }, [selectedProjectId]);

  useEffect(() => {
    if (!selectedProjectId || cityInsight?.status !== 'collecting') return;
    const timer = window.setInterval(() => {
      void loadCityInsight(selectedProjectId, true);
    }, 3000);
    return () => window.clearInterval(timer);
  }, [selectedProjectId, cityInsight?.status]);

  useEffect(() => {
    if (!selectedProjectId) return;
    const hasActiveTask = crawlTasks.some(task => task.status === 'pending' || task.status === 'running');
    if (!hasActiveTask) return;
    const timer = window.setInterval(() => {
      void loadCrawlTasks(selectedProjectId, true);
    }, 3000);
    return () => window.clearInterval(timer);
  }, [selectedProjectId, crawlTasks]);

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

  const runCrawlerTask = async (loadingKey: string, actionName: string, types: Array<'competitor' | 'supporting' | 'rent'>) => {
    const result = await runAction(loadingKey, actionName, () => enrichProjectCrawler(selectedProjectId, types));
    if (result) {
      await loadCrawlTasks(selectedProjectId, true);
    }
  };

  const collectGovernmentStats = async () => {
    const result = await runAction(
      'governmentStats',
      '城市公开数据采集',
      () => collectProjectGovernmentStats(selectedProjectId),
    );
    if (result) {
      await loadCityInsight(selectedProjectId, true);
    }
  };

  const submitManualUrl = async () => {
    if (!selectedProjectId) {
      message.warning('请先选择或创建项目');
      return;
    }
    try {
      const values = await manualUrlForm.validateFields();
      const result = await runAction('crawlerManualUrl', '手动 URL 爬虫补充', () => createCrawlerManualUrlTask(selectedProjectId, values));
      if (result) {
        setManualUrlOpen(false);
        manualUrlForm.resetFields();
        await loadCrawlTasks(selectedProjectId, true);
      }
    } catch (error: any) {
      if (error?.errorFields) return;
      message.error(errorText(error, '手动 URL 任务创建失败'));
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

  const runDemoData = async () => {
    const result = await runAction('demoData', '演示数据生成', () => generateDemoData(selectedProjectId));
    if (!result) return;
    setQuality(null);
    setAiReview(null);
    setScore(null);
    setReport(null);
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

  const printReport = () => {
    if (!reportPrintRef.current) return;
    const previousTitle = document.title;
    document.title = `${projectTitle(selectedProject)}-电竞馆选址分析报告`;
    document.body.classList.add('report-printing');
    const cleanup = () => {
      document.body.classList.remove('report-printing');
      document.title = previousTitle;
      window.removeEventListener('afterprint', cleanup);
    };
    window.addEventListener('afterprint', cleanup);
    window.print();
    window.setTimeout(cleanup, 1000);
  };

  const qualityScore = Number(quality?.quality_score) || 0;
  const reportContent = String(report?.content || '');
  const hasSimulationData = Boolean(
    quality?.simulation_data_summary?.has_simulation_data
    || report?.simulation_data_summary?.has_simulation_data,
  );
  const reportCreatedAt = report?.created_at || report?.generated_at || new Date().toISOString();
  const scoreDimensions = score?.dimensions && typeof score.dimensions === 'object'
    ? Object.entries(score.dimensions as Record<string, any>)
    : [];
  const supplementSuggestions = buildSupplementSuggestions(quality);
  const crawlerQuality = quality?.crawler_quality || {};
  const crawlTaskStats = {
    total: crawlTasks.length,
    pending: crawlTasks.filter(task => task.status === 'pending').length,
    running: crawlTasks.filter(task => task.status === 'running').length,
    success: crawlTasks.filter(task => task.status === 'success' || task.status === 'partial').length,
    skipped: crawlTasks.filter(task => task.status === 'skipped').length,
    failed: crawlTasks.filter(task => task.status === 'failed').length,
  };
  const hasCrawlerAttempt = crawlTaskStats.total > 0 || Number(crawlerQuality.total_task_count || 0) > 0;
  const hasCrawlerResult = crawlTaskStats.success > 0 || Number(crawlerQuality.success_task_count || 0) > 0;
  const crawlerAttemptNeedsAttention = hasCrawlerAttempt
    && !hasCrawlerResult
    && crawlTaskStats.pending + crawlTaskStats.running === 0;
  const workflowSteps = buildWorkflowSteps(selectedProject, quality, score, reportContent, hasCrawlerResult);
  const firstIncompleteWorkflowIndex = workflowSteps.findIndex(item => item.status !== 'finish');
  const currentWorkflowIndex = firstIncompleteWorkflowIndex === -1
    ? Math.max(0, workflowSteps.length - 1)
    : firstIncompleteWorkflowIndex;
  const activeWorkflowStep = workflowSteps[currentWorkflowIndex] || workflowSteps[workflowSteps.length - 1];
  const completedWorkflowSteps = workflowSteps.filter(item => item.status === 'finish').length;
  const workflowAllCompleted = workflowSteps.length > 0 && completedWorkflowSteps === workflowSteps.length;
  const workflowProgressPercent = Math.round(completedWorkflowSteps / Math.max(1, workflowSteps.length) * 100);
  const projectPoiCount = selectedProject ? numberFromStats(selectedProject, 'poi_count') : 0;
  const projectCompetitorCount = selectedProject ? numberFromStats(selectedProject, 'competitor_count') : 0;
  const projectFoodCount = selectedProject ? numberFromStats(selectedProject, 'food_count') : 0;
  const projectEntertainmentCount = selectedProject ? numberFromStats(selectedProject, 'entertainment_count') : 0;
  const projectRentCount = selectedProject ? numberFromStats(selectedProject, 'rent_count') : 0;
  const cityCoverageStatus = cityInsight?.data_quality?.coverage_status
    || (cityInsight?.status === 'ready' ? 'target_ready' : 'unavailable');
  const cityCoverageScopeText = cityCoverageStatus === 'target_ready'
    ? (cityInsight?.data_quality?.target_scope_names || []).join('、')
    : (cityInsight?.data_quality?.fallback_scope_names || []).join('、');
  const hasAmapData = projectPoiCount > 0;
  const hasCompetitorData = projectCompetitorCount > 0;
  const hasSupportingData = projectFoodCount > 0 || projectEntertainmentCount > 0;
  const crawlerSources = dataSources.filter(source => source.name.startsWith('crawler_'));
  const visibleDataSources = crawlerSources.length > 0
    ? dataSources.filter(source => source.name !== 'crawler')
    : dataSources;
  const crawlerAvailable = crawlerSources.some(source => source.status === 'available');
  const crawlerSearchAvailable = crawlerAvailable && crawlerSearchEnabled;
  const crawlerDisabledReason = sideContextLoading && crawlerSources.length === 0
    ? '数据源状态加载中...'
    : crawlerSources.length
    ? crawlerSources.map(source => `${source.display_name}：${source.status === 'available' ? '可用' : providerStatusText(source.status)}`).join('；')
    : '爬虫数据源尚未注册';
  const hasQualityResult = Boolean(quality);
  const hasScoreResult = Boolean(score);
  const hasReportResult = Boolean(reportContent);
  const hasAnyProjectData = hasAmapData
    || projectCompetitorCount > 0
    || projectFoodCount > 0
    || projectEntertainmentCount > 0
    || projectRentCount > 0;
  const reportTrustLabel = hasSimulationData
    ? '仅限演示'
    : Number(crawlerQuality.pending_review_count || 0) > 0
      ? '存在待确认线索'
      : qualityScore >= 80
        ? '数据较完整'
        : '数据待补充';
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
              const progress = projectProgress(item);
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
                        <Tag color={progress.color}>{progress.text}</Tag>
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
          extra={<Tag color={workflowAllCompleted ? 'green' : 'blue'}>{workflowAllCompleted ? '流程已完成' : activeWorkflowStep?.title}</Tag>}
        >
          <Alert
            type={workflowAllCompleted ? 'success' : 'info'}
            showIcon
            message={workflowAllCompleted ? '选址分析流程已完成' : `当前阶段：${activeWorkflowStep?.title || '新建或选择项目'}`}
            description={workflowAllCompleted
              ? '评分和 AI 报告已生成，可在报告底部导出 HTML 或打印为 PDF；如需提高可信度，请继续补充缺失数据并重新核验。'
              : `下一步：${activeWorkflowStep?.description || '先在左侧新建项目，或选择已有项目。'}`}
            style={{marginBottom: 12}}
          />
          <div className="v11-workflow-progress" aria-label="选址流程完成进度">
            <Progress percent={workflowProgressPercent} showInfo={false} status={completedWorkflowSteps === workflowSteps.length ? 'success' : 'active'} />
            <Typography.Text strong>已完成 {completedWorkflowSteps}/{workflowSteps.length} 步</Typography.Text>
          </div>

          <div className="v11-step-grid">
            <Card size="small" className={selectedProject ? 'v11-step-card done' : 'v11-step-card active'} title="Step 1：新建或选择项目" extra={doneTag(Boolean(selectedProject))}>
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

            <Card size="small" className={hasProjectLocation(selectedProject) ? 'v11-step-card done' : 'v11-step-card'} title="Step 2：确认地址和范围" extra={doneTag(hasProjectLocation(selectedProject))}>
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

            <Card size="small" className={hasAmapData ? 'v11-step-card done' : selectedProject ? 'v11-step-card active' : 'v11-step-card'} title="Step 3：采集基础数据" extra={doneTag(hasAmapData, actionLoading === 'amap' || actionLoading === 'competitor' || actionLoading === 'supporting' || actionLoading === 'governmentStats')}>
                <Space direction="vertical" size={8} style={{width: '100%'}}>
                  <Space size={[4, 4]} wrap>
                    <Tag color={projectPoiCount > 0 ? 'green' : 'default'}>POI {projectPoiCount}</Tag>
                    <Tag color={projectCompetitorCount > 0 ? 'orange' : 'default'}>竞品 {projectCompetitorCount}</Tag>
                    <Tag color={projectFoodCount > 0 ? 'cyan' : 'default'}>餐饮 {projectFoodCount}</Tag>
                    <Tag color={projectEntertainmentCount > 0 ? 'blue' : 'default'}>娱乐 {projectEntertainmentCount}</Tag>
                  </Space>
                  <Button
                    icon={<CloudDownloadOutlined />}
                    type={hasAmapData ? 'default' : 'primary'}
                    loading={actionLoading === 'amap'}
                    onClick={() => runAction('amap', '高德 POI 采集', () => collectProjectAmap(selectedProjectId))}
                    block
                  >
                    {hasAmapData ? '高德 POI 已完成 / 重新采集' : '采集高德 POI'}
                  </Button>
                  <Button
                    type={hasCompetitorData ? 'default' : 'primary'}
                    icon={hasCompetitorData ? <CheckCircleOutlined /> : undefined}
                    loading={actionLoading === 'competitor'}
                    onClick={() => runAction('competitor', '竞品采集', () => collectProjectCompetitors(selectedProjectId))}
                    block
                  >
                    {hasCompetitorData ? '竞品已获取 / 重新获取' : '获取竞品'}
                  </Button>
                  <Button
                    type={hasSupportingData ? 'default' : 'primary'}
                    icon={hasSupportingData ? <CheckCircleOutlined /> : undefined}
                    loading={actionLoading === 'supporting'}
                    onClick={() => runAction('supporting', '周边配套采集', () => collectProjectSupporting(selectedProjectId))}
                    block
                  >
                    {hasSupportingData ? '配套已获取 / 重新获取' : '获取配套'}
                  </Button>
                  <Button
                    type={cityInsight?.status === 'ready' ? 'default' : 'primary'}
                    icon={cityInsight?.status === 'ready' ? <CheckCircleOutlined /> : <CloudDownloadOutlined />}
                    loading={actionLoading === 'governmentStats' || cityInsight?.status === 'collecting'}
                    disabled={!selectedProjectId}
                    onClick={collectGovernmentStats}
                    block
                  >
                    {cityInsight?.status === 'ready' ? '城市公开数据已获取 / 刷新' : '获取城市公开数据'}
                  </Button>
                  {cityInsight && (
                    <Alert
                      type={cityInsight.status === 'collecting' ? 'info' : cityCoverageStatus === 'target_ready' ? 'success' : 'warning'}
                      showIcon
                      message={cityInsight.status === 'ready' && cityCoverageStatus === 'target_ready'
                        ? `城市公开数据已就绪：${cityInsight.data_quality.confirmed_target_metric_count ?? cityInsight.data_quality.confirmed_metric_count} 项目标行政区指标`
                        : cityInsight.status === 'ready' && cityCoverageStatus === 'fallback_only'
                          ? `仅获取到${cityCoverageScopeText || '上级行政区'}宏观数据，目标城市/区县数据暂缺`
                        : cityInsight.status === 'collecting'
                          ? '政府公开数据正在后台同步'
                          : '尚无可用城市公开指标'}
                      description={`最新统计期：${cityInsight.data_quality.latest_target_period || cityInsight.data_quality.latest_period || '--'}；实际已加载口径：${cityCoverageScopeText || '--'}。宏观数据不代表项目分析半径内的真实人口和客流。`}
                    />
                  )}
                  {inlineResult('amap')}
                  {inlineResult('competitor')}
                  {inlineResult('supporting')}
                  {inlineResult('governmentStats')}
                </Space>
            </Card>

            <Card size="small" className={hasCrawlerResult ? 'v11-step-card done' : hasAmapData ? 'v11-step-card active' : 'v11-step-card'} title="Step 4：搜索并补充公开数据" extra={doneTag(hasCrawlerResult, actionLoading.startsWith('crawler'))}>
                <Space direction="vertical" size={8} style={{width: '100%'}}>
                  <Alert
                    type={crawlerSearchAvailable ? 'info' : 'warning'}
                    showIcon
                    message={crawlerSearchAvailable ? '按名称和地址搜索公开网页' : crawlerAvailable ? '自动搜索发现已关闭' : '爬虫服务尚未就绪'}
                    description={crawlerSearchAvailable
                      ? '系统会先校验目标名称、位置和业务类型，再抓取相关网页。结果默认待人工确认，不直接作为最终事实。'
                      : crawlerAvailable
                        ? '仍可使用下方“手动添加公开网页链接”；如需自动搜索，请在配置页启用搜索发现。'
                        : `请先安装并启用独立爬虫服务。${crawlerDisabledReason}`}
                  />
                  <Button
                    disabled={!selectedProjectId || !hasAmapData || !crawlerSearchAvailable}
                    loading={actionLoading === 'crawlerCompetitor'}
                    onClick={() => runCrawlerTask('crawlerCompetitor', '搜索并补充竞品信息', ['competitor'])}
                    block
                  >
                    搜索并补充竞品信息
                  </Button>
                  <Button
                    disabled={!selectedProjectId || !hasAmapData || !crawlerSearchAvailable}
                    loading={actionLoading === 'crawlerSupporting'}
                    onClick={() => runCrawlerTask('crawlerSupporting', '搜索并补充周边配套', ['supporting'])}
                    block
                  >
                    搜索并补充周边配套
                  </Button>
                  <Button
                    disabled={!selectedProjectId || !crawlerSearchAvailable}
                    loading={actionLoading === 'crawlerRent'}
                    onClick={() => runCrawlerTask('crawlerRent', '搜索并补充租金信息', ['rent'])}
                    block
                  >
                    搜索并补充租金信息
                  </Button>
                  <Button
                    disabled={!selectedProjectId || !crawlerAvailable}
                    loading={actionLoading === 'crawlerManualUrl'}
                    onClick={() => setManualUrlOpen(true)}
                    block
                  >
                    手动添加公开网页链接
                  </Button>
                  {crawlTaskStats.total > 0 && (
                    <Card size="small" title="爬虫任务中心" extra={<Button size="small" loading={crawlTasksLoading} onClick={() => loadCrawlTasks()}>刷新</Button>}>
                      <Space direction="vertical" size={8} style={{width: '100%'}}>
                        <Space size={[4, 4]} wrap>
                          <Tag>总任务 {crawlTaskStats.total}</Tag>
                          <Tag color={crawlTaskStats.pending + crawlTaskStats.running > 0 ? 'processing' : 'default'}>执行中 {crawlTaskStats.pending + crawlTaskStats.running}</Tag>
                          <Tag color="green">成功 {crawlTaskStats.success}</Tag>
                          <Tag color="orange">跳过 {crawlTaskStats.skipped}</Tag>
                          <Tag color="red">失败 {crawlTaskStats.failed}</Tag>
                        </Space>
                        {crawlTaskStats.skipped > 0 && (
                          <Alert
                            type="warning"
                            showIcon
                            message="部分任务未搜索到可访问的公开网页"
                            description="建议人工补充，或在本步骤手动提供公开来源链接后重新抓取。"
                          />
                        )}
                        {crawlerAttemptNeedsAttention && (
                          <Alert
                            type="warning"
                            showIcon
                            message="本次爬虫补充尚未取得有效结果"
                            description="Step 4 不会标记为已完成。请启用搜索发现、检查来源网站，或手动添加公开网页链接后重试。"
                          />
                        )}
                        <List
                          size="small"
                          dataSource={crawlTasks.slice(0, 5)}
                          renderItem={task => (
                            <List.Item>
                              <Space direction="vertical" size={0} style={{width: '100%'}}>
                                <Space size={[4, 4]} wrap>
                                  <Tag>{CRAWLER_SOURCE_LABELS[task.task_type] || task.task_type}</Tag>
                                  <Tag color={task.status === 'success' || task.status === 'partial' ? 'green' : task.status === 'failed' ? 'red' : task.status === 'skipped' ? 'orange' : 'blue'}>{CRAWLER_TASK_STATUS_LABELS[task.status] || task.status}</Tag>
                                  <Typography.Text>{task.target_name || task.target_address || task.target_url || `任务 ${task.id}`}</Typography.Text>
                                </Space>
                                {task.error_message && <Typography.Text type="secondary">{task.error_message}</Typography.Text>}
                              </Space>
                            </List.Item>
                          )}
                        />
                      </Space>
                    </Card>
                  )}
                  {inlineResult('crawlerCompetitor')}
                  {inlineResult('crawlerSupporting')}
                  {inlineResult('crawlerRent')}
                  {inlineResult('crawlerManualUrl')}
                </Space>
            </Card>

            <Card size="small" className={(projectCompetitorCount > 0 || projectRentCount > 0) ? 'v11-step-card active' : 'v11-step-card'} title="Step 5：人工确认和补充" extra={<Tag color="orange">需人工确认</Tag>}>
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
                  <Popconfirm
                    title="生成演示模拟数据？"
                    description="系统会基于已采集的POI补齐一批示例竞品、配套和租金数据，仅用于演示，不代表真实调研。"
                    okText="生成演示数据"
                    cancelText="取消"
                    onConfirm={runDemoData}
                  >
                    <Button
                      disabled={!selectedProjectId}
                      loading={actionLoading === 'demoData'}
                      block
                    >
                      一键生成演示数据
                    </Button>
                  </Popconfirm>
                  <Typography.Text type="secondary">
                    人工审核重点：竞品是否真实、价格/配置/上座率、真实租金、夜间营业情况。
                  </Typography.Text>
                  {inlineResult('demoData')}
                </Space>
            </Card>

            <Card size="small" className={hasQualityResult ? 'v11-step-card done' : 'v11-step-card'} title="Step 6：AI 数据核验" extra={doneTag(hasQualityResult, actionLoading === 'quality' || actionLoading === 'ai-review')}>
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
                  <Button
                    type={hasQualityResult ? 'default' : 'primary'}
                    icon={hasQualityResult ? <CheckCircleOutlined /> : undefined}
                    loading={actionLoading === 'quality' || actionLoading === 'ai-review'}
                    disabled={!selectedProjectId || !hasAnyProjectData}
                    onClick={checkQuality}
                    block
                  >
                    {hasQualityResult ? '数据已核验 / 重新核验' : 'AI 数据核验'}
                  </Button>
                  {inlineResult('quality')}
                  {inlineResult('aiReview')}
                </Space>
            </Card>

            <Card size="small" className={hasScoreResult ? 'v11-step-card done' : 'v11-step-card'} title="Step 7：评分分析" extra={doneTag(hasScoreResult, actionLoading === 'score')}>
                <Space direction="vertical" size={8} style={{width: '100%'}}>
                  <Button
                    type={hasScoreResult ? 'default' : 'primary'}
                    icon={hasScoreResult ? <CheckCircleOutlined /> : undefined}
                    loading={actionLoading === 'score'}
                    disabled={!selectedProjectId || !hasQualityResult}
                    onClick={runScore}
                    block
                  >
                    {hasScoreResult ? '评分已完成 / 重新评分' : '开始评分分析'}
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

            <Card size="small" className={hasReportResult ? 'v11-step-card done' : 'v11-step-card'} title="Step 8：生成报告和继续咨询" extra={doneTag(hasReportResult, actionLoading === 'report')}>
              <Space direction="vertical" size={8} style={{width: '100%'}}>
                <Button
                  type={hasReportResult ? 'default' : 'primary'}
                  icon={hasReportResult ? <CheckCircleOutlined /> : <FileTextOutlined />}
                  loading={actionLoading === 'report'}
                  disabled={!selectedProjectId || !hasScoreResult}
                  onClick={runReport}
                  block
                >
                  {hasReportResult ? '报告已生成 / 重新生成' : '生成 AI 报告'}
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

        {cityInsight && (
          <Suspense fallback={<Card loading title="城市洞察" />}>
            <CityInsightPanel insight={cityInsight} />
          </Suspense>
        )}
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
                    {quality.crawler_quality && Number(quality.crawler_quality.total_task_count || 0) > 0 && (
                      <Alert
                        style={{marginTop: 8}}
                        type="info"
                        showIcon
                        message="公开网页补充数据"
                        description={`任务 ${countText(quality.crawler_quality.total_task_count)} 个，执行中 ${countText(quality.crawler_quality.running_task_count)} 个，成功 ${countText(quality.crawler_quality.success_task_count)} 个，搜索到候选网页 ${countText(quality.crawler_quality.discovered_url_count)} 个，待人工确认 ${countText(quality.crawler_quality.pending_review_count)} 条，跳过 ${countText(quality.crawler_quality.skipped_task_count)} 个，失败 ${countText(quality.crawler_quality.failed_task_count)} 个。`}
                      />
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
                    <Typography.Text type="secondary">导出入口已移到报告末尾，阅读确认后再导出。</Typography.Text>
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
                <div ref={reportPrintRef} className="v11-report-print-root">
                  <header className="v11-report-cover">
                    <div className="v11-report-kicker">ESPORTS SITE SELECTION</div>
                    <h1>{projectTitle(selectedProject)} · 电竞馆选址分析报告</h1>
                    <div className="v11-report-meta">
                      {selectedProject?.city || '城市待补充'}
                      {selectedProject?.district ? ` · ${selectedProject.district}` : ''}
                      {selectedProject?.address ? ` · ${selectedProject.address}` : ''}
                      {selectedProject?.radius_meters ? ` · 分析半径 ${selectedProject.radius_meters} 米` : ''}
                    </div>
                    <div className="v11-report-badges">
                      <span className="v11-report-badge">AI 分析报告</span>
                      <span className="v11-report-badge">数据完整度 {quality ? `${qualityScore}%` : '待核验'}</span>
                      {hasSimulationData && <span className="v11-report-badge warning">包含演示模拟数据</span>}
                      {Number(crawlerQuality.pending_review_count || 0) > 0 && (
                        <span className="v11-report-badge warning">
                          爬虫线索待确认 {countText(crawlerQuality.pending_review_count)} 条
                        </span>
                      )}
                    </div>
                    <div className="v11-report-summary">
                      <div className="v11-report-summary-item">
                        <span className="v11-report-summary-label">综合评分</span>
                        <span className="v11-report-summary-value">{score?.total_score ?? '--'} 分</span>
                      </div>
                      <div className="v11-report-summary-item">
                        <span className="v11-report-summary-label">推荐等级</span>
                        <span className="v11-report-summary-value">{score?.level || '待评分'}</span>
                      </div>
                      <div className="v11-report-summary-item">
                        <span className="v11-report-summary-label">报告生成时间</span>
                        <span className="v11-report-summary-value small">{formatReportDate(reportCreatedAt)}</span>
                      </div>
                      <div className="v11-report-summary-item">
                        <span className="v11-report-summary-label">数据可信状态</span>
                        <span className="v11-report-summary-value small">{reportTrustLabel}</span>
                      </div>
                    </div>
                  </header>
                  {(qualityScore < 80 || hasSimulationData || Number(crawlerQuality.pending_review_count || 0) > 0) && (
                    <section className="v11-report-quality-note">
                      <strong>阅读提示：</strong>
                      {hasSimulationData
                        ? '本报告包含演示模拟数据，只用于展示系统流程，不可直接用于投资决策。'
                        : Number(crawlerQuality.pending_review_count || 0) > 0
                          ? `仍有 ${countText(crawlerQuality.pending_review_count)} 条爬虫线索待人工确认，相关内容只能作为调查方向。`
                          : `当前数据完整度为 ${qualityScore}%，请优先完成报告中列出的人工核实清单。`}
                    </section>
                  )}
                  <MarkdownReport content={reportContent} showToc />
                  <footer className="v11-report-footer">
                    <strong>数据使用说明：</strong>
                    本报告仅依据系统中已采集、已确认及明确标注的数据生成。待确认线索和演示模拟数据不能替代现场调查，
                    最终投资决策前应完成人工核实。
                  </footer>
                </div>
                <Card size="small" className="v11-report-export-card">
                  <Space direction="vertical" size={8}>
                    <Typography.Text strong>报告导出</Typography.Text>
                    <Typography.Text type="secondary">导出文件会保留标题、目录、表格和数据状态标识；打印只包含正式报告。</Typography.Text>
                    <Space wrap>
                      <Button
                        type="primary"
                        onClick={() => reportPrintRef.current && downloadReportHtml(
                          `${projectTitle(selectedProject)}-选址报告.html`,
                          reportPrintRef.current,
                        )}
                      >
                        导出 HTML
                      </Button>
                      <Button onClick={printReport}>打印 / PDF</Button>
                    </Space>
                  </Space>
                </Card>
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

        <Card title={<Space><RobotOutlined />AI 助手</Space>} className="v11-chat-card">
          <Typography.Text type="secondary" className="v11-chat-hint">围绕当前项目提问，不会修改真实数据。</Typography.Text>
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
          <div className="v11-quick-actions">
            {QUICK_MESSAGES.map(item => <Button key={item} size="small" onClick={() => setChatInput(item)}>{item}</Button>)}
          </div>
          <Space.Compact className="v11-chat-input-row" style={{width: '100%'}}>
            <Input.TextArea
              value={chatInput}
              placeholder="输入选址问题"
              autoSize={{minRows: 2, maxRows: 4}}
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
            dataSource={visibleDataSources}
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
      <Modal
        title="手动添加公开网页链接"
        open={manualUrlOpen}
        onCancel={() => setManualUrlOpen(false)}
        onOk={submitManualUrl}
        confirmLoading={actionLoading === 'crawlerManualUrl'}
        okText="创建抓取任务"
        cancelText="取消"
      >
        <Alert
          type="info"
          showIcon
          style={{marginBottom: 12}}
          message="用于搜索引擎不可控时的兜底抓取"
          description="请输入允许公开访问的网页链接。系统只抓取页面公开内容，结果仍需人工确认。"
        />
        <Form form={manualUrlForm} layout="vertical" initialValues={{task_type: 'competitor'}}>
          <Form.Item name="task_type" label="数据类型" rules={[{required: true, message: '请选择数据类型'}]}>
            <Select
              options={[
                {value: 'competitor', label: '竞品'},
                {value: 'supporting', label: '配套'},
                {value: 'rent', label: '租金'},
              ]}
            />
          </Form.Item>
          <Form.Item noStyle shouldUpdate={(previous, current) => previous.task_type !== current.task_type}>
            {({getFieldValue}) => getFieldValue('task_type') === 'supporting' ? (
              <Form.Item name="record_type" label="配套分类" rules={[{required: true, message: '请选择配套分类'}]}>
                <Select
                  options={[
                    {value: 'food', label: '餐饮'},
                    {value: 'entertainment', label: '娱乐'},
                  ]}
                />
              </Form.Item>
            ) : null}
          </Form.Item>
          <Form.Item noStyle shouldUpdate={(previous, current) => previous.task_type !== current.task_type}>
            {({getFieldValue}) => {
              const taskType = getFieldValue('task_type') || 'competitor';
              const presets = crawlSourcePresets(selectedProject, taskType);
              return (
                <Card size="small" style={{marginBottom: 12}} title={`${CRAWLER_SOURCE_LABELS[taskType] || '数据'}推荐来源`}>
                  <Space direction="vertical" size={8} style={{width: '100%'}}>
                    <Typography.Text type="secondary">
                      这些是常用公开入口。最好打开网站后复制具体详情页 URL；如果先用入口页，系统会尽量抓取页面中的公开线索。
                    </Typography.Text>
                    <Space size={[6, 6]} wrap>
                      {presets.map(preset => (
                        <Button
                          key={preset.label}
                          size="small"
                          onClick={() => manualUrlForm.setFieldsValue({
                            name: preset.name,
                            address: selectedProject?.address || '',
                            url: preset.url,
                          })}
                        >
                          {preset.label}
                        </Button>
                      ))}
                    </Space>
                  </Space>
                </Card>
              );
            }}
          </Form.Item>
          <Form.Item name="name" label="名称" rules={[{required: true, message: '请输入名称'}]}>
            <Input placeholder="例如：某电竞馆 / 某商铺出租信息" />
          </Form.Item>
          <Form.Item name="address" label="地址">
            <Input placeholder="可选，便于后续人工确认" />
          </Form.Item>
          <Form.Item
            name="url"
            label="公开网页 URL"
            rules={[
              {required: true, message: '请输入公开网页 URL'},
              {type: 'url', message: '请输入有效 URL，例如 https://example.com/page'},
            ]}
          >
            <Input placeholder="https://..." />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
}
