import {useEffect, useMemo, useState} from 'react';
import {
  Alert,
  Button,
  Card,
  Col,
  Form,
  Input,
  InputNumber,
  List,
  Row,
  Space,
  Switch,
  Tag,
  Typography,
  message,
} from 'antd';
import {CheckCircleOutlined, ReloadOutlined, SaveOutlined} from '@ant-design/icons';
import {
  getManagedSystemConfig,
  testManagedSystemConfig,
  updateManagedSystemConfig,
} from '../api/client';
import {
  checkDataSourceConnectivity,
  getDataSourceStatus,
  type ConnectivityCheck,
  type DataSourceStatus,
} from '../api/dataSources';
import {
  getScoringConfig,
  resetScoringConfig,
  updateScoringConfig,
  type ScoringDimensionConfig,
} from '../api/scoringConfig';
import {
  createMemory,
  listMemory,
  reviewMemory,
  type MemoryItem,
  type MemoryStatus,
} from '../api/memory';

function statusTag(configured?: boolean, text?: string) {
  return configured ? <Tag color="green">{text || '已配置'}</Tag> : <Tag color="red">{text || '未配置'}</Tag>;
}

function providerStatusText(status: string) {
  if (status === 'available') return '可用';
  if (status === 'disabled') return '已停用';
  if (status === 'not_configured') return '未配置';
  return status;
}

