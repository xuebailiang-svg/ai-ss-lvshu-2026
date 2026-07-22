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
import {CheckCircleOutlined, PlusOutlined, ReloadOutlined, SaveOutlined} from '@ant-design/icons';
import {
  getManagedSystemConfig,
  testManagedSystemConfig,
  updateManagedSystemConfig,
  verifyManagedSystemConfigToken,
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
  type ScoringFactorConfig,
} from '../api/scoringConfig';
import {
  createMemory,
  listMemory,
  reviewMemory,
  type MemoryItem,
  type MemoryStatus,
} from '../api/memory';

type CheckState = ConnectivityCheck | {success: false; message: string; latency_ms?: number} | 'loading' | undefined;

function statusTag(configured?: boolean, text?: string) {
  return configured ? <Tag color="green">{text || '已配置'}</Tag> : <Tag color="red">{text || '未配置'}</Tag>;
}

function providerStatusText(status: string) {
  if (status === 'available') return '可用';
  if (status === 'disabled') return '已停用';
  if (status === 'not_configured') return '未配置';
  return status;
}

function splitDataSources(value: string) {
  return value.split(/[,，、\s]+/).map(item => item.trim()).filter(Boolean);
}

function newKey(prefix: string) {
  return `${prefix}_${Date.now()}_${Math.random().toString(16).slice(2, 8)}`;
}

function checkAlert(provider: string, state: CheckState) {
  if (!state) return null;
  if (state === 'loading') {
    return <Alert style={{marginTop: 8}} type="info" showIcon message={`${provider} 连接测试中...`} />;
  }
  const ok = 'success' in state ? state.success : state.reachable;
  return (
    <Alert
      style={{marginTop: 8}}
      type={ok ? 'success' : 'error'}
      showIcon
      message={ok ? `${provider} 测试成功` : `${provider} 测试失败`}
      description={`${state.message}${state.latency_ms != null ? ` · ${state.latency_ms}ms` : ''}`}
    />
  );
}

