import {useEffect, useMemo, useRef, useState} from 'react';
import {
  Alert,
  Button,
  Card,
  Col,
  Descriptions,
  List,
  Progress,
  Row,
  Space,
  Statistic,
  Tag,
  Typography,
  message,
} from 'antd';
import {
  CheckCircleOutlined,
  CloudDownloadOutlined,
  DownloadOutlined,
  EditOutlined,
  FileTextOutlined,
  FormOutlined,
  PrinterOutlined,
  SafetyCertificateOutlined,
} from '@ant-design/icons';
import {useNavigate, useParams} from 'react-router-dom';
import {collectProjectAmap, collectProjectCompetitors, collectProjectSupporting, geocodeProject, getProject, getProjectDataQuality} from '../../api/projects';
import {generateAiReport} from '../../api/report';
import MarkdownReport from '../../components/MarkdownReport';
import DataCollectionCenter from '../../components/DataCollectionCenter';
import AIQuestionForm from '../../components/AIQuestionForm';

const STATUS_TEXT: Record<string, string> = {
  pending_review: '初始化',
  confirmed: '初始化',
  collecting: '数据采集中',
  supplementing: '数据补充中',
  scored: '分析完成',
  reported: '已生成报告',
};

function safeText(value: unknown, fallback = '-') {
  return value === undefined || value === null || value === '' ? fallback : String(value);
}

function statusTag(status?: string) {
  const text = STATUS_TEXT[status || ''] || '初始化';
  const color =
    text === '已生成报告' ? 'purple' :
    text === '分析完成' ? 'green' :
    text === '数据补充中' ? 'orange' :
    text === '数据采集中' ? 'blue' :
    'default';
  return <Tag color={color}>{text}</Tag>;
}

function countValue(value: unknown) {
  return typeof value === 'number' ? value : '--';
}

function stringList(value: unknown): string[] {
  if (!Array.isArray(value)) return [];
  return value.map(item => {
    if (typeof item === 'string') return item;
    if (item && typeof item === 'object') {
      const record = item as Record<string, unknown>;
      return String(record.description || record.message || record.field || '待核实数据');
    }
    return String(item);
  });
}

