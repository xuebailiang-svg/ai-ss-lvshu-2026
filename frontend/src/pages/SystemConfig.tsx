import {useEffect, useState} from 'react';
import {Alert, Button, Card, Col, Form, Input, Row, Space, Tag, Typography, message} from 'antd';
import {CheckCircleOutlined, ReloadOutlined, SaveOutlined} from '@ant-design/icons';
import {
  getManagedSystemConfig,
  testManagedSystemConfig,
  updateManagedSystemConfig,
  verifyManagedSystemConfigToken,
} from '../api/client';

type ProviderName = 'deepseek' | 'amap';
type CheckState = {success: boolean; message: string; latency_ms?: number} | 'loading' | undefined;

function errorText(error: any, fallback: string) {
  const detail = error?.response?.data?.detail;
  if (typeof detail === 'string') return detail;
  if (Array.isArray(detail)) {
    return detail.map(item => item?.msg || item?.message || JSON.stringify(item)).join('；');
  }
  if (detail && typeof detail === 'object') return detail.message || JSON.stringify(detail);
  return error?.message || fallback;
}

function configuredTag(configured: boolean) {
  return configured
    ? <Tag color="green" icon={<CheckCircleOutlined />}>已配置</Tag>
    : <Tag color="orange">未配置</Tag>;
}

