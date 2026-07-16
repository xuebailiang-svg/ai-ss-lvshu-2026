import {useEffect, useMemo, useState} from 'react';
import {
  Alert,
  Button,
  Card,
  Col,
  Descriptions,
  Divider,
  List,
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
  CheckCircleOutlined,
  CloudDownloadOutlined,
  EditOutlined,
  FileTextOutlined,
  FormOutlined,
  RobotOutlined,
  SafetyCertificateOutlined,
  SearchOutlined,
} from '@ant-design/icons';
import {useNavigate, useParams} from 'react-router-dom';
import {collectProjectAmap, collectProjectCompetitors, collectProjectSupporting, getProject, getProjectDataQuality} from '../../api/projects';
import {generateAiReport} from '../../api/report';
import {scoreProject} from '../../api/score';
import MarkdownReport from '../../components/MarkdownReport';
import ProjectAssistant from '../../components/ProjectAssistant';
import DataCollectionCenter from '../../components/DataCollectionCenter';

const STATUS_TEXT: Record<string, string> = {
  pending_review: '初始化',
  confirmed: '初始化',
  collecting: '数据采集中',
  supplementing: '数据补充中',
  scored: '分析完成',
  reported: '已生成报告',
};

const DIMENSION_TEXT: Record<string, string> = {
  population: '人口条件',
  traffic: '交通条件',
  competitor: '竞争环境',
  support: '夜间消费环境',
  rent: '租金成本',
  risk: '风险情况',
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

function StepCard({
  step,
  title,
  description,
  icon,
  children,
  actionText,
  actionLoading,
  actionFirst,
  onAction,
}: {
  step: number;
  title: string;
  description: string;
  icon: React.ReactNode;
  children?: React.ReactNode;
  actionText: string;
  actionLoading?: boolean;
  actionFirst?: boolean;
  onAction: () => void;
}) {
  const actionButton = (
    <Button style={{marginTop: 12}} loading={actionLoading} onClick={onAction}>
      {actionText}
    </Button>
  );

  return (
    <Card className="workflow-step-card">
      <Space align="start" size={16}>
        <div className="workflow-step-icon">{icon}</div>
        <div style={{flex: 1}}>
          <Space>
            <Tag color="blue">Step {step}</Tag>
            <Typography.Title level={4} style={{margin: 0}}>{title}</Typography.Title>
          </Space>
          <Typography.Paragraph type="secondary" style={{marginTop: 8}}>{description}</Typography.Paragraph>
          {actionFirst && actionButton}
          {children}
          {!actionFirst && actionButton}
        </div>
      </Space>
    </Card>
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
  const [scoring, setScoring] = useState(false);
  const [scoreResult, setScoreResult] = useState<any>(null);
  const [scoreError, setScoreError] = useState<string>('');
  const [generatingReport, setGeneratingReport] = useState(false);
  const [reportResult, setReportResult] = useState<any>(null);
  const [reportError, setReportError] = useState<string>('');

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
  const placeholder = () => message.info('该步骤将在后续小任务中接入真实功能');

  const runAmapCollect = async () => {
    if (!projectId) return;
    setCollecting(true);
    setCollectError('');
    try {
      const result = await collectProjectAmap(projectId);
      setCollectResult(result);
      message.success('高德采集完成');
    } catch (error: any) {
      const reason = error?.response?.data?.detail || error?.message || '采集失败';
      setCollectError(typeof reason === 'string' ? reason : JSON.stringify(reason));
      message.error('采集失败');
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
      message.success('数据完整度检查完成');
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

  const runScoring = async () => {
    if (!projectId) return;
    setScoring(true);
    setScoreError('');
    setScoreResult(null);
    setReportResult(null);
    setReportError('');
    try {
      const result = await scoreProject(projectId);
      setScoreResult(result);
      message.success('评分分析完成');
    } catch (error: any) {
      const reason = error?.response?.data?.detail || error?.message || '评分分析失败';
      setScoreError(typeof reason === 'string' ? reason : reason?.message || '请求失败，请稍后重试');
      message.error('评分分析失败');
    } finally {
      setScoring(false);
    }
  };

  const runReportGeneration = async () => {
    if (!projectId || !scoreResult) return;
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

  const collected = collectResult?.collected || {};
  const qualityScore = Math.max(0, Math.min(100, Number(qualityResult?.quality_score) || 0));
  const missingItems = stringList(qualityResult?.missing);
  const warningItems = stringList(qualityResult?.warnings);
  const competitorDetailQuality = qualityResult?.competitor_detail_quality || {};
  const competitorMissingSummary = Array.isArray(competitorDetailQuality?.missing_summary)
    ? competitorDetailQuality.missing_summary
    : [];
  const incompleteCompetitors = Array.isArray(competitorDetailQuality?.incomplete_items)
    ? competitorDetailQuality.incomplete_items
    : [];
  const supportingDetailQuality = qualityResult?.supporting_detail_quality || {};
  const supportingMissingSummary = Array.isArray(supportingDetailQuality?.missing_summary)
    ? supportingDetailQuality.missing_summary
    : [];
  const incompleteSupportingItems = Array.isArray(supportingDetailQuality?.incomplete_items)
    ? supportingDetailQuality.incomplete_items
    : [];
  const rentQuality = qualityResult?.rent_quality || {};
  const rentMissingSummary = Array.isArray(rentQuality?.missing_summary)
    ? rentQuality.missing_summary
    : [];
  const incompleteRentItems = Array.isArray(rentQuality?.incomplete_items)
    ? rentQuality.incomplete_items
    : [];
  const dimensionEntries = Object.entries(scoreResult?.dimensions || {}) as Array<[string, any]>;
  const scoreAdvantages = stringList(scoreResult?.advantages);
  const scoreRisks = stringList(scoreResult?.risks);
  const scoreMissing = stringList(scoreResult?.missing_data);
  const competitorAnalysis = scoreResult?.competitor_analysis || {};
  const supportingAnalysis = scoreResult?.supporting_analysis || {};
  const rentAnalysis = scoreResult?.rent_analysis || {};
  const competitionLevelText: Record<string, string> = {
    low: '较低',
    medium: '中等',
    high: '较高',
  };
  const nightActivityLevelText: Record<string, string> = {
    none: '未形成',
    low: '较低',
    medium: '中等',
    high: '较高',
  };
  const rentPressureText: Record<string, string> = {
    low: '较低',
    medium: '中等',
    high: '较高',
    unknown: '数据不足',
  };

  const locateCompetitorDetail = (competitorId: number) => {
    const target = document.getElementById(`competitor-item-${competitorId}`)
      || document.getElementById('competitor-review-section');
    target?.scrollIntoView({behavior: 'smooth', block: 'center'});
    message.info('请在竞品列表中点击“补充详情”继续完善经营信息');
  };

  const locateSupportingDetail = (supportingId: string) => {
    const targetId = `supporting-item-${String(supportingId).replace(':', '-')}`;
    const target = document.getElementById(targetId)
      || document.getElementById('supporting-review-section');
    target?.scrollIntoView({behavior: 'smooth', block: 'center'});
    message.info('请在周边配套列表中点击“补充详情”继续完善营业信息');
  };

  const locateRentDetail = (rentId: number) => {
    const target = document.getElementById(`rent-item-${rentId}`)
      || document.getElementById('rent-data-section');
    target?.scrollIntoView({behavior: 'smooth', block: 'center'});
    message.info('请在租金数据列表中点击“补充详情”继续完善物业和来源信息。');
  };

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
          const previousScore = qualityResult?.quality_score === undefined
            ? null
            : Number(qualityResult.quality_score);
          const refreshedQuality = await getProjectDataQuality(projectId);
          setQualityResult(refreshedQuality);
          setQualityError('');
          try {
            const refreshedProject = await getProject(projectId);
            setProjectStats(refreshedProject?.stats || {});
          } catch {
            // Step 5 已更新，项目顶部统计刷新失败不影响数据质量结果。
          }
          return {
            previousScore: Number.isFinite(previousScore) ? previousScore : null,
            currentScore: Number(refreshedQuality?.quality_score) || 0,
          };
        }}
      />

      <Card title="选址分析流程" style={{marginBottom: 16}}>
        <Steps
          current={collectResult ? 1 : 0}
          items={[
            {title: '地址输入'},
            {title: '高德 POI'},
            {title: '爬虫补充'},
            {title: '人工补充'},
            {title: '数据核验'},
            {title: '评分与报告'},
          ]}
        />
      </Card>

      <Row gutter={[16, 16]}>
        <Col span={24}>
          <StepCard
            step={1}
            title="输入地址和范围"
            description="确认项目地址、城市和分析半径，这是后续采集和分析的基础。"
            icon={<EditOutlined />}
            actionText="编辑项目信息"
            onAction={placeholder}
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
            {collectResult && (
              <Alert style={{marginBottom: 12}} type="success" showIcon message="高德采集完成" description="已保存本次成功采集的数据。" />
            )}
            <Row gutter={16}>
              <Col span={6}><Statistic title="POI数量" value={countValue(collected.poi_count)} /></Col>
              <Col span={6}><Statistic title="竞品数量" value={countValue(collected.competitor_count)} /></Col>
              <Col span={6}><Statistic title="餐饮数量" value={countValue(collected.food_count)} /></Col>
              <Col span={6}><Statistic title="娱乐场所数量" value={countValue(collected.entertainment_count)} /></Col>
            </Row>
          </StepCard>
        </Col>

        <Col span={24}>
          <StepCard
            step={3}
            title="爬虫补充数据"
            description="后续根据高德识别到的竞品、餐饮、娱乐场所，补充价格、营业时间、配置等信息。"
            icon={<SearchOutlined />}
            actionText="启动爬虫补充"
            onAction={() => message.info('爬虫补充当前仅为占位，尚未接入')}
          >
            <Tag>当前状态：暂未启动</Tag>
          </StepCard>
        </Col>

        <Col span={24}>
          <StepCard
            step={4}
            title="人工补充数据"
            description="补充高德和爬虫无法获取的数据，例如竞品价格、机器配置、上座率、租金、物业费、转让费。"
            icon={<FormOutlined />}
            actionText="进入人工补充"
            onAction={() => navigate(`/projects/${projectId}/supplement`)}
          />
        </Col>

        <Col span={24}>
          <StepCard
            step={5}
            title="数据核验"
            description="检查数据完整度，判断是否可以生成报告。"
            icon={<SafetyCertificateOutlined />}
            actionText={checkingQuality ? '正在检查数据完整度...' : '检查数据完整度'}
            actionLoading={checkingQuality}
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
                <Statistic title="数据完整度" value="--" />
                <Tag>缺失字段：暂未检查</Tag>
              </Space>
            )}

            {qualityResult && (
              <Space direction="vertical" size={12} style={{width: '100%'}}>
                <Card size="small" title="数据完整度">
                  <Progress
                    percent={qualityScore}
                    status={qualityScore >= 80 ? 'success' : 'normal'}
                    strokeColor={qualityScore >= 80 ? '#389e0d' : '#d48806'}
                  />
                </Card>

                <Row gutter={12}>
                  <Col xs={24} md={12}>
                    <Card size="small" title={`缺失数据（${missingItems.length}项）`}>
                      {missingItems.length > 0 ? (
                        <List size="small" dataSource={missingItems} renderItem={item => <List.Item>{item}</List.Item>} />
                      ) : (
                        <Typography.Text type="secondary">未发现明显缺失数据</Typography.Text>
                      )}
                    </Card>
                  </Col>
                  <Col xs={24} md={12}>
                    <Card size="small" title={`风险提示（${warningItems.length}项）`}>
                      {warningItems.length > 0 ? (
                        <List size="small" dataSource={warningItems} renderItem={item => <List.Item>{item}</List.Item>} />
                      ) : (
                        <Typography.Text type="secondary">当前没有额外风险提示</Typography.Text>
                      )}
                    </Card>
                  </Col>
                </Row>

                <Card size="small" title="竞品详情完整度">
                  <Typography.Paragraph>
                    已确认 {Number(competitorDetailQuality?.confirmed_competitors) || 0} 个竞品，
                    其中 {Number(competitorDetailQuality?.incomplete_competitors) || 0} 个缺少经营信息。
                  </Typography.Paragraph>

                  {competitorMissingSummary.length > 0 ? (
                    <List
                      size="small"
                      header={<Typography.Text strong>缺失较多的字段</Typography.Text>}
                      dataSource={competitorMissingSummary}
                      renderItem={(item: any) => (
                        <List.Item>
                          <Space wrap>
                            <Tag color={item?.importance === 'important' ? 'red' : 'blue'}>
                              {item?.importance === 'important' ? '关键' : '建议'}
                            </Tag>
                            <Typography.Text>{safeText(item?.label)}：{Number(item?.missing_count) || 0} 家未填写</Typography.Text>
                          </Space>
                        </List.Item>
                      )}
                    />
                  ) : (
                    <Typography.Text type="secondary">
                      {Number(competitorDetailQuality?.confirmed_competitors) > 0
                        ? '已确认竞品的重要经营信息基本完整。'
                        : '尚无已确认竞品，确认后系统将检查其经营信息完整度。'}
                    </Typography.Text>
                  )}

                  {incompleteCompetitors.length > 0 && (
                    <List
                      size="small"
                      header={<Typography.Text strong>需要继续补充的竞品</Typography.Text>}
                      dataSource={incompleteCompetitors}
                      renderItem={(item: any) => (
                        <List.Item
                          actions={[
                            <Button
                              key="continue"
                              size="small"
                              onClick={() => locateCompetitorDetail(Number(item?.competitor_id))}
                            >
                              继续补充
                            </Button>,
                          ]}
                        >
                          <List.Item.Meta
                            title={safeText(item?.name)}
                            description={`缺少：${stringList(item?.missing_fields).join('、') || '经营信息'}`}
                          />
                        </List.Item>
                      )}
                    />
                  )}

                  {incompleteCompetitors.length > 0 && (
                    <Alert
                      type="warning"
                      showIcon
                      style={{marginTop: 12}}
                      message="建议补充竞品经营信息后再生成 AI 报告，以提高分析准确度。"
                    />
                  )}
                </Card>

                <Card size="small" title="周边配套完整度">
                  <Typography.Paragraph>
                    周边已确认 {Number(supportingDetailQuality?.total_confirmed) || 0} 家商户，
                    已完整补充 {Number(supportingDetailQuality?.completed) || 0} 家，
                    其中 {Number(supportingDetailQuality?.incomplete) || 0} 家缺少营业详情。
                  </Typography.Paragraph>

                  {supportingMissingSummary.length > 0 ? (
                    <List
                      size="small"
                      header={<Typography.Text strong>缺失字段汇总</Typography.Text>}
                      dataSource={supportingMissingSummary}
                      renderItem={(item: any) => (
                        <List.Item>
                          <Typography.Text>{safeText(item?.label)}：{Number(item?.missing_count) || 0} 家未填写</Typography.Text>
                        </List.Item>
                      )}
                    />
                  ) : (
                    <Typography.Text type="secondary">
                      {Number(supportingDetailQuality?.total_confirmed) > 0
                        ? '已确认配套的关键营业详情基本完整。'
                        : '尚无已确认配套，确认后系统将检查营业详情完整度。'}
                    </Typography.Text>
                  )}

                  {incompleteSupportingItems.length > 0 && (
                    <List
                      size="small"
                      header={<Typography.Text strong>需要继续补充的周边配套</Typography.Text>}
                      dataSource={incompleteSupportingItems}
                      renderItem={(item: any) => (
                        <List.Item
                          actions={[
                            <Button
                              key="continue"
                              size="small"
                              onClick={() => locateSupportingDetail(String(item?.id || ''))}
                            >
                              继续补充
                            </Button>,
                          ]}
                        >
                          <List.Item.Meta
                            title={safeText(item?.name)}
                            description={`缺少：${stringList(item?.missing_fields).join('、') || '营业详情'}`}
                          />
                        </List.Item>
                      )}
                    />
                  )}

                  {incompleteSupportingItems.length > 0 && (
                    <Alert
                      type="warning"
                      showIcon
                      style={{marginTop: 12}}
                      message="建议核实营业时间和夜间经营状态后再进行后续分析。"
                    />
                  )}
                </Card>

                <Card size="small" title="租金数据完整度">
                  <Typography.Paragraph>
                    已确认 {Number(rentQuality?.total_confirmed) || 0} 条租金，
                    详情完整 {Number(rentQuality?.detail_completed) || 0} 条，
                    其中 {Number(rentQuality?.incomplete) || 0} 条仍需补充。
                  </Typography.Paragraph>

                  {rentMissingSummary.length > 0 ? (
                    <List
                      size="small"
                      header={<Typography.Text strong>缺失字段汇总</Typography.Text>}
                      dataSource={rentMissingSummary}
                      renderItem={(item: any) => (
                        <List.Item>
                          <Space wrap>
                            <Tag color={item?.importance === 'core' ? 'red' : 'blue'}>
                              {item?.importance === 'core' ? '核心' : '建议'}
                            </Tag>
                            <Typography.Text>
                              {safeText(item?.label)}：{Number(item?.missing_count) || 0} 条未填写
                            </Typography.Text>
                          </Space>
                        </List.Item>
                      )}
                    />
                  ) : (
                    <Typography.Text type="secondary">
                      {Number(rentQuality?.total_confirmed) > 0
                        ? '已确认租金的核心字段和建议详情基本完整。'
                        : '尚无已确认租金，确认后系统将检查租金数据完整度。'}
                    </Typography.Text>
                  )}

                  {incompleteRentItems.length > 0 && (
                    <List
                      size="small"
                      header={<Typography.Text strong>需要继续补充的租金记录</Typography.Text>}
                      dataSource={incompleteRentItems}
                      renderItem={(item: any) => (
                        <List.Item
                          actions={[
                            <Button
                              key="continue"
                              size="small"
                              onClick={() => locateRentDetail(Number(item?.rent_id))}
                            >
                              继续补充
                            </Button>,
                          ]}
                        >
                          <List.Item.Meta
                            title={safeText(item?.address)}
                            description={`缺少：${stringList(item?.missing_fields).join('、') || '租金详情'}`}
                          />
                        </List.Item>
                      )}
                    />
                  )}

                  {incompleteRentItems.length > 0 && (
                    <Alert
                      type="warning"
                      showIcon
                      style={{marginTop: 12}}
                      message="建议核实租金地址、面积、月租金及物业来源信息后再进行成本分析。"
                    />
                  )}
                </Card>

                <Alert
                  type={qualityScore >= 80 ? 'success' : 'warning'}
                  showIcon
                  message={qualityScore >= 80
                    ? '数据基本完整，可以进入 AI 报告生成。'
                    : '建议补充缺失数据后再生成报告。'}
                />
              </Space>
            )}

            <Typography.Paragraph type="secondary" style={{marginTop: 12, marginBottom: 0}}>
              当前人工补充数据为本地暂存，后续阶段将接入后端保存后参与核验。
            </Typography.Paragraph>
          </StepCard>
        </Col>

        <Col span={24}>
          <StepCard
            step={6}
            title="评分分析 → AI报告"
            description="先根据现有项目数据生成结构化评分，再进入 AI 报告生成。"
            icon={<RobotOutlined />}
            actionText={scoring ? '正在分析选址条件...' : '开始评分分析'}
            actionLoading={scoring}
            actionFirst
            onAction={runScoring}
          >
            <Typography.Title level={5}>第一阶段：评分分析</Typography.Title>

            {scoreError && (
              <Alert
                type="error"
                showIcon
                style={{marginBottom: 12}}
                message="评分分析失败"
                description={scoreError}
              />
            )}

            {!scoreResult && !scoreError && (
              <Typography.Text type="secondary">尚未评分，请先完成数据核验后开始评分分析。</Typography.Text>
            )}

            {scoreResult && (
              <Space direction="vertical" size={12} style={{width: '100%'}}>
                <Row gutter={12}>
                  <Col xs={24} md={8}>
                    <Card size="small"><Statistic title="综合评分" value={scoreResult.total_score ?? '--'} suffix="分" /></Card>
                  </Col>
                  <Col xs={24} md={8}>
                    <Card size="small"><Statistic title="评级" value={safeText(scoreResult.level, '暂未评级')} /></Card>
                  </Col>
                  <Col xs={24} md={8}>
                    <Card size="small"><Statistic title="评分维度" value={dimensionEntries.length} suffix="项" /></Card>
                  </Col>
                </Row>

                {dimensionEntries.length > 0 && (
                  <Row gutter={[12, 12]}>
                    {dimensionEntries.map(([key, value]) => (
                      <Col xs={24} md={12} lg={8} key={key}>
                        <Card size="small" title={DIMENSION_TEXT[key] || key}>
                          <Statistic value={value?.score ?? '--'} suffix={value?.max !== undefined ? `/ ${value.max} 分` : '分'} />
                          {key === 'competitor' && (
                            <Descriptions column={1} size="small" style={{marginTop: 12}}>
                              <Descriptions.Item label="竞争强度">
                                {competitionLevelText[competitorAnalysis.competition_level] || '数据不足'}
                              </Descriptions.Item>
                              <Descriptions.Item label="已确认竞品">
                                {competitorAnalysis.confirmed_competitor_count ?? 0} 家
                              </Descriptions.Item>
                              <Descriptions.Item label="待核实竞品">
                                {competitorAnalysis.pending_review_count ?? 0} 家
                              </Descriptions.Item>
                              <Descriptions.Item label="平均距离">
                                {competitorAnalysis.average_distance == null
                                  ? '未采集'
                                  : `${competitorAnalysis.average_distance} 米`}
                              </Descriptions.Item>
                              <Descriptions.Item label="平均价格">
                                {competitorAnalysis.average_hour_price == null
                                  ? '经营信息不足'
                                  : `${competitorAnalysis.average_hour_price} 元/小时`}
                              </Descriptions.Item>
                              <Descriptions.Item label="平均上座率">
                                {competitorAnalysis.average_occupancy_rate == null
                                  ? '经营信息不足'
                                  : `${Math.round(Number(competitorAnalysis.average_occupancy_rate) * 100)}%`}
                              </Descriptions.Item>
                              <Descriptions.Item label="平均机器数量">
                                {competitorAnalysis.average_machine_count == null
                                  ? '经营信息不足'
                                  : `${competitorAnalysis.average_machine_count} 台`}
                              </Descriptions.Item>
                              <Descriptions.Item label="常见显卡">
                                {competitorAnalysis.common_gpu || '经营信息不足'}
                              </Descriptions.Item>
                            </Descriptions>
                          )}
                          {key === 'support' && (
                            <>
                              <Descriptions column={1} size="small" style={{marginTop: 12}}>
                                <Descriptions.Item label="已确认餐饮">
                                  {supportingAnalysis.food_count ?? 0} 家
                                </Descriptions.Item>
                                <Descriptions.Item label="夜间营业餐饮">
                                  {supportingAnalysis.night_food_count ?? 0} 家
                                </Descriptions.Item>
                                <Descriptions.Item label="已确认娱乐">
                                  {supportingAnalysis.entertainment_count ?? 0} 家
                                </Descriptions.Item>
                                <Descriptions.Item label="已核实夜间商业">
                                  {supportingAnalysis.night_business_count ?? 0} 家
                                </Descriptions.Item>
                                <Descriptions.Item label="夜间活跃度">
                                  {nightActivityLevelText[supportingAnalysis.night_activity_level] || '数据不足'}
                                </Descriptions.Item>
                                <Descriptions.Item label="详情完整度">
                                  {supportingAnalysis.detail_completeness == null
                                    ? '未检查'
                                    : `${Math.round(Number(supportingAnalysis.detail_completeness) * 100)}%`}
                                </Descriptions.Item>
                              </Descriptions>
                              {Number(supportingAnalysis.detail_completeness ?? 0) < 0.5 && (
                                <Tag color="orange">夜间经营信息不足</Tag>
                              )}
                            </>
                          )}
                          {key === 'rent' && (
                            <Descriptions column={1} size="small" style={{marginTop: 12}}>
                              <Descriptions.Item label="有效租金样本">
                                {rentAnalysis.confirmed_rent_count ?? 0} 条
                              </Descriptions.Item>
                              <Descriptions.Item label="平均面积">
                                {rentAnalysis.average_area_sqm == null
                                  ? '数据不足'
                                  : `${rentAnalysis.average_area_sqm} ㎡`}
                              </Descriptions.Item>
                              <Descriptions.Item label="平均月租">
                                {rentAnalysis.average_monthly_rent == null
                                  ? '数据不足'
                                  : `${rentAnalysis.average_monthly_rent} 元/月`}
                              </Descriptions.Item>
                              <Descriptions.Item label="平均单价">
                                {rentAnalysis.average_rent_unit_price == null
                                  ? '数据不足'
                                  : `${rentAnalysis.average_rent_unit_price} 元/㎡/月`}
                              </Descriptions.Item>
                              <Descriptions.Item label="租金压力">
                                {rentPressureText[rentAnalysis.rent_pressure] || '数据不足'}
                              </Descriptions.Item>
                              <Descriptions.Item label="核心数据完整度">
                                {rentAnalysis.data_completeness == null
                                  ? '未检查'
                                  : `${Math.round(Number(rentAnalysis.data_completeness) * 100)}%`}
                              </Descriptions.Item>
                            </Descriptions>
                          )}
                          {stringList(value?.reasons).length > 0 && (
                            <List
                              size="small"
                              header={<Typography.Text strong>评分原因</Typography.Text>}
                              dataSource={stringList(value.reasons)}
                              renderItem={item => <List.Item>{item}</List.Item>}
                            />
                          )}
                        </Card>
                      </Col>
                    ))}
                  </Row>
                )}

                <Row gutter={12}>
                  <Col xs={24} md={8}>
                    <Card size="small" title="主要优势">
                      {scoreAdvantages.length > 0
                        ? <List size="small" dataSource={scoreAdvantages} renderItem={item => <List.Item>{item}</List.Item>} />
                        : <Typography.Text type="secondary">暂无明确优势项</Typography.Text>}
                    </Card>
                  </Col>
                  <Col xs={24} md={8}>
                    <Card size="small" title="风险提示">
                      {scoreRisks.length > 0
                        ? <List size="small" dataSource={scoreRisks} renderItem={item => <List.Item>{item}</List.Item>} />
                        : <Typography.Text type="secondary">暂无额外风险提示</Typography.Text>}
                    </Card>
                  </Col>
                  <Col xs={24} md={8}>
                    <Card size="small" title="建议补充">
                      {scoreMissing.length > 0
                        ? <List size="small" dataSource={scoreMissing} renderItem={item => <List.Item>{item}</List.Item>} />
                        : <Typography.Text type="secondary">当前没有评分所需的缺失项</Typography.Text>}
                    </Card>
                  </Col>
                </Row>
              </Space>
            )}

            <Divider />
            <Typography.Title level={5}>第二阶段：AI报告生成</Typography.Title>
            <Space direction="vertical" size={12} style={{width: '100%'}}>
              <Space wrap>
                <FileTextOutlined />
                <Typography.Text type="secondary">
                  {scoreResult ? '评分已完成，可以生成 AI 选址分析报告。' : '请先完成评分分析，再生成 AI 报告。'}
                </Typography.Text>
                <Button
                  type="primary"
                  disabled={!scoreResult}
                  loading={generatingReport}
                  icon={<CheckCircleOutlined />}
                  onClick={runReportGeneration}
                >
                  {generatingReport ? '正在生成选址分析报告...' : '生成 AI 报告'}
                </Button>
              </Space>

              {reportError && (
                <Alert type="error" showIcon message="报告生成失败" description={reportError} />
              )}

              {reportResult?.content && (
                <Card title="电竞馆选址分析报告" className="ai-report-card">
                  <MarkdownReport content={reportResult.content} />
                </Card>
              )}
            </Space>
          </StepCard>
        </Col>

        <Col span={24}>
          <ProjectAssistant projectId={projectId} />
        </Col>
      </Row>
    </div>
  );
}