function htmlEscape(value: unknown) {
  const entities: Record<string, string> = {
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#039;',
  };
  return String(value ?? '').replace(/[&<>"']/g, character => entities[character] || character);
}

function StepCard({
  step,
  title,
  description,
  icon,
  children,
  actionText,
  actionLoading,
  actionFirst,
  actionDisabled,
  prerequisite,
  status,
  onAction,
}: {
  step: number;
  title: string;
  description: string;
  icon: React.ReactNode;
  children?: React.ReactNode;
  actionText?: string;
  actionLoading?: boolean;
  actionFirst?: boolean;
  actionDisabled?: boolean;
  prerequisite?: string;
  status: 'completed' | 'active' | 'pending';
  onAction?: () => void;
}) {
  const actionButton = actionText && onAction ? (
    <Button style={{marginTop: 12}} loading={actionLoading} disabled={actionDisabled} onClick={onAction}>
      {actionText}
    </Button>
  ) : null;
  const statusView = status === 'completed'
    ? {text: '已完成', color: 'green'}
    : status === 'active'
      ? {text: '当前步骤', color: 'blue'}
      : {text: '待开始', color: 'default'};

  return (
    <Card id={`workflow-step-${step}`} className={`workflow-step-card status-${status}`} data-step-status={status}>
      <Space align="start" size={16} className="workflow-step-layout">
        <div className="workflow-step-icon">{status === 'completed' ? <CheckCircleOutlined /> : icon}</div>
        <div className="workflow-step-content">
          <Space wrap>
            <Tag color="blue">Step {step}</Tag>
            <Typography.Title level={4} style={{margin: 0}}>{title}</Typography.Title>
            <Tag color={statusView.color}>{statusView.text}</Tag>
          </Space>
          <Typography.Paragraph type="secondary" style={{marginTop: 8}}>{description}</Typography.Paragraph>
          {status === 'pending' && prerequisite && (
            <Alert type="info" showIcon message={`前置条件：${prerequisite}`} style={{marginBottom: 12}} />
          )}
          {actionFirst && actionButton}
          {children}
          {!actionFirst && actionButton}
        </div>
      </Space>
    </Card>
  );
}

const READINESS_GROUPS = [
  ['technical_prerequisites', '技术前置条件'],
  ['key_unknowns', '关键未知'],
  ['recommended', '建议补充'],
  ['optional', '可选信息'],
] as const;

const READINESS_STATUS: Record<string, {text: string; color: string}> = {
  complete: {text: '已完成', color: 'green'},
  not_applicable: {text: '无需补充', color: 'green'},
  optional: {text: '可选', color: 'default'},
  acknowledged_unknown: {text: '已标记未知', color: 'blue'},
  missing: {text: '待补充', color: 'orange'},
  blocked: {text: '阻塞', color: 'red'},
};

function ReadinessPanel({result, onSupplement}: {result: any; onSupplement: () => void}) {
  const readiness = result?.readiness || {};
  const percent = Math.max(0, Math.min(100, Number(readiness?.completion_percent) || 0));
  const groups = readiness?.groups || {};
  const statusText = readiness?.status === 'ready'
    ? '可以生成正式报告'
    : readiness?.status === 'blocked'
      ? '技术前置条件未完成'
      : '可以继续，但建议先补充关键数据';
  return (
    <Space direction="vertical" size={12} style={{width: '100%'}}>
      <Alert
        type={readiness?.status === 'ready' ? 'success' : readiness?.status === 'blocked' ? 'error' : 'warning'}
        showIcon
        message={statusText}
        description={readiness?.score_explanation || '准备度仅表示数据准备情况，不代表项目推荐概率。'}
      />
      <Card size="small" title="数据准备度">
        <Progress percent={percent} status={readiness?.status === 'ready' ? 'success' : 'normal'} />
        <Typography.Text type="secondary">
          已完成 {Number(readiness?.summary?.complete) || 0} 项，
          待补充 {Number(readiness?.summary?.missing) || 0} 项，
          阻塞 {Number(readiness?.summary?.blocked) || 0} 项。
        </Typography.Text>
      </Card>
      <Row gutter={[12, 12]}>
        {READINESS_GROUPS.map(([key, title]) => (
          <Col xs={24} lg={12} key={key}>
            <Card size="small" title={title} style={{height: '100%'}}>
              <List
                size="small"
                dataSource={Array.isArray(groups[key]) ? groups[key] : []}
                locale={{emptyText: '暂无检查项'}}
                renderItem={(item: any) => {
                  const view = READINESS_STATUS[item?.status] || {text: item?.status || '未知', color: 'default'};
                  return (
                    <List.Item>
                      <List.Item.Meta
                        title={<Space wrap><Tag color={view.color}>{view.text}</Tag><Typography.Text strong>{safeText(item?.label)}</Typography.Text></Space>}
                        description={<><div>{safeText(item?.summary)}</div>{item?.action && <Typography.Text type="secondary">下一步：{safeText(item.action)}</Typography.Text>}</>}
                      />
                    </List.Item>
                  );
                }}
              />
            </Card>
          </Col>
        ))}
      </Row>
      {(readiness?.status === 'needs_input' || readiness?.status === 'blocked') && (
        <Button onClick={onSupplement}>进入人工补充</Button>
      )}
    </Space>
  );
}

export default function ProjectDetailPage() {
  const {projectId = ''} = useParams();
  const navigate = useNavigate();
  const [project, setProject] = useState<any>(null);
  const [projectStats, setProjectStats] = useState<Record<string, any>>({});
  const [loadingProject, setLoadingProject] = useState(false);
  const [collecting, setCollecting] = useState(false);
  const [collectResult, setCollectResult] = useState<any>(null);
  const [collectError, setCollectError] = useState<string>('');
  const [collectingCompetitors, setCollectingCompetitors] = useState(false);
  const [competitorCollectResult, setCompetitorCollectResult] = useState<any>(null);
  const [competitorCollectError, setCompetitorCollectError] = useState('');
  const [collectingSupporting, setCollectingSupporting] = useState(false);
  const [supportingCollectResult, setSupportingCollectResult] = useState<any>(null);
  const [supportingCollectError, setSupportingCollectError] = useState('');
  const [checkingQuality, setCheckingQuality] = useState(false);
  const [qualityResult, setQualityResult] = useState<any>(null);
  const [qualityError, setQualityError] = useState<string>('');
  const [generatingReport, setGeneratingReport] = useState(false);
  const [reportResult, setReportResult] = useState<any>(null);
  const [reportError, setReportError] = useState<string>('');
  const [importantInfoSaved, setImportantInfoSaved] = useState(false);
  const reportRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!projectId) return;
    setLoadingProject(true);
    getProject(projectId)
      .then(data => {
        setProject(data.project || data);
        setProjectStats(data.stats || {});
      })
      .catch(error => message.error(error?.response?.data?.detail || error.message || '加载项目失败'))
      .finally(() => setLoadingProject(false));
  }, [projectId]);

  const currentStatus = useMemo(() => project?.status || 'confirmed', [project]);

  const runAmapCollect = async () => {
    if (!projectId) return;
    setCollecting(true);
    setCollectError('');
    try {
      const result = await collectProjectAmap(projectId);
      setCollectResult(result);
      if (result?.success === false) {
        message.warning(result?.message || '高德采集未完成');
      } else {
        const refreshed = await getProject(projectId);
        setProject(refreshed?.project || refreshed);
        setProjectStats(refreshed?.stats || {});
        message.success(result?.message || '高德采集完成');
      }
    } catch (error: any) {
      const reason = error?.response?.data?.detail || error?.message || '采集失败';
      setCollectError(typeof reason === 'string' ? reason : JSON.stringify(reason));
      message.error('采集失败');
    } finally {
      setCollecting(false);
    }
  };

  const confirmGeocodeCandidate = async (candidateIndex: number) => {
    if (!projectId) return;
    setCollecting(true);
    setCollectError('');
    try {
      const geocode = await geocodeProject(projectId, true, candidateIndex);
      if (geocode?.success === false) {
        throw new Error(geocode?.message || '地址确认失败');
      }
      const result = await collectProjectAmap(projectId);
      setCollectResult(result);
      const refreshed = await getProject(projectId);
      setProject(refreshed?.project || refreshed);
      setProjectStats(refreshed?.stats || {});
      if (result?.success === false) message.warning(result?.message || '地址已确认，但采集未完成');
      else message.success(result?.message || '地址已确认并完成高德采集');
    } catch (error: any) {
      const reason = error?.response?.data?.detail || error?.message || '地址确认失败';
      setCollectError(typeof reason === 'string' ? reason : JSON.stringify(reason));
      message.error('地址确认失败');
    } finally {
      setCollecting(false);
    }
  };

  const runQualityCheck = async () => {
    if (!projectId) return;
    setCheckingQuality(true);
    setQualityError('');
    setQualityResult(null);
    try {
      const result = await getProjectDataQuality(projectId);
      setQualityResult(result);
      message.success('数据准备度检查完成');
    } catch (error: any) {
      const reason = error?.response?.data?.detail || error?.message || '数据核验失败';
      setQualityError(typeof reason === 'string' ? reason : reason?.message || '请求失败，请稍后重试');
      message.error('数据核验失败');
    } finally {
      setCheckingQuality(false);
    }
  };

  const runCompetitorCollect = async () => {
    if (!projectId) return;
    setCollectingCompetitors(true);
    setCompetitorCollectError('');
    try {
      const result = await collectProjectCompetitors(projectId);
      setCompetitorCollectResult(result);
      if (result?.success === false) {
        setCompetitorCollectError(result?.message || '竞品采集失败');
        message.warning(result?.message || '竞品采集失败');
        return;
      }
      const refreshed = await getProject(projectId);
      setProjectStats(refreshed?.stats || {});
      const discoveredCount = Number(result?.discovered_count) || 0;
      message.success(
        discoveredCount > 0
          ? `发现 ${discoveredCount} 个疑似竞品，请确认哪些是真正电竞馆竞品`
          : '未发现电竞馆相关竞品',
      );
    } catch (error: any) {
      const reason = error?.response?.data?.detail || error?.message || '竞品采集失败';
      setCompetitorCollectError(typeof reason === 'string' ? reason : '请求失败，请稍后重试');
      message.error('竞品采集失败');
    } finally {
      setCollectingCompetitors(false);
    }
  };

  const runSupportingCollect = async () => {
    if (!projectId) return;
    setCollectingSupporting(true);
    setSupportingCollectError('');
    try {
      const result = await collectProjectSupporting(projectId);
      setSupportingCollectResult(result);
      if (result?.success === false) {
        setSupportingCollectError(result?.message || '周边配套采集失败');
        message.warning(result?.message || '周边配套采集失败');
        return;
      }
      const refreshed = await getProject(projectId);
      setProjectStats(refreshed?.stats || {});
      message.success(
        `周边配套采集完成：餐饮 ${Number(result?.food_count) || 0} 条，娱乐 ${Number(result?.entertainment_count) || 0} 条，夜间商业 ${Number(result?.night_business_count) || 0} 条`,
      );
    } catch (error: any) {
      const reason = error?.response?.data?.detail || error?.message || '周边配套采集失败';
      setSupportingCollectError(typeof reason === 'string' ? reason : '请求失败，请稍后重试');
      message.error('周边配套采集失败');
    } finally {
      setCollectingSupporting(false);
    }
  };

  const runReportGeneration = async () => {
    if (!projectId) return;
    setGeneratingReport(true);
    setReportError('');
    setReportResult(null);
    try {
      const result = await generateAiReport(projectId);
      if (result?.success === false) {
        throw new Error(result.message || 'AI报告生成失败');
      }
      if (!result?.content) {
        throw new Error('报告已生成，但未返回可展示的内容');
      }
      setReportResult(result);
      message.success('AI报告生成完成');
    } catch (error: any) {
      const reason = error?.response?.data?.detail || error?.message || '报告生成失败';
      setReportError(typeof reason === 'string' ? reason : reason?.message || '请求失败，请稍后重试');
      message.error('报告生成失败');
    } finally {
      setGeneratingReport(false);
    }
  };

  const exportReportHtml = () => {
    if (!reportRef.current || !reportResult?.content) {
      message.warning('请先生成报告');
      return;
    }
    const title = `${project?.name || '电竞馆选址'}分析报告`;
    const documentHtml = `<!doctype html><html lang="zh-CN"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>${htmlEscape(title)}</title><style>body{margin:0;background:#f3f5f8;color:#263548;font-family:"Microsoft YaHei",sans-serif;line-height:1.8}.report-export-root{max-width:980px;margin:24px auto;padding:40px;background:#fff}h1{color:#102033}h2{margin-top:32px;padding-bottom:8px;border-bottom:1px solid #d9e4ef;color:#153b62}table{width:100%;border-collapse:collapse}th,td{padding:8px 10px;border:1px solid #dce4ec;text-align:left;vertical-align:top}th{background:#edf4fa}blockquote{margin:16px 0;padding:12px 16px;border-left:4px solid #4a86bd;background:#f5f9fd}@media print{body{background:#fff}.report-export-root{max-width:none;margin:0;padding:0}}</style></head><body><main class="report-export-root">${reportRef.current.innerHTML}</main></body></html>`;
    const blob = new Blob([documentHtml], {type: 'text/html;charset=utf-8'});
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `${String(project?.name || '电竞馆选址报告').replace(/[\\/:*?"<>|]/g, '-')}.html`;
    link.click();
    URL.revokeObjectURL(url);
    message.success('HTML 报告已导出');
  };

  const printReport = () => {
    if (!reportRef.current) {
      message.warning('请先生成报告');
      return;
    }
    const cleanup = () => document.body.classList.remove('project-report-printing');
    document.body.classList.add('project-report-printing');
    window.addEventListener('afterprint', cleanup, {once: true});
    window.print();
  };

  const collected = collectResult?.collected || {};
  const collectionStatus = String(collectResult?.collection_status || '');
  const collectionDiagnostics = collectResult?.diagnostics || {};
  const geocodeCandidates = Array.isArray(collectionDiagnostics?.geocode?.candidates)
    ? collectionDiagnostics.geocode.candidates
    : [];
  const categorySummary = collectionDiagnostics?.category_summary && typeof collectionDiagnostics.category_summary === 'object'
    ? Object.entries(collectionDiagnostics.category_summary) as Array<[string, any]>
    : [];
  const categoryNames: Record<string, string> = {
    transport: '交通', competitor: '疑似竞品', education: '教育', residential: '住宅', food: '餐饮', entertainment: '娱乐',
  };
  const missingItems = stringList(qualityResult?.missing);
  const locationReady = project?.longitude != null && project?.latitude != null;
  const amapReady = Boolean(
    collectResult?.success && collectionStatus !== 'failed' && collectionStatus !== 'needs_confirmation'
    || Number(projectStats?.poi_count) > 0,
  );
  const flowFinished = Boolean(reportResult?.content);
  const stepStatus = (step: number): 'completed' | 'active' | 'pending' => {
    if (flowFinished) return 'completed';
    if (step === 1) return locationReady ? 'completed' : 'active';
    if (step === 2) return amapReady ? 'completed' : locationReady ? 'active' : 'pending';
    if (step === 3) return qualityResult ? 'completed' : amapReady ? 'active' : 'pending';
    if (step === 4) return qualityResult ? 'completed' : checkingQuality ? 'active' : 'pending';
    if (step === 5) return importantInfoSaved ? 'completed' : qualityResult ? 'active' : 'pending';
    return importantInfoSaved ? 'active' : 'pending';
  };
  const currentStage = flowFinished
    ? {step: 6, title: '流程已完成', next: '查看报告，或在补充新数据后重新生成。'}
    : importantInfoSaved
      ? {step: 6, title: '生成 AI 选址报告', next: '生成并核对最终报告。'}
      : qualityResult
        ? {step: 5, title: '确认重要信息', next: '回答关键问题，也可将暂时无法获得的信息标记为未知。'}
        : amapReady
          ? {step: 3, title: '查看与人工补充', next: '确认竞品、配套及候选物业信息，再检查数据准备度。'}
          : locationReady
            ? {step: 2, title: '获取高德 POI', next: '采集周边交通、疑似竞品、餐饮和娱乐数据。'}
            : {step: 1, title: '确认地址和范围', next: '请先确保地址可以准确定位。'};

  return (
    <div className="page">
      <div className="page-title-row">
        <div>
          <Typography.Title level={2}>项目工作台</Typography.Title>
          <Typography.Paragraph type="secondary">
            按客户选址流程推进：确认地址、采集数据、补充资料、核验完整度、AI 分析、查看报告。
          </Typography.Paragraph>
        </div>
        {statusTag(currentStatus)}
      </div>

      <Card loading={loadingProject} title="项目基础信息" style={{marginBottom: 16}}>
        <Descriptions column={3} size="small">
          <Descriptions.Item label="项目名称">{safeText(project?.name)}</Descriptions.Item>
          <Descriptions.Item label="城市">{safeText(project?.city)}</Descriptions.Item>
          <Descriptions.Item label="地址">{[project?.district, project?.address].filter(Boolean).join(' ') || '-'}</Descriptions.Item>
          <Descriptions.Item label="分析范围">{project?.radius_meters ? `${project.radius_meters} 米` : '-'}</Descriptions.Item>
          <Descriptions.Item label="经营类型">{safeText(project?.business_type)}</Descriptions.Item>
          <Descriptions.Item label="当前状态">{statusTag(currentStatus)}</Descriptions.Item>
        </Descriptions>
      </Card>

      <Card className="workflow-current-stage" style={{marginBottom: 16}}>
        <div>
          <Typography.Text type="secondary">当前阶段</Typography.Text>
          <Typography.Title level={3}>Step {currentStage.step}：{currentStage.title}</Typography.Title>
          <Typography.Paragraph type="secondary">下一步：{currentStage.next}</Typography.Paragraph>
        </div>
        <Tag color={flowFinished ? 'green' : 'blue'}>{flowFinished ? '全部完成' : `进行到 ${currentStage.step} / 6`}</Tag>
      </Card>

      <Row gutter={[16, 16]}>
        <Col span={24}>
          <StepCard
            step={1}
            title="输入地址和范围"
            description="确认项目地址、城市和分析半径，这是后续采集和分析的基础。"
            icon={<EditOutlined />}
            status={stepStatus(1)}
          >
            <Descriptions column={3} size="small">
              <Descriptions.Item label="城市">{safeText(project?.city)}</Descriptions.Item>
              <Descriptions.Item label="地址">{safeText(project?.address)}</Descriptions.Item>
              <Descriptions.Item label="半径">{project?.radius_meters ? `${project.radius_meters} 米` : '-'}</Descriptions.Item>
            </Descriptions>
          </StepCard>
        </Col>

        <Col span={24}>
          <StepCard
            step={2}
            title="获取高德 POI"
            description="调用高德获取周边 POI、竞品、交通、餐饮、娱乐等基础数据。"
            icon={<CloudDownloadOutlined />}
            status={stepStatus(2)}
            prerequisite="先确认项目地址"
            actionText={collecting ? '正在获取数据...' : '获取高德 POI'}
            actionLoading={collecting}
            onAction={runAmapCollect}
          >
            {collecting && (
              <Alert style={{marginBottom: 12}} type="info" showIcon message="正在获取数据..." description="系统正在调用高德接口采集项目周边基础数据。" />
            )}
            {collectError && (
              <Alert style={{marginBottom: 12}} type="error" showIcon message="采集失败" description={collectError} />
            )}
            {collectResult && collectionStatus !== 'needs_confirmation' && (
              <Alert
                style={{marginBottom: 12}}
                type={collectionStatus === 'failed' ? 'error' : collectionStatus === 'partial' || collectionStatus === 'truncated' ? 'warning' : 'success'}
                showIcon
                message={collectResult?.message || '高德采集完成'}
                description={
                  collectionStatus === 'success_zero' ? '接口调用成功，但当前地址和范围内没有有效结果。' :
                  collectionStatus === 'partial' ? '已保存成功返回的数据；失败关键词可稍后重试。' :
                  collectionStatus === 'truncated' ? '结果达到配置上限；当前结果已去重保存。' :
                  collectionStatus === 'failed' ? '没有保存本次失败请求的数据，请检查提示后重试。' :
                  '已按高德 POI ID 去重并保存本次有效数据。'
                }
              />
            )}
            {collectionStatus === 'needs_confirmation' && (
              <Card size="small" title="请选择准确地址" style={{marginBottom: 12}}>
                <Alert type="warning" showIcon message="地址存在多个候选结果" description="确认后系统才会使用该坐标采集周边 POI。" />
                <List
                  size="small"
                  dataSource={geocodeCandidates}
                  renderItem={(candidate: any) => (
                    <List.Item actions={[<Button key="select" type="primary" size="small" onClick={() => confirmGeocodeCandidate(Number(candidate.index))}>选择此地址</Button>]}>
                      <List.Item.Meta
                        title={safeText(candidate.formatted_address, '未提供完整地址')}
                        description={`${safeText(candidate.district, '')} ${safeText(candidate.level, '')} · ${candidate.longitude}, ${candidate.latitude}`}
                      />
                    </List.Item>
                  )}
                />
              </Card>
            )}
            <Row gutter={16}>
              <Col span={6}><Statistic title="POI数量" value={countValue(collected.poi_count)} /></Col>
              <Col span={6}><Statistic title="竞品数量" value={countValue(collected.competitor_count)} /></Col>
              <Col span={6}><Statistic title="餐饮数量" value={countValue(collected.food_count)} /></Col>
              <Col span={6}><Statistic title="娱乐场所数量" value={countValue(collected.entertainment_count)} /></Col>
            </Row>
            {categorySummary.length > 0 && (
              <Space wrap style={{marginTop: 12}}>
                {categorySummary.map(([category, summary]) => (
                  <Tag key={category} color={summary?.truncated ? 'orange' : 'blue'}>
                    {categoryNames[category] || category}：{Number(summary?.unique_count) || 0} 条
                    {summary?.truncated ? '（已达上限）' : ''}
                  </Tag>
                ))}
                <Tag>原始返回 {Number(collectionDiagnostics?.raw_return_count ?? collectionDiagnostics?.raw_discovered_count) || 0}</Tag>
                <Tag>去重 {Number(collectionDiagnostics?.duplicate_count) || 0}</Tag>
                <Tag>范围外排除 {Number(collectionDiagnostics?.outside_radius_count) || 0}</Tag>
              </Space>
            )}
          </StepCard>
        </Col>

        <Col span={24}>
          <StepCard
            step={3}
            title="查看与人工补充"
            description="查看高德采集结果，并补充价格、机器配置、租金、物业费等高德无法提供的真实信息。"
            icon={<FormOutlined />}
            status={stepStatus(3)}
            prerequisite="先完成高德 POI 采集"
            actionText="进入人工补充"
            actionDisabled={!amapReady}
            onAction={() => navigate(`/projects/${projectId}/supplement`)}
          >
            <DataCollectionCenter
              projectId={projectId}
              stats={projectStats}
              collecting={collecting}
              collectResult={collectResult}
              collectError={collectError}
              collectingCompetitors={collectingCompetitors}
              competitorCollectResult={competitorCollectResult}
              competitorCollectError={competitorCollectError}
              onCollectCompetitors={runCompetitorCollect}
              collectingSupporting={collectingSupporting}
              supportingCollectResult={supportingCollectResult}
              supportingCollectError={supportingCollectError}
              onCollectSupporting={runSupportingCollect}
              onCompetitorReviewed={async () => {
                const refreshed = await getProject(projectId);
                setProjectStats(refreshed?.stats || {});
              }}
              onCompetitorDetailSaved={async () => {
                const previousScore = qualityResult?.quality_score === undefined ? null : Number(qualityResult.quality_score);
                const refreshedQuality = await getProjectDataQuality(projectId);
                setQualityResult(refreshedQuality);
                setQualityError('');
                try {
                  const refreshedProject = await getProject(projectId);
                  setProjectStats(refreshedProject?.stats || {});
                } catch {
                  // 数据质量已更新，顶部统计刷新失败不影响人工核实结果。
                }
                return {
                  previousScore: Number.isFinite(previousScore) ? previousScore : null,
                  currentScore: Number(refreshedQuality?.quality_score) || 0,
                };
              }}
            />
          </StepCard>
        </Col>

        <Col span={24}>
          <StepCard
            step={4}
            title="数据检查"
            description="按固定目录区分技术前置、关键未知、建议补充和可选信息。"
            icon={<SafetyCertificateOutlined />}
            status={stepStatus(4)}
            prerequisite="先采集并查看基础数据"
            actionText={checkingQuality ? '正在检查数据准备度...' : '检查数据准备度'}
            actionLoading={checkingQuality}
            actionDisabled={!amapReady}
            onAction={runQualityCheck}
          >
            {qualityError && (
              <Alert
                type="error"
                showIcon
                style={{marginBottom: 12}}
                message="数据核验失败"
                description={qualityError}
              />
            )}

            {!qualityResult && !qualityError && (
              <Space wrap>
                <Statistic title="数据准备度" value="--" />
                <Tag>缺失字段：暂未检查</Tag>
              </Space>
            )}

            {qualityResult && (
              <ReadinessPanel
                result={qualityResult}
                onSupplement={() => navigate(`/projects/${projectId}/supplement`)}
              />
            )}


            <Typography.Paragraph type="secondary" style={{marginTop: 12, marginBottom: 0}}>
              准备度仅表示数据是否齐备，不代表项目推荐概率；人工补充会保存到当前项目。
            </Typography.Paragraph>
          </StepCard>
        </Col>

        <Col span={24}>
          <StepCard
            step={5}
            title="确认重要信息"
            description="根据数据检查结果，确认影响选址结论的关键缺失信息。"
            icon={<SafetyCertificateOutlined />}
            status={stepStatus(5)}
            prerequisite="先执行数据准备度检查"
            actionText="查看并补充关键信息"
            actionDisabled={!qualityResult}
            onAction={() => navigate(`/projects/${projectId}/supplement`)}
          >
            {!qualityResult ? (
              <Alert
                type="info"
                showIcon
                message="请先执行数据检查，系统会列出需要确认的重要信息。"
              />
            ) : missingItems.length > 0 ? (
              <Alert
                type="warning"
                showIcon
                message={`发现 ${missingItems.length} 项待确认信息`}
                description={missingItems.slice(0, 5).join('；')}
              />
            ) : (
              <Alert type="success" showIcon message="当前未发现明确的关键缺失信息。" />
            )}
            <AIQuestionForm
              projectId={projectId}
              onSaved={async () => {
                const refreshed = await getProjectDataQuality(projectId);
                setQualityResult(refreshed);
                setQualityError('');
                setImportantInfoSaved(true);
              }}
            />
          </StepCard>
        </Col>

        <Col span={24}>
          <StepCard
            step={6}
            title="生成 AI 选址报告"
            description="使用已采集和人工确认的数据生成选址分析报告；缺失信息会在报告中明确说明。"
            icon={<FileTextOutlined />}
            status={stepStatus(6)}
            prerequisite="先执行数据准备度检查，并确认重要信息"
            actionText={generatingReport ? '正在生成选址分析报告...' : '生成 AI 报告'}
            actionLoading={generatingReport}
            actionDisabled={!qualityResult}
            onAction={runReportGeneration}
          >
            <Space direction="vertical" size={12} style={{width: '100%'}}>
              {reportError && (
                <Alert type="error" showIcon message="报告生成失败" description={reportError} />
              )}

              {reportResult?.content && (
                <Card
                  title="电竞馆选址分析报告"
                  className="ai-report-card"
                  extra={(
                    <Space className="report-actions" wrap>
                      <Button icon={<DownloadOutlined />} onClick={exportReportHtml}>导出 HTML</Button>
                      <Button icon={<PrinterOutlined />} onClick={printReport}>打印 / PDF</Button>
                    </Space>
                  )}
                >
                  <div ref={reportRef} className="report-export-root">
                    <Alert
                      type="success"
                      showIcon
                      style={{marginBottom: 16}}
                      message={reportResult.validation_status === 'passed' ? '真实性校验已通过' : '系统生成的数据不足报告'}
                      description="报告只读取高德事实、用户人工提供信息和确定性计算；每次重新生成都会保存独立快照版本。"
                    />
                    <MarkdownReport content={reportResult.content} showToc />
                  </div>
                  <div className="report-bottom-actions report-actions">
                    <Typography.Text type="secondary">报告核对完成后，可导出 HTML 或使用浏览器打印为 PDF。</Typography.Text>
                    <Space wrap>
                      <Button icon={<DownloadOutlined />} onClick={exportReportHtml}>导出 HTML</Button>
                      <Button type="primary" icon={<PrinterOutlined />} onClick={printReport}>打印 / PDF</Button>
                    </Space>
                  </div>
                </Card>
              )}
            </Space>
          </StepCard>
        </Col>
      </Row>
    </div>
  );
}