export default function SystemConfig() {
  const [form] = Form.useForm();
  const [token, setToken] = useState('');
  const [tokenStatus, setTokenStatus] = useState<'idle' | 'checking' | 'valid' | 'invalid'>('idle');
  const [config, setConfig] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState<ProviderName | null>(null);
  const [checks, setChecks] = useState<Record<ProviderName, CheckState>>({deepseek: undefined, amap: undefined});
  const [feedback, setFeedback] = useState<{type: 'success' | 'error' | 'warning' | 'info'; message: string; description?: string} | null>(null);

  const load = async () => {
    setLoading(true);
    try {
      const result = await getManagedSystemConfig();
      setConfig(result);
      form.setFieldsValue({
        deepseek_base_url: result?.deepseek_base_url || 'https://api.deepseek.com',
        deepseek_model: result?.deepseek_model || 'deepseek-chat',
      });
    } catch (error: any) {
      const reason = errorText(error, '配置加载失败');
      setFeedback({type: 'error', message: '配置加载失败', description: reason});
      message.error(reason);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
  }, []);

  const requireToken = () => {
    if (token.trim()) return true;
    setFeedback({
      type: 'warning',
      message: '需要管理员 Token',
      description: '部署管理员首次配置时输入 ADMIN_CONFIG_TOKEN。Key 保存后全局生效，普通使用者不需要再次配置。',
    });
    message.warning('请先输入 ADMIN_CONFIG_TOKEN');
    return false;
  };

  const verifyToken = async () => {
    if (!requireToken()) {
      setTokenStatus('invalid');
      return;
    }
    setTokenStatus('checking');
    try {
      await verifyManagedSystemConfigToken(token.trim());
      setTokenStatus('valid');
      setFeedback({type: 'success', message: '管理员身份验证成功', description: '现在可以保存或测试高德和 DeepSeek 配置。'});
      message.success('管理员 Token 验证成功');
    } catch (error: any) {
      const reason = errorText(error, '管理员 Token 验证失败');
      setTokenStatus('invalid');
      setFeedback({type: 'error', message: '管理员身份验证失败', description: reason});
      message.error(reason);
    }
  };

  const providerFields = (provider: ProviderName) => provider === 'deepseek'
    ? ['deepseek_api_key', 'deepseek_base_url', 'deepseek_model']
    : ['amap_web_service_key'];

  const saveProvider = async (provider: ProviderName, showNoChanges = true) => {
    if (!requireToken()) return false;
    const values = form.getFieldsValue(providerFields(provider));
    const payload = Object.fromEntries(
      Object.entries(values).filter(([, value]) => value !== undefined && value !== null && String(value).trim() !== ''),
    ) as Record<string, string | number | boolean>;
    if (!Object.keys(payload).length) {
      if (showNoChanges) message.info('没有需要保存的新配置');
      return Boolean(provider === 'deepseek' ? config?.deepseek?.configured : config?.amap?.configured);
    }
    setSaving(provider);
    try {
      const result = await updateManagedSystemConfig(payload, token.trim());
      setConfig(result);
      form.setFieldValue(provider === 'deepseek' ? 'deepseek_api_key' : 'amap_web_service_key', undefined);
      const name = provider === 'deepseek' ? 'DeepSeek' : '高德 Web Service';
      setFeedback({
        type: 'success',
        message: `${name} 配置保存成功`,
        description: 'Key 已加密保存并全局生效，页面不会回显完整 Key。',
      });
      message.success(`${name} 配置保存成功`);
      return true;
    } catch (error: any) {
      const reason = errorText(error, '配置保存失败');
      setFeedback({type: 'error', message: '配置保存失败', description: reason});
      message.error(reason);
      return false;
    } finally {
      setSaving(null);
    }
  };

  const testProvider = async (provider: ProviderName) => {
    if (!requireToken()) return;
    const values = form.getFieldsValue(providerFields(provider));
    const hasPendingValue = Object.values(values).some(value => value !== undefined && value !== null && String(value).trim() !== '');
    if (hasPendingValue) {
      const saved = await saveProvider(provider, false);
      if (!saved) return;
    }
    setChecks(previous => ({...previous, [provider]: 'loading'}));
    try {
      const result = await testManagedSystemConfig(provider, token.trim());
      setChecks(previous => ({...previous, [provider]: result}));
      message.success(result.message || '连接测试成功');
    } catch (error: any) {
      const reason = errorText(error, '连接测试失败');
      setChecks(previous => ({...previous, [provider]: {success: false, message: reason}}));
      message.error(reason);
    }
  };

  const renderCheck = (provider: ProviderName, label: string) => {
    const state = checks[provider];
    if (!state) return null;
    if (state === 'loading') return <Alert style={{marginTop: 12}} type="info" showIcon message={`${label} 连接测试中...`} />;
    return (
      <Alert
        style={{marginTop: 12}}
        type={state.success ? 'success' : 'error'}
        showIcon
        message={state.success ? `${label} 测试成功` : `${label} 测试失败`}
        description={`${state.message}${state.latency_ms != null ? ` · ${state.latency_ms}ms` : ''}`}
      />
    );
  };

  const deepseekConfigured = Boolean(config?.deepseek?.configured);
  const amapConfigured = Boolean(config?.amap?.configured);

  return (
    <div className="page">
      <div className="page-title-row">
        <div>
          <Typography.Title level={2}>系统配置</Typography.Title>
          <Typography.Paragraph type="secondary">
            仅配置当前选址流程需要的高德 Web Service 和 DeepSeek。管理员部署后配置一次，所有普通使用者即可使用。
          </Typography.Paragraph>
        </div>
        <Button icon={<ReloadOutlined />} loading={loading} onClick={load}>刷新状态</Button>
      </div>

      {feedback && (
        <Alert
          closable
          onClose={() => setFeedback(null)}
          style={{marginBottom: 16}}
          type={feedback.type}
          showIcon
          message={feedback.message}
          description={feedback.description}
        />
      )}

      <Card title="管理员验证" style={{marginBottom: 16}}>
        <Alert
          style={{marginBottom: 12}}
          type="info"
          showIcon
          message="管理员 Token 不会保存到浏览器"
          description="Token 只在本次页面操作中用于保护 Key。Key 保存到服务器后普通用户不需要管理员 Token。"
        />
        <Space.Compact style={{width: '100%', maxWidth: 760}}>
          <Input.Password
            value={token}
            onChange={event => {
              setToken(event.target.value);
              setTokenStatus('idle');
            }}
            placeholder="输入部署环境中的 ADMIN_CONFIG_TOKEN"
          />
          <Button loading={tokenStatus === 'checking'} onClick={verifyToken}>验证</Button>
        </Space.Compact>
        {tokenStatus === 'valid' && <Tag style={{marginLeft: 12}} color="green">已验证</Tag>}
        {tokenStatus === 'invalid' && <Tag style={{marginLeft: 12}} color="red">验证失败</Tag>}
      </Card>

      <Form form={form} layout="vertical">
        <Row gutter={[16, 16]}>
          <Col xs={24} lg={12}>
            <Card title="DeepSeek" extra={configuredTag(deepseekConfigured)} loading={loading} style={{height: '100%'}}>
              <Typography.Paragraph type="secondary">
                当前状态：{config?.deepseek?.masked || '未保存 Key'}
              </Typography.Paragraph>
              <Form.Item name="deepseek_base_url" label="API 地址" rules={[{required: true, message: '请输入 API 地址'}]}>
                <Input placeholder="https://api.deepseek.com" />
              </Form.Item>
              <Form.Item name="deepseek_model" label="模型" rules={[{required: true, message: '请输入模型名称'}]}>
                <Input placeholder="deepseek-chat" />
              </Form.Item>
              <Form.Item name="deepseek_api_key" label="API Key">
                <Input.Password placeholder={deepseekConfigured ? '已配置；留空表示不更换' : '请输入 DeepSeek API Key'} />
              </Form.Item>
              <Space wrap>
                <Button
                  type={deepseekConfigured ? 'default' : 'primary'}
                  icon={deepseekConfigured ? <CheckCircleOutlined /> : <SaveOutlined />}
                  loading={saving === 'deepseek'}
                  onClick={() => saveProvider('deepseek')}
                >
                  {deepseekConfigured ? '更新配置' : '保存配置'}
                </Button>
                <Button loading={checks.deepseek === 'loading'} onClick={() => testProvider('deepseek')}>测试 DeepSeek</Button>
              </Space>
              {renderCheck('deepseek', 'DeepSeek')}
            </Card>
          </Col>

          <Col xs={24} lg={12}>
            <Card title="高德地图 Web Service" extra={configuredTag(amapConfigured)} loading={loading} style={{height: '100%'}}>
              <Typography.Paragraph type="secondary">
                当前状态：{config?.amap?.masked || '未保存 Key'}
              </Typography.Paragraph>
              <Alert
                style={{marginBottom: 12}}
                type="info"
                showIcon
                message="只使用 Web Service Key"
                description="用于地址解析和周边 POI 采集。当前 MVP 不要求配置 JS Key 或安全密钥。"
              />
              <Form.Item name="amap_web_service_key" label="Web Service Key">
                <Input.Password placeholder={amapConfigured ? '已配置；留空表示不更换' : '请输入高德 Web Service Key'} />
              </Form.Item>
              <Space wrap>
                <Button
                  type={amapConfigured ? 'default' : 'primary'}
                  icon={amapConfigured ? <CheckCircleOutlined /> : <SaveOutlined />}
                  loading={saving === 'amap'}
                  onClick={() => saveProvider('amap')}
                >
                  {amapConfigured ? '更新配置' : '保存配置'}
                </Button>
                <Button loading={checks.amap === 'loading'} onClick={() => testProvider('amap')}>测试高德</Button>
              </Space>
              {renderCheck('amap', '高德')}
            </Card>
          </Col>
        </Row>
      </Form>
    </div>
  );
}