export default function SystemConfig() {
  const [token, setToken] = useState('');
  const [configForm] = Form.useForm();
  const [memoryForm] = Form.useForm();
  const [managedConfig, setManagedConfig] = useState<any>(null);
  const [dataSources, setDataSources] = useState<DataSourceStatus[]>([]);
  const [checks, setChecks] = useState<Record<string, ConnectivityCheck | 'loading' | 'failed'>>({});
  const [dimensions, setDimensions] = useState<ScoringDimensionConfig[]>([]);
  const [memories, setMemories] = useState<MemoryItem[]>([]);
  const [savingConfig, setSavingConfig] = useState(false);
  const [savingDimensions, setSavingDimensions] = useState(false);

  const totalWeight = useMemo(
    () => dimensions.filter(item => item.enabled).reduce((sum, item) => sum + Number(item.weight || 0), 0),
    [dimensions],
  );

  const loadAll = async () => {
    const [config, sources, scoring, memory] = await Promise.all([
      getManagedSystemConfig().catch(() => null),
      getDataSourceStatus().catch(() => ({items: []})),
      getScoringConfig().catch(() => ({dimensions: [], total_weight: 0, normalized: false})),
      listMemory().catch(() => ({items: [], total: 0})),
    ]);
    setManagedConfig(config);
    setDataSources(sources.items || []);
    setDimensions(scoring.dimensions || []);
    setMemories(memory.items || []);
    configForm.setFieldsValue({
      deepseek_base_url: config?.deepseek_base_url || 'https://api.deepseek.com',
      deepseek_model: config?.deepseek_model || 'deepseek-chat',
    });
  };

  useEffect(() => {
    loadAll().catch(error => message.error(error.message || '配置加载失败'));
  }, []);

  const saveConfigPatch = async (patch: Record<string, string | undefined>) => {
    if (!token.trim()) {
      message.warning('请先输入 ADMIN_CONFIG_TOKEN');
      return;
    }
    const payload: Record<string, string> = Object.fromEntries(
      Object.entries(patch).filter(([, value]) => typeof value === 'string' && value.trim()),
    ) as Record<string, string>;
    if (!Object.keys(payload).length) return;
    setSavingConfig(true);
    try {
      const result = await updateManagedSystemConfig(payload, token.trim());
      setManagedConfig(result);
      configForm.setFieldsValue({
        deepseek_api_key: undefined,
        amap_web_service_key: undefined,
        amap_js_key: undefined,
        amap_security_js_code: undefined,
        third_party_api_key: undefined,
      });
      message.success('配置已加密保存');
    } catch (error: any) {
      message.error(error?.response?.data?.detail || error.message || '配置保存失败');
    } finally {
      setSavingConfig(false);
    }
  };

  const testManagedProvider = async (provider: 'deepseek' | 'amap') => {
    if (!token.trim()) {
      message.warning('请先输入 ADMIN_CONFIG_TOKEN');
      return;
    }
    setChecks(previous => ({...previous, [provider]: 'loading'}));
    try {
      const result = await testManagedSystemConfig(provider, token.trim());
      setChecks(previous => ({...previous, [provider]: result}));
      message.success(result.message);
    } catch (error: any) {
      setChecks(previous => ({...previous, [provider]: 'failed'}));
      message.error(error?.response?.data?.detail || error.message || '连接测试失败');
    }
  };

  const testDataSource = async (name: string) => {
    setChecks(previous => ({...previous, [name]: 'loading'}));
    try {
      const result = await checkDataSourceConnectivity(name);
      setChecks(previous => ({...previous, [name]: result}));
    } catch {
      setChecks(previous => ({...previous, [name]: 'failed'}));
    }
  };

  const updateDimension = (index: number, patch: Partial<ScoringDimensionConfig>) => {
    setDimensions(previous => previous.map((item, itemIndex) => itemIndex === index ? {...item, ...patch} : item));
  };

  const saveDimensions = async () => {
    setSavingDimensions(true);
    try {
      const result = await updateScoringConfig(dimensions);
      setDimensions(result.dimensions);
      message.success('评分维度和权重已保存');
    } catch (error: any) {
      message.error(error?.response?.data?.detail || error.message || '评分配置保存失败');
    } finally {
      setSavingDimensions(false);
    }
  };

  const resetDimensions = async () => {
    setSavingDimensions(true);
    try {
      const result = await resetScoringConfig();
      setDimensions(result.dimensions);
      message.success('已恢复默认评分维度');
    } finally {
      setSavingDimensions(false);
    }
  };

  const submitMemory = async (values: any) => {
    try {
      await createMemory({
        ...values,
        tags: String(values.tags || '').split(/[,\s，、]+/).filter(Boolean),
        status: 'pending_review',
        confidence: Number(values.confidence ?? 0.7),
      });
      memoryForm.resetFields();
      const result = await listMemory();
      setMemories(result.items);
      message.success('记忆已创建，默认待确认');
    } catch (error: any) {
      message.error(error?.response?.data?.detail || error.message || '记忆保存失败');
    }
  };

  const changeMemoryStatus = async (memoryId: number, status: MemoryStatus) => {
    await reviewMemory(memoryId, status);
    const result = await listMemory();
    setMemories(result.items);
  };

  return (
    <div className="v11-config-page">
      <div className="v11-page-heading">
        <div>
          <Typography.Title level={2}>配置</Typography.Title>
          <Typography.Paragraph type="secondary">
            集中管理 Key、模型、数据源、评分维度、权重和 memory。敏感 Key 加密保存，不回显完整值。
          </Typography.Paragraph>
        </div>
        <Button icon={<ReloadOutlined />} onClick={() => loadAll()}>刷新</Button>
      </div>

      <Card title="管理员验证">
        <Input.Password
          value={token}
          onChange={event => setToken(event.target.value)}
          placeholder="请输入 ADMIN_CONFIG_TOKEN"
          autoComplete="off"
        />
        <Typography.Paragraph type="secondary" style={{marginTop: 8}}>
          Token 只保存在当前浏览器内存中，用于保存配置和测试连接。
        </Typography.Paragraph>
      </Card>

      <Card title="Key 和模型配置">
        <Form form={configForm} layout="vertical">
          <Row gutter={16}>
            <Col xs={24} md={12}>
              <Card size="small" title="DeepSeek">
                <Space direction="vertical" style={{width: '100%'}}>
                  <Space>{statusTag(managedConfig?.deepseek?.configured)}<span>{managedConfig?.deepseek?.masked || ''}</span></Space>
                  <Form.Item name="deepseek_base_url" label="API 地址">
                    <Input onBlur={event => saveConfigPatch({deepseek_base_url: event.target.value})} />
                  </Form.Item>
                  <Form.Item name="deepseek_model" label="模型">
                    <Input onBlur={event => saveConfigPatch({deepseek_model: event.target.value})} />
                  </Form.Item>
                  <Form.Item name="deepseek_api_key" label="DeepSeek API Key">
                    <Input.Password onBlur={event => saveConfigPatch({deepseek_api_key: event.target.value})} placeholder="输入后自动加密保存" />
                  </Form.Item>
                  <Button onClick={() => testManagedProvider('deepseek')} loading={checks.deepseek === 'loading'}>测试 DeepSeek</Button>
                </Space>
              </Card>
            </Col>
            <Col xs={24} md={12}>
              <Card size="small" title="高德地图">
                <Space direction="vertical" style={{width: '100%'}}>
                  <Space>Web Service：{statusTag(managedConfig?.amap?.configured)} {managedConfig?.amap?.masked || ''}</Space>
                  <Space>JS Key：{statusTag(managedConfig?.amap_js?.configured)} {managedConfig?.amap_js?.masked || ''}</Space>
                  <Form.Item name="amap_web_service_key" label="高德 Web Service Key">
                    <Input.Password onBlur={event => saveConfigPatch({amap_web_service_key: event.target.value})} placeholder="输入后自动加密保存" />
                  </Form.Item>
                  <Form.Item name="amap_js_key" label="高德 JS Key">
                    <Input.Password onBlur={event => saveConfigPatch({amap_js_key: event.target.value})} placeholder="输入后自动加密保存" />
                  </Form.Item>
                  <Form.Item name="amap_security_js_code" label="高德安全密钥">
                    <Input.Password onBlur={event => saveConfigPatch({amap_security_js_code: event.target.value})} placeholder="输入后自动加密保存" />
                  </Form.Item>
                  <Button onClick={() => testManagedProvider('amap')} loading={checks.amap === 'loading'}>测试高德</Button>
                </Space>
              </Card>
            </Col>
            <Col span={24}>
              <Card size="small" title="后续第三方平台 Key">
                <Form.Item name="third_party_api_key" label="第三方平台 Key">
                  <Input.Password onBlur={event => saveConfigPatch({third_party_api_key: event.target.value})} placeholder="预留：美团/消费数据等第三方平台" />
                </Form.Item>
              </Card>
            </Col>
          </Row>
        </Form>
        {savingConfig && <Alert style={{marginTop: 12}} type="info" showIcon message="正在保存配置..." />}
      </Card>

      <Card title="评分维度和权重">
        <Alert
          type={Math.abs(totalWeight - 100) < 0.01 ? 'success' : 'warning'}
          showIcon
          message={`当前启用维度权重合计：${totalWeight.toFixed(2)}`}
          description="建议合计为 100。系统会把这些业务维度映射到现有评分引擎，后续可逐步细化到每个维度独立评分。"
          style={{marginBottom: 12}}
        />
        <List
          dataSource={dimensions}
          renderItem={(item, index) => (
            <List.Item>
              <Row gutter={12} style={{width: '100%'}} align="middle">
                <Col xs={24} md={4}><Input value={item.name} onChange={event => updateDimension(index, {name: event.target.value})} /></Col>
                <Col xs={24} md={3}><InputNumber min={0} value={item.weight} onChange={value => updateDimension(index, {weight: Number(value || 0)})} style={{width: '100%'}} /></Col>
                <Col xs={24} md={3}><Switch checked={item.enabled} onChange={checked => updateDimension(index, {enabled: checked})} checkedChildren="启用" unCheckedChildren="停用" /></Col>
                <Col xs={24} md={6}><Input value={(item.data_sources || []).join(',')} onChange={event => updateDimension(index, {data_sources: event.target.value.split(',').map(v => v.trim()).filter(Boolean)})} /></Col>
                <Col xs={24} md={8}><Input value={item.description || ''} onChange={event => updateDimension(index, {description: event.target.value})} /></Col>
              </Row>
            </List.Item>
          )}
        />
        <Space>
          <Button type="primary" icon={<SaveOutlined />} loading={savingDimensions} onClick={saveDimensions}>保存维度配置</Button>
          <Button onClick={resetDimensions}>恢复默认</Button>
        </Space>
      </Card>

      <Card title="数据源">
        <List
          grid={{gutter: 12, xs: 1, md: 2, xl: 3}}
          dataSource={dataSources}
          renderItem={item => {
            const check = checks[item.name];
            const checkResult = typeof check === 'object' ? check : null;
            return (
              <List.Item>
                <Card size="small" title={item.display_name}>
                  <Space direction="vertical">
                    <Space>
                      <Tag color={item.status === 'available' ? 'green' : item.status === 'disabled' ? 'default' : 'orange'}>
                        {providerStatusText(item.status)}
                      </Tag>
                      <Tag>{(item.capabilities || []).join('、') || '基础能力'}</Tag>
                    </Space>
                    <Typography.Text type="secondary">{item.description}</Typography.Text>
                    <Button size="small" disabled={!item.check_supported} loading={check === 'loading'} onClick={() => testDataSource(item.name)}>检测连接</Button>
                    {check === 'failed' && <Typography.Text type="danger">检测失败，请稍后重试。</Typography.Text>}
                    {checkResult && (
                      <Typography.Text type={checkResult.reachable ? 'success' : 'danger'}>
                        {checkResult.message} · {checkResult.latency_ms}ms
                      </Typography.Text>
                    )}
                  </Space>
                </Card>
              </List.Item>
            );
          }}
        />
      </Card>

      <Card title="Memory 管理">
        <Row gutter={16}>
          <Col xs={24} md={9}>
            <Form
              form={memoryForm}
              layout="vertical"
              initialValues={{scope: 'global', memory_type: 'business_rule', source: 'manual', confidence: 0.8}}
              onFinish={submitMemory}
            >
              <Form.Item name="title" label="标题" rules={[{required: true}]}><Input /></Form.Item>
              <Form.Item name="content" label="内容" rules={[{required: true}]}><Input.TextArea rows={4} /></Form.Item>
              <Row gutter={8}>
                <Col span={12}><Form.Item name="scope" label="范围"><Input /></Form.Item></Col>
                <Col span={12}><Form.Item name="memory_type" label="类型"><Input /></Form.Item></Col>
              </Row>
              <Form.Item name="tags" label="标签"><Input placeholder="电竞馆、租金、夜经济" /></Form.Item>
              <Form.Item name="confidence" label="置信度"><InputNumber min={0} max={1} step={0.1} style={{width: '100%'}} /></Form.Item>
              <Button type="primary" htmlType="submit">新增待确认记忆</Button>
            </Form>
          </Col>
          <Col xs={24} md={15}>
            <List
              dataSource={memories}
              locale={{emptyText: '暂无 memory'}}
              renderItem={item => (
                <List.Item
                  actions={[
                    <Button key="confirm" size="small" icon={<CheckCircleOutlined />} onClick={() => changeMemoryStatus(item.id, 'confirmed')}>确认</Button>,
                    <Button key="disable" size="small" danger onClick={() => changeMemoryStatus(item.id, 'disabled')}>停用</Button>,
                  ]}
                >
                  <List.Item.Meta
                    title={<Space><span>{item.title}</span><Tag>{item.status}</Tag><Tag>{item.memory_type}</Tag></Space>}
                    description={<Typography.Paragraph ellipsis={{rows: 2}}>{item.content}</Typography.Paragraph>}
                  />
                </List.Item>
              )}
            />
          </Col>
        </Row>
      </Card>
    </div>
  );
}
