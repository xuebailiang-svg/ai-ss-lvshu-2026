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
  Progress,
  Row,
  Space,
  Statistic,
  Tag,
  Typography,
  message,
} from 'antd';
import {
  CloudDownloadOutlined,
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

type ProjectItem = {
  project_id: string;
  name?: string;
  project_name?: string;
  city?: string;
  address?: string;
  radius_meters?: number;
  business_type?: string;
  status?: string;
  stats?: Record<string, unknown>;
};

type ChatMessage = {
  role: 'user' | 'assistant' | 'system';
  content: string;
};

const QUICK_MESSAGES = [
  '西安市 小寨地铁站 1000米 电竞馆，帮我做一次选址分析',
  '这个项目当前缺哪些关键数据？',
  '竞品压力和夜间消费环境怎么样？',
  '生成一份适合投资人看的报告',
];

function projectTitle(project?: ProjectItem | null) {
  if (!project) return '未选择项目';
  return project.name || project.project_name || project.address || project.project_id;
}

function statusText(status?: string) {
  const map: Record<string, string> = {
    pending_review: '初始化',
    confirmed: '初始化',
    collecting: '数据采集中',
    supplementing: '数据补充中',
    scored: '分析完成',
    reported: '已生成报告',
  };
  return map[status || ''] || '初始化';
}

function errorText(error: any, fallback: string) {
  const detail = error?.response?.data?.detail;
  if (typeof detail === 'string') return detail;
  if (detail?.message) return detail.message;
  return error?.message || fallback;
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
  const [projectForm] = Form.useForm<ProjectCreatePayload>();
  const [projects, setProjects] = useState<ProjectItem[]>([]);
  const [selectedProjectId, setSelectedProjectId] = useState('');
  const [creating, setCreating] = useState(false);
  const [loadingProjects, setLoadingProjects] = useState(false);
  const [actionLoading, setActionLoading] = useState('');
  const [quality, setQuality] = useState<any>(null);
  const [score, setScore] = useState<any>(null);
  const [report, setReport] = useState<any>(null);
  const [dataSources, setDataSources] = useState<DataSourceStatus[]>([]);
  const [dimensions, setDimensions] = useState<ScoringDimensionConfig[]>([]);
  const [memories, setMemories] = useState<MemoryItem[]>([]);
  const [sessionId, setSessionId] = useState('');
  const [chatInput, setChatInput] = useState('');
  const [messages, setMessages] = useState<ChatMessage[]>([
    {role: 'system', content: '这是面向客户的工作台。可以直接创建项目、采集数据、补充信息、评分、生成报告，也可以围绕当前项目提问。'},
  ]);

  const selectedProject = useMemo(
    () => projects.find(item => item.project_id === selectedProjectId) || null,
    [projects, selectedProjectId],
  );

  const loadProjects = async () => {
    setLoadingProjects(true);
    try {
      const result = await listProjects();
      const items = Array.isArray(result?.items) ? result.items : [];
      setProjects(items);
      if (!selectedProjectId && items[0]) setSelectedProjectId(items[0].project_id);
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
        projectId ? listMemory({project_id: projectId, status: 'confirmed'}).catch(() => ({items: [], total: 0})) : Promise.resolve({items: [], total: 0}),
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
    setScore(null);
    setReport(null);
    setSessionId('');
    void loadSideContext(selectedProjectId);
    createProjectChatSession(selectedProjectId)
      .then(result => setSessionId(String(result.session_id)))
      .catch(() => setSessionId(''));
  }, [selectedProjectId]);

  const createNewProject = async (values: ProjectCreatePayload) => {
    setCreating(true);
    try {
      const result = await createProject(values);
      await loadProjects();
      setSelectedProjectId(result.project_id);
      setMessages(previous => [...previous, {role: 'system', content: `已创建项目：${values.name || values.address}`}]);
      projectForm.resetFields();
    } catch (error: any) {
      message.error(errorText(error, '创建项目失败'));
    } finally {
      setCreating(false);
    }
  };

  const runAction = async (name: string, fn: () => Promise<any>, successMessage: string) => {
    if (!selectedProjectId) {
      message.warning('请先选择或创建项目');
      return;
    }
    setActionLoading(name);
    try {
      const result = await fn();
      message.success(successMessage);
      setMessages(previous => [...previous, {role: 'system', content: `${successMessage}：${JSON.stringify(result).slice(0, 180)}`}]);
      await loadProjects();
      await loadSideContext(selectedProjectId);
      return result;
    } catch (error: any) {
      const reason = errorText(error, `${successMessage}失败`);
      setMessages(previous => [...previous, {role: 'system', content: `操作失败：${reason}`}]);
      message.error(reason);
      return null;
    } finally {
      setActionLoading('');
    }
  };

  const checkQuality = async () => {
    const result = await runAction('quality', () => getProjectDataQuality(selectedProjectId), '数据核验完成');
    if (result) setQuality(result);
  };

  const runScore = async () => {
    const result = await runAction('score', () => scoreProject(selectedProjectId), '评分分析完成');
    if (result) setScore(result);
  };

  const runReport = async () => {
    const result = await runAction('report', () => generateAiReport(selectedProjectId), 'AI 报告生成完成');
    if (result?.success === false) {
      message.warning(result.message || 'AI 报告生成失败');
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

  return (
    <div className="v11-workbench">
      <aside className="v11-left-panel">
        <Card title="项目" extra={<Button size="small" icon={<ReloadOutlined />} onClick={loadProjects} loading={loadingProjects}>刷新</Button>}>
          <List
            size="small"
            dataSource={projects}
            locale={{emptyText: '暂无项目，请先新建'}}
            renderItem={item => (
              <List.Item
                className={item.project_id === selectedProjectId ? 'v11-project-item active' : 'v11-project-item'}
                onClick={() => setSelectedProjectId(item.project_id)}
              >
                <List.Item.Meta
                  title={projectTitle(item)}
                  description={`${item.city || '-'} · ${item.address || '-'} · ${statusText(item.status)}`}
                />
              </List.Item>
            )}
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
              <Col span={12}><Form.Item name="district" label="区域"><Input /></Form.Item></Col>
            </Row>
            <Form.Item name="address" label="详细地址" rules={[{required: true, message: '请输入地址'}]}>
              <Input placeholder="例如：小寨地铁站" />
            </Form.Item>
            <Row gutter={8}>
              <Col span={12}><Form.Item name="radius_meters" label="分析范围"><InputNumber min={200} max={5000} style={{width: '100%'}} /></Form.Item></Col>
              <Col span={12}><Form.Item name="business_type" label="经营类型"><Input /></Form.Item></Col>
            </Row>
            <Row gutter={8}>
              <Col span={12}><Form.Item name="expected_area_sqm" label="预计面积"><InputNumber min={0} style={{width: '100%'}} /></Form.Item></Col>
              <Col span={12}><Form.Item name="investment_budget" label="投资预算"><InputNumber min={0} style={{width: '100%'}} /></Form.Item></Col>
            </Row>
            <Button type="primary" icon={<PlusOutlined />} htmlType="submit" loading={creating} block>创建项目</Button>
          </Form>
        </Card>
      </aside>

      <main className="v11-center-panel">
        <Card className="v11-project-header">
          <Space direction="vertical" size={4}>
            <Typography.Title level={3} style={{margin: 0}}>{projectTitle(selectedProject)}</Typography.Title>
            <Typography.Text type="secondary">
              {selectedProject ? `${selectedProject.city || '-'} · ${selectedProject.address || '-'} · ${selectedProject.radius_meters || 1000}米 · ${selectedProject.business_type || '电竞馆'}` : '选择项目后开始分析'}
            </Typography.Text>
          </Space>
        </Card>

        <Card title="选址操作" className="v11-action-card">
          <Space wrap>
            <Button icon={<CloudDownloadOutlined />} loading={actionLoading === 'amap'} onClick={() => runAction('amap', () => collectProjectAmap(selectedProjectId), '高德 POI 采集完成')}>采集高德 POI</Button>
            <Button loading={actionLoading === 'competitor'} onClick={() => runAction('competitor', () => collectProjectCompetitors(selectedProjectId), '竞品采集完成')}>获取竞品</Button>
            <Button loading={actionLoading === 'supporting'} onClick={() => runAction('supporting', () => collectProjectSupporting(selectedProjectId), '周边配套采集完成')}>获取配套</Button>
            <Button loading={actionLoading === 'quality'} onClick={checkQuality}>数据核验</Button>
            <Button type="primary" loading={actionLoading === 'score'} onClick={runScore}>评分分析</Button>
            <Button icon={<FileTextOutlined />} loading={actionLoading === 'report'} onClick={runReport}>生成报告</Button>
          </Space>
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

        {(quality || score || reportContent) && (
          <Card title="分析结果与报告" className="v11-result-card">
            <Row gutter={[12, 12]}>
              {quality && (
                <Col xs={24} md={8}>
                  <Card size="small">
                    <Statistic title="数据完整度" value={qualityScore} suffix="%" />
                    <Progress percent={qualityScore} status={qualityScore >= 80 ? 'success' : 'active'} />
                    <Typography.Text type="secondary">缺失：{Array.isArray(quality.missing) ? quality.missing.length : 0} 项</Typography.Text>
                  </Card>
                </Col>
              )}
              {score && (
                <Col xs={24} md={8}>
                  <Card size="small">
                    <Statistic title="综合评分" value={score.total_score ?? '--'} suffix="分" />
                    <Typography.Text>等级：{score.level || '-'}</Typography.Text>
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
                  <Typography.Text type="secondary">{item.capabilities.join('、') || item.description}</Typography.Text>
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