export default function SystemConfig() {
  const [token, setToken] = useState('');
  const [tokenStatus, setTokenStatus] = useState<'idle' | 'checking' | 'valid' | 'invalid'>('idle');
  const [configForm] = Form.useForm();
  const [memoryForm] = Form.useForm();
  const [managedConfig, setManagedConfig] = useState<any>(null);
  const [dataSources, setDataSources] = useState<DataSourceStatus[]>([]);
  const [checks, setChecks] = useState<Record<string, CheckState>>({});
  const [dimensions, setDimensions] = useState<ScoringDimensionConfig[]>([]);
  const [memories, setMemories] = useState<MemoryItem[]>([]);
  const [savingConfig, setSavingConfig] = useState(false);
  const [savingDimensions, setSavingDimensions] = useState(false);
  const [loading, setLoading] = useState(false);
  const [configSaveFeedback, setConfigSaveFeedback] = useState<{
    type: 'success' | 'error' | 'info' | 'warning';
    message: string;
    description?: string;
  } | null>(null);

  const totalWeight = useMemo(
    () => dimensions.filter(item => item.enabled).reduce((sum, item) => sum + Number(item.weight || 0), 0),
    [dimensions],
  );
  const deepseekConfigured = Boolean(managedConfig?.deepseek?.configured);
  const amapConfigured = Boolean(managedConfig?.amap?.configured || managedConfig?.amap_js?.configured);
  const crawlerConfigured = Boolean(managedConfig?.crawler?.configured);

  const loadAll = async () => {
    setLoading(true);
    try {
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
        crawler_enabled: Boolean(config?.crawler_enabled),
        crawler_provider: config?.crawler_provider || 'crawl4ai',
        crawler_timeout_seconds: Number(config?.crawler_timeout_seconds || 60),
        crawler_max_pages_per_task: Number(config?.crawler_max_pages_per_task || 5),
        crawler_max_tasks_per_project: Number(config?.crawler_max_tasks_per_project || 50),
        crawler_rate_limit_seconds: Number(config?.crawler_rate_limit_seconds || 5),
        crawler_allowed_domains: config?.crawler_allowed_domains || '',
        crawler_blocked_domains: config?.crawler_blocked_domains || '',
      });
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadAll().catch(error => message.error(error.message || '配置加载失败'));
  }, []);

  const verifyToken = async () => {
    if (!token.trim()) {
      setTokenStatus('invalid');
      message.warning('请先输入 ADMIN_CONFIG_TOKEN');
      return;
    }
    setTokenStatus('checking');
    try {
      await verifyManagedSystemConfigToken(token.trim());
      setTokenStatus('valid');
      message.success('管理员 Token 验证成功');
    } catch (error: any) {
      setTokenStatus('invalid');
      message.error(error?.response?.data?.detail || error.message || '管理员 Token 验证失败');
    }
  };

  const saveConfigPatch = async (
    patch: Record<string, string | number | boolean | undefined>,
    options: {showEmptyMessage?: boolean} = {showEmptyMessage: true},
  ) => {
    if (!token.trim()) {
      setConfigSaveFeedback({
        type: 'warning',
        message: '需要管理员 Token',
        description: '只有管理员需要输入 ADMIN_CONFIG_TOKEN。Key 保存成功后会全局生效，普通使用者不需要输入 Token。',
      });
      message.warning('请先输入 ADMIN_CONFIG_TOKEN');
      return false;
    }
    const payload = Object.fromEntries(
      Object.entries(patch)
        .filter(([, value]) => value !== undefined && value !== null && String(value).trim() !== '')
        .map(([key, value]) => [key, typeof value === 'boolean' ? (value ? 'true' : 'false') : value]),
    ) as Record<string, string | number | boolean>;
    if (!Object.keys(payload).length) {
      if (options.showEmptyMessage) {
        setConfigSaveFeedback({
          type: 'info',
          message: '没有需要保存的配置',
          description: '如果状态已经显示“已配置”，普通用户可以直接在工作台使用相关能力。',
        });
        message.info('没有需要保存的配置');
      }
      return true;
    }
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
      setConfigSaveFeedback({
        type: 'success',
        message: '配置已加密保存并全局生效',
        description: `保存时间：${new Date().toLocaleString('zh-CN')}。后续普通使用者进入工作台即可使用，不需要输入管理员 Token。`,
      });
      message.success('配置已加密保存');
      return true;
    } catch (error: any) {
      const reason = error?.response?.data?.detail || error.message || '配置保存失败';
      setConfigSaveFeedback({
        type: 'error',
        message: '配置保存失败',
        description: reason,
      });
      message.error(reason);
      return false;
    } finally {
      setSavingConfig(false);
    }
  };

  const saveDeepSeekConfig = () => {
    const values = configForm.getFieldsValue([
      'deepseek_base_url',
      'deepseek_model',
      'deepseek_api_key',
    ]);
    return saveConfigPatch(values);
  };

  const saveAmapConfig = () => {
    const values = configForm.getFieldsValue([
      'amap_web_service_key',
      'amap_js_key',
      'amap_security_js_code',
    ]);
    return saveConfigPatch(values);
  };

  const saveThirdPartyConfig = () => {
    const values = configForm.getFieldsValue(['third_party_api_key']);
    return saveConfigPatch(values);
  };

  const saveCrawlerConfig = () => {
    const values = configForm.getFieldsValue([
      'crawler_enabled',
      'crawler_provider',
      'crawler_timeout_seconds',
      'crawler_max_pages_per_task',
      'crawler_max_tasks_per_project',
      'crawler_rate_limit_seconds',
      'crawler_allowed_domains',
      'crawler_blocked_domains',
    ]);
    return saveConfigPatch(values);
  };

  const testManagedProvider = async (provider: 'deepseek' | 'amap') => {
    if (!token.trim()) {
      setConfigSaveFeedback({
        type: 'warning',
        message: '测试连接需要管理员 Token',
        description: '测试连接会先保存当前填写的 Key，因此需要管理员 Token。普通用户不需要执行此操作。',
      });
      message.warning('请先输入 ADMIN_CONFIG_TOKEN');
      return;
    }
    const pendingValues = provider === 'deepseek'
      ? configForm.getFieldsValue(['deepseek_base_url', 'deepseek_model', 'deepseek_api_key'])
      : configForm.getFieldsValue(['amap_web_service_key', 'amap_js_key', 'amap_security_js_code']);
    const saved = await saveConfigPatch(pendingValues, {showEmptyMessage: false});
    if (!saved) return;
    setChecks(previous => ({...previous, [provider]: 'loading'}));
    try {
      const result = await testManagedSystemConfig(provider, token.trim());
      setChecks(previous => ({...previous, [provider]: result}));
      message.success(result.message);
    } catch (error: any) {
      setChecks(previous => ({
        ...previous,
        [provider]: {
          success: false,
          message: error?.response?.data?.detail || error.message || '连接测试失败',
        },
      }));
    }
  };

  const testDataSource = async (name: string) => {
    setChecks(previous => ({...previous, [name]: 'loading'}));
    try {
      const result = await checkDataSourceConnectivity(name);
      setChecks(previous => ({...previous, [name]: result}));
    } catch (error: any) {
      setChecks(previous => ({
        ...previous,
        [name]: {success: false, message: error?.response?.data?.detail || error.message || '检测失败，请稍后重试'},
      }));
    }
  };

  const updateDimension = (index: number, patch: Partial<ScoringDimensionConfig>) => {
    setDimensions(previous => previous.map((item, itemIndex) => itemIndex === index ? {...item, ...patch} : item));
  };

  const updateFactor = (dimensionIndex: number, factorIndex: number, patch: Partial<ScoringFactorConfig>) => {
    setDimensions(previous => previous.map((dimension, itemIndex) => {
      if (itemIndex !== dimensionIndex) return dimension;
      return {
        ...dimension,
        factors: (dimension.factors || []).map((factor, currentFactorIndex) => (
          currentFactorIndex === factorIndex ? {...factor, ...patch} : factor
        )),
      };
    }));
  };

  const addDimension = () => {
    setDimensions(previous => [
      ...previous,
      {
        key: newKey('dimension'),
        name: '新维度',
        description: '请填写该维度的业务含义',
        weight: 0,
        enabled: true,
        data_sources: ['manual'],
        sort_order: previous.length,
        factors: [],
      },
    ]);
  };

  const removeDimension = (index: number) => {
    setDimensions(previous => previous.filter((_, itemIndex) => itemIndex !== index));
  };

  const addFactor = (dimensionIndex: number) => {
    setDimensions(previous => previous.map((dimension, itemIndex) => {
      if (itemIndex !== dimensionIndex) return dimension;
      const factors = dimension.factors || [];
      return {
        ...dimension,
        factors: [
          ...factors,
          {
            key: newKey('factor'),
            name: '新子维度',
            description: '请填写该子维度的判断规则',
            weight: 0,
            enabled: true,
            data_sources: dimension.data_sources || ['manual'],
            sort_order: factors.length,
            config: {},
          },
        ],
      };
    }));
  };

  const removeFactor = (dimensionIndex: number, factorIndex: number) => {
    setDimensions(previous => previous.map((dimension, itemIndex) => {
      if (itemIndex !== dimensionIndex) return dimension;
      return {
        ...dimension,
        factors: (dimension.factors || []).filter((_, currentFactorIndex) => currentFactorIndex !== factorIndex),
      };
    }));
  };

  const saveDimensions = async () => {
    setSavingDimensions(true);
    try {
      const payload = dimensions.map((item, index) => ({...item, sort_order: index}));
      const result = await updateScoringConfig(payload);
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
        tags: String(values.tags || '').split(/[,，、\s]+/).filter(Boolean),
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
            集中管理 Key、模型、数据源、评分维度、权重和 memory。管理员首次部署后配置一次即可，敏感 Key 会加密保存并全局生效，普通使用者进入工作台即可使用。
          </Typography.Paragraph>
        </div>
        <Button icon={<ReloadOutlined />} loading={loading} onClick={() => loadAll()}>刷新</Button>
      </div>

      <Card title="管理员验证">
        <Space.Compact style={{width: '100%'}}>
          <Input.Password
            value={token}
            onChange={event => {
              setToken(event.target.value);
              setTokenStatus('idle');
            }}
            placeholder="请输入 ADMIN_CONFIG_TOKEN"
            autoComplete="off"
          />
          <Button loading={tokenStatus === 'checking'} onClick={verifyToken}>验证管理员 Token</Button>
        </Space.Compact>
        {tokenStatus === 'valid' && <Alert style={{marginTop: 8}} type="success" showIcon message="管理员 Token 验证成功，可以保存配置和测试连接。" />}
        {tokenStatus === 'invalid' && <Alert style={{marginTop: 8}} type="error" showIcon message="管理员 Token 验证失败，请检查 /etc/esports-site-selection/backend.env。" />}
        <Typography.Paragraph type="secondary" style={{marginTop: 8}}>
          管理员 Token 只用于保护配置写入，不需要也不建议保存到浏览器。Key 保存成功后存入服务器加密配置，普通使用者不需要知道 Token，也不需要重复配置 Key。
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
                    <Input placeholder="https://api.deepseek.com" />
                  </Form.Item>
                  <Form.Item name="deepseek_model" label="模型">
                    <Input placeholder="deepseek-chat" />
                  </Form.Item>
                  <Form.Item name="deepseek_api_key" label="DeepSeek API Key">
                    <Input.Password placeholder="填写后点击保存 DeepSeek 配置" />
                  </Form.Item>
                  <Space>
                    <Button
                      type={deepseekConfigured ? 'default' : 'primary'}
                      icon={deepseekConfigured ? <CheckCircleOutlined /> : <SaveOutlined />}
                      loading={savingConfig}
                      onClick={saveDeepSeekConfig}
                    >
                      {deepseekConfigured ? '已保存 DeepSeek 配置' : '保存 DeepSeek 配置'}
                    </Button>
                    <Button onClick={() => testManagedProvider('deepseek')} loading={checks.deepseek === 'loading'}>测试 DeepSeek</Button>
                  </Space>
                  {checkAlert('DeepSeek', checks.deepseek)}
                </Space>
              </Card>
            </Col>
            <Col xs={24} md={12}>
              <Card size="small" title="高德地图">
                <Space direction="vertical" style={{width: '100%'}}>
                  <Space>Web Service：{statusTag(managedConfig?.amap?.configured)} {managedConfig?.amap?.masked || ''}</Space>
                  <Space>JS Key：{statusTag(managedConfig?.amap_js?.configured)} {managedConfig?.amap_js?.masked || ''}</Space>
                  <Form.Item name="amap_web_service_key" label="高德 Web Service Key">
                    <Input.Password placeholder="后端地址解析和 POI 查询使用" />
                  </Form.Item>
                  <Form.Item name="amap_js_key" label="高德 JS Key">
                    <Input.Password placeholder="前端地图展示使用" />
                  </Form.Item>
                  <Form.Item name="amap_security_js_code" label="高德安全密钥">
                    <Input.Password placeholder="高德 JS API 2.0 安全密钥" />
                  </Form.Item>
                  <Space>
                    <Button
                      type={amapConfigured ? 'default' : 'primary'}
                      icon={amapConfigured ? <CheckCircleOutlined /> : <SaveOutlined />}
                      loading={savingConfig}
                      onClick={saveAmapConfig}
                    >
                      {amapConfigured ? '已保存高德配置' : '保存高德配置'}
                    </Button>
                    <Button onClick={() => testManagedProvider('amap')} loading={checks.amap === 'loading'}>测试高德</Button>
                  </Space>
                  {checkAlert('高德', checks.amap)}
                </Space>
              </Card>
            </Col>
            <Col span={24}>
              <Card size="small" title="后续第三方平台 Key">
                <Form.Item name="third_party_api_key" label="第三方平台 Key">
                  <Input.Password placeholder="预留：美团、消费数据等第三方平台" />
                </Form.Item>
                <Button loading={savingConfig} onClick={saveThirdPartyConfig}>保存第三方配置</Button>
              </Card>
            </Col>
            <Col span={24}>
              <Card
                size="small"
                title="爬虫数据源"
                extra={crawlerConfigured ? <Tag color="green">已启用</Tag> : <Tag color="orange">默认关闭</Tag>}
              >
                <Alert
                  style={{marginBottom: 12}}
                  type="warning"
                  showIcon
                  message="合规限制"
                  description="只抓取允许访问的公开页面，不绕过登录、验证码、反爬或付费墙；结果默认待人工确认。"
                />
                <Row gutter={12}>
                  <Col xs={24} md={6}>
                    <Form.Item name="crawler_enabled" label="启用爬虫" valuePropName="checked">
                      <Switch checkedChildren="启用" unCheckedChildren="关闭" />
                    </Form.Item>
                  </Col>
                  <Col xs={24} md={6}>
                    <Form.Item name="crawler_provider" label="Provider">
                      <Input placeholder="crawl4ai" />
                    </Form.Item>
                  </Col>
                  <Col xs={24} md={6}>
                    <Form.Item name="crawler_timeout_seconds" label="单任务超时（秒）">
                      <InputNumber min={10} max={300} style={{width: '100%'}} />
                    </Form.Item>
                  </Col>
                  <Col xs={24} md={6}>
                    <Form.Item name="crawler_max_tasks_per_project" label="单项目最大任务数">
                      <InputNumber min={1} max={200} style={{width: '100%'}} />
                    </Form.Item>
                  </Col>
                  <Col xs={24} md={6}>
                    <Form.Item name="crawler_max_pages_per_task" label="单任务最大页数">
                      <InputNumber min={1} max={20} style={{width: '100%'}} />
                    </Form.Item>
                  </Col>
                  <Col xs={24} md={6}>
                    <Form.Item name="crawler_rate_limit_seconds" label="请求间隔（秒）">
                      <InputNumber min={0} max={60} style={{width: '100%'}} />
                    </Form.Item>
                  </Col>
                  <Col xs={24} md={6}>
                    <Form.Item name="crawler_allowed_domains" label="允许域名">
                      <Input placeholder="example.com,example.cn" />
                    </Form.Item>
                  </Col>
                  <Col xs={24} md={6}>
                    <Form.Item name="crawler_blocked_domains" label="禁用域名">
                      <Input placeholder="禁止访问的域名，逗号分隔" />
                    </Form.Item>
                  </Col>
                </Row>
                <Space>
                  <Button
                    type={crawlerConfigured ? 'default' : 'primary'}
                    icon={crawlerConfigured ? <CheckCircleOutlined /> : <SaveOutlined />}
                    loading={savingConfig}
                    onClick={saveCrawlerConfig}
                  >
                    {crawlerConfigured ? '已保存爬虫配置' : '保存爬虫配置'}
                  </Button>
                  <Button onClick={() => testDataSource('crawler_competitor')} loading={checks.crawler_competitor === 'loading'}>
                    测试竞品爬虫
                  </Button>
                  <Button onClick={() => testDataSource('crawler_supporting')} loading={checks.crawler_supporting === 'loading'}>
                    测试配套爬虫
                  </Button>
                  <Button onClick={() => testDataSource('crawler_rent')} loading={checks.crawler_rent === 'loading'}>
                    测试租金爬虫
                  </Button>
                </Space>
                {checkAlert('竞品爬虫', checks.crawler_competitor)}
                {checkAlert('配套爬虫', checks.crawler_supporting)}
                {checkAlert('租金爬虫', checks.crawler_rent)}
              </Card>
            </Col>
          </Row>
        </Form>
        {savingConfig && <Alert style={{marginTop: 12}} type="info" showIcon message="正在保存配置..." />}
        {configSaveFeedback && (
          <Alert
            style={{marginTop: 12}}
            type={configSaveFeedback.type}
            showIcon
            message={configSaveFeedback.message}
            description={configSaveFeedback.description}
          />
        )}
      </Card>

      <Card title="评分维度和权重">
        <Alert
          type={Math.abs(totalWeight - 100) < 0.01 ? 'success' : 'warning'}
          showIcon
          message={`当前启用维度权重合计：${totalWeight.toFixed(2)}`}
          description="建议合计为 100。新增维度默认不影响评分，保存后会进入后续分析上下文。"
          style={{marginBottom: 12}}
        />
        {loading && <Alert style={{marginBottom: 12}} type="info" showIcon message="正在加载评分配置..." />}
        {!loading && dimensions.length === 0 && (
          <Alert style={{marginBottom: 12}} type="warning" showIcon message="评分配置为空，请点击恢复默认。" />
        )}
        <Space style={{marginBottom: 12}}>
          <Button icon={<PlusOutlined />} onClick={addDimension}>新增维度</Button>
          <Button type="primary" icon={<SaveOutlined />} loading={savingDimensions} onClick={saveDimensions}>保存维度配置</Button>
          <Button onClick={resetDimensions}>恢复默认</Button>
        </Space>
        <List
          dataSource={dimensions}
          locale={{emptyText: '暂无评分维度'}}
          renderItem={(item, index) => (
            <List.Item>
              <Card size="small" style={{width: '100%'}} title={<Space><span>{item.name}</span><Tag>{item.key}</Tag></Space>}>
                <Row gutter={12} align="middle">
                  <Col xs={24} md={4}><Input value={item.name} onChange={event => updateDimension(index, {name: event.target.value})} placeholder="维度名称" /></Col>
                  <Col xs={24} md={3}><InputNumber min={0} value={item.weight} onChange={value => updateDimension(index, {weight: Number(value || 0)})} style={{width: '100%'}} addonAfter="权重" /></Col>
                  <Col xs={24} md={3}><Switch checked={item.enabled} onChange={checked => updateDimension(index, {enabled: checked})} checkedChildren="启用" unCheckedChildren="停用" /></Col>
                  <Col xs={24} md={5}><Input value={(item.data_sources || []).join(',')} onChange={event => updateDimension(index, {data_sources: splitDataSources(event.target.value)})} placeholder="依赖数据源，逗号分隔" /></Col>
                  <Col xs={24} md={7}><Input value={item.description || ''} onChange={event => updateDimension(index, {description: event.target.value})} placeholder="说明" /></Col>
                  <Col xs={24} md={2}><Button danger onClick={() => removeDimension(index)}>删除</Button></Col>
                </Row>
                <Space style={{marginTop: 12, marginBottom: 8}}>
                  <Button size="small" icon={<PlusOutlined />} onClick={() => addFactor(index)}>新增子维度</Button>
                  <Typography.Text type="secondary">子维度用于记录更细的判断规则，后续可逐步接入独立评分。</Typography.Text>
                </Space>
                <List
                  size="small"
                  dataSource={item.factors || []}
                  locale={{emptyText: '暂无子维度'}}
                  renderItem={(factor, factorIndex) => (
                    <List.Item>
                      <Row gutter={8} style={{width: '100%'}} align="middle">
                        <Col xs={24} md={4}><Input value={factor.name} onChange={event => updateFactor(index, factorIndex, {name: event.target.value})} placeholder="子维度名称" /></Col>
                        <Col xs={24} md={3}><InputNumber min={0} value={factor.weight} onChange={value => updateFactor(index, factorIndex, {weight: Number(value || 0)})} style={{width: '100%'}} addonAfter="权重" /></Col>
                        <Col xs={24} md={3}><Switch checked={factor.enabled} onChange={checked => updateFactor(index, factorIndex, {enabled: checked})} checkedChildren="启用" unCheckedChildren="停用" /></Col>
                        <Col xs={24} md={5}><Input value={(factor.data_sources || []).join(',')} onChange={event => updateFactor(index, factorIndex, {data_sources: splitDataSources(event.target.value)})} placeholder="依赖数据源" /></Col>
                        <Col xs={24} md={7}><Input value={factor.description || ''} onChange={event => updateFactor(index, factorIndex, {description: event.target.value})} placeholder="说明" /></Col>
                        <Col xs={24} md={2}><Button danger size="small" onClick={() => removeFactor(index, factorIndex)}>删除</Button></Col>
                      </Row>
                    </List.Item>
                  )}
                />
              </Card>
            </List.Item>
          )}
        />
      </Card>

      <Card title="数据源">
        <List
          grid={{gutter: 12, xs: 1, md: 2, xl: 3}}
          dataSource={dataSources}
          locale={{emptyText: '暂无数据源状态'}}
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
                    {check === 'loading' && <Typography.Text type="secondary">检测中...</Typography.Text>}
                    {checkResult && (
                      <Typography.Text type={'success' in checkResult ? checkResult.success ? 'success' : 'danger' : checkResult.reachable ? 'success' : 'danger'}>
                        {checkResult.message}{checkResult.latency_ms != null ? ` · ${checkResult.latency_ms}ms` : ''}
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
