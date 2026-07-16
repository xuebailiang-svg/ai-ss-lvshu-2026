import {useEffect, useState} from 'react';
import {Alert, Button, Card, Descriptions, Form, Input, Space, Tag, Typography, message} from 'antd';
import {
  amapGeocodeTest,
  configStatus,
  getManagedSystemConfig,
  testManagedSystemConfig,
  updateManagedSystemConfig,
} from '../api/client';
import {loadRuntimeConfig, maskKey} from '../runtimeConfig';

declare global {
  interface Window {
    AMap: any;
    _AMapSecurityConfig?: {securityJsCode: string};
  }
}

async function testAmapSdkLoad() {
  const config = await loadRuntimeConfig(true);
  if (!config.amapJsKey) throw new Error('前端高德地图 JS Key 未配置，请在服务器配置 /etc/esports-site-selection/frontend-runtime.json');
  if (config.amapSecurityJsCode) window._AMapSecurityConfig = {securityJsCode: config.amapSecurityJsCode};
  if (window.AMap) return true;
  await new Promise<void>((resolve, reject) => {
    const script = document.createElement('script');
    script.async = true;
    script.src = `https://webapi.amap.com/maps?v=2.0&key=${encodeURIComponent(config.amapJsKey || '')}`;
    script.onload = () => window.AMap ? resolve() : reject(new Error('高德 SDK 已加载但 AMap 未初始化'));
    script.onerror = () => reject(new Error('高德地图 JavaScript API 加载失败'));
    document.head.appendChild(script);
  });
  return true;
}

export default function SystemConfig() {
  const [deepseekForm] = Form.useForm();
  const [amapForm] = Form.useForm();
  const [status, setStatus] = useState<any>();
  const [runtime, setRuntime] = useState<any>();
  const [managed, setManaged] = useState<any>();
  const [adminToken, setAdminToken] = useState('');
  const [saving, setSaving] = useState(false);
  const [testingProvider, setTestingProvider] = useState<string>();
  const [loading, setLoading] = useState(false);

  const load = async () => {
    const [config, runtimeConfig, managedConfig] = await Promise.all([
      configStatus(),
      loadRuntimeConfig(true).catch(() => ({})),
      getManagedSystemConfig(),
    ]);
    setStatus(config);
    setRuntime(runtimeConfig);
    setManaged(managedConfig);
  };

  useEffect(() => {
    load().catch(error => message.error(error.message));
  }, []);

  useEffect(() => {
    if (!managed) return;
    deepseekForm.setFieldsValue({
      deepseek_base_url: managed.deepseek_base_url || 'https://api.deepseek.com',
      deepseek_model: managed.deepseek_model || 'deepseek-chat',
    });
  }, [managed, deepseekForm]);

  const runGeocodeTest = async (values: {city: string; address: string}) => {
    setLoading(true);
    try {
      const result = await amapGeocodeTest(values);
      message.success(`后端地址解析成功：${result.result?.formatted_address || values.address}`);
    } catch (error: any) {
      message.error(error.response?.data?.detail?.message || error.response?.data?.detail || error.message);
    } finally {
      setLoading(false);
    }
  };

  const runFrontendMapTest = async () => {
    setLoading(true);
    try {
      await testAmapSdkLoad();
      message.success('前端高德地图 JavaScript SDK 加载成功');
    } catch (error: any) {
      message.error(error.message);
    } finally {
      setLoading(false);
    }
  };

  const saveManagedConfig = async (values: Record<string, string>) => {
    if (!adminToken.trim()) {
      message.error('请输入管理员 Token');
      return;
    }
    const payload = Object.fromEntries(
      Object.entries(values).filter(([, value]) => typeof value === 'string' && value.trim()),
    );
    if (Object.keys(payload).length === 0) {
      message.info('没有需要保存的配置');
      return;
    }
    setSaving(true);
    try {
      const result = await updateManagedSystemConfig(payload, adminToken.trim());
      setManaged(result);
      deepseekForm.setFieldValue('deepseek_api_key', undefined);
      amapForm.setFieldValue('amap_web_service_key', undefined);
      message.success('系统配置已加密保存并立即生效');
    } catch (error: any) {
      message.error(error.response?.data?.detail || error.message || '配置保存失败');
    } finally {
      setSaving(false);
    }
  };

  const testManagedConnection = async (providerName: 'deepseek' | 'amap') => {
    if (!adminToken.trim()) {
      message.error('请输入管理员 Token');
      return;
    }
    setTestingProvider(providerName);
    try {
      const result = await testManagedSystemConfig(providerName, adminToken.trim());
      message.success(`${result.message}${result.latency_ms == null ? '' : `，耗时 ${result.latency_ms}ms`}`);
    } catch (error: any) {
      message.error(error.response?.data?.detail || error.message || '连接测试失败');
    } finally {
      setTestingProvider(undefined);
    }
  };

  return (
    <div className="page">
      <h2>系统配置</h2>
      <Alert
        type="info"
        showIcon
        message="第三方 Key 使用加密存储"
        description="页面不会回显完整 Key。保存和连接测试必须通过管理员 Token 验证；Token 仅保留在当前页面内存中。"
      />

      <Card title="管理员验证">
        <Space direction="vertical" style={{width: '100%'}}>
          <Input.Password
            value={adminToken}
            onChange={event => setAdminToken(event.target.value)}
            placeholder="请输入 ADMIN_CONFIG_TOKEN"
            autoComplete="off"
          />
          <Typography.Text type={managed?.management_enabled ? 'success' : 'danger'}>
            {managed?.management_enabled
              ? 'Web 配置管理已启用'
              : 'Web 配置管理未启用，请先在服务器配置加密主密钥和管理员 Token'}
          </Typography.Text>
        </Space>
      </Card>

      <Card title="AI 模型配置">
        <Descriptions column={1} style={{marginBottom: 16}} items={[
          {key: 'status', label: 'DeepSeek Key', children: managed?.deepseek?.configured ? <Tag color="green">已配置</Tag> : <Tag color="red">未配置</Tag>},
          {key: 'masked', label: '脱敏 Key', children: managed?.deepseek?.masked || '-'},
          {key: 'source', label: '生效来源', children: managed?.deepseek?.source || '-'},
        ]} />
        <Form
          form={deepseekForm}
          layout="vertical"
          initialValues={{
            deepseek_base_url: managed?.deepseek_base_url || 'https://api.deepseek.com',
            deepseek_model: managed?.deepseek_model || 'deepseek-chat',
          }}
          onFinish={saveManagedConfig}
        >
          <Form.Item name="deepseek_base_url" label="API 地址">
            <Input placeholder="https://api.deepseek.com" />
          </Form.Item>
          <Form.Item name="deepseek_model" label="模型">
            <Input placeholder="deepseek-chat" />
          </Form.Item>
          <Form.Item name="deepseek_api_key" label="API Key">
            <Input.Password placeholder="输入新 Key；留空表示保持现有配置" autoComplete="new-password" />
          </Form.Item>
          <Space>
            <Button type="primary" htmlType="submit" loading={saving}>保存 AI 配置</Button>
            <Button onClick={() => testManagedConnection('deepseek')} loading={testingProvider === 'deepseek'}>测试 DeepSeek 连接</Button>
          </Space>
        </Form>
      </Card>

      <Card title="高德 Web 服务配置">
        <Descriptions column={1} style={{marginBottom: 16}} items={[
          {key: 'status', label: '高德 Web 服务 Key', children: managed?.amap?.configured ? <Tag color="green">已配置</Tag> : <Tag color="red">未配置</Tag>},
          {key: 'masked', label: '脱敏 Key', children: managed?.amap?.masked || '-'},
          {key: 'source', label: '生效来源', children: managed?.amap?.source || '-'},
        ]} />
        <Form form={amapForm} layout="vertical" onFinish={saveManagedConfig}>
          <Form.Item name="amap_web_service_key" label="高德 Web 服务 Key">
            <Input.Password placeholder="输入新 Key；留空表示保持现有配置" autoComplete="new-password" />
          </Form.Item>
          <Space>
            <Button type="primary" htmlType="submit" loading={saving}>保存高德配置</Button>
            <Button onClick={() => testManagedConnection('amap')} loading={testingProvider === 'amap'}>测试高德连接</Button>
          </Space>
        </Form>
      </Card>

      <Card title="配置文件位置">
        <Descriptions column={1} items={[
          {key: 'backend', label: '后端私密配置', children: '/etc/esports-site-selection/backend.env'},
          {key: 'frontend', label: '前端公开运行配置', children: '/etc/esports-site-selection/frontend-runtime.json'},
          {key: 'runtime', label: '浏览器读取路径', children: '/runtime-config.json'},
        ]} />
      </Card>

      <Card title="配置状态">
        <Descriptions column={1} items={[
          {key: 'backend-key', label: '后端高德 Web 服务 Key', children: status?.backend?.amapWebServiceKeyConfigured ? <Tag color="green">已配置</Tag> : <Tag color="red">未配置</Tag>},
          {key: 'db', label: '数据库连接', children: status?.backend?.databaseConfigured ? <Tag color="green">已配置</Tag> : <Tag color="red">未配置</Tag>},
          {key: 'mock', label: 'AMAP_MOCK', children: String(status?.backend?.amapMock ?? '-')},
          {key: 'runtime-exists', label: '前端 runtime 配置文件', children: status?.frontend?.runtimeConfigExists ? <Tag color="green">存在</Tag> : <Tag color="red">不存在或无效</Tag>},
          {key: 'frontend-key', label: '前端高德 JS Key', children: status?.frontend?.amapJsKeyConfigured ? <Tag color="green">已配置</Tag> : <Tag color="red">未配置</Tag>},
          {key: 'frontend-code', label: '前端安全密钥', children: status?.frontend?.amapSecurityJsCodeConfigured ? <Tag color="green">已配置</Tag> : <Tag>未配置</Tag>},
          {key: 'masked', label: '前端 JS Key 脱敏', children: status?.frontend?.amapJsKeyMasked || maskKey(runtime?.amapJsKey)},
          {key: 'provider', label: '地图 Provider', children: status?.frontend?.mapProvider || runtime?.mapProvider || 'amap'},
        ]} />
        <Button onClick={load}>刷新配置状态</Button>
      </Card>

      <Card title="后端地址解析测试">
        <Form layout="inline" onFinish={runGeocodeTest} initialValues={{city: '西安市', address: '雁塔区小寨西路'}}>
          <Form.Item name="city" label="城市" rules={[{required: true}]}>
            <Input />
          </Form.Item>
          <Form.Item name="address" label="地址" rules={[{required: true}]}>
            <Input style={{width: 260}} />
          </Form.Item>
          <Button type="primary" htmlType="submit" loading={loading}>测试后端地址解析</Button>
        </Form>
      </Card>

      <Card title="前端地图加载测试">
        <Space direction="vertical">
          <p>测试浏览器是否能读取 `/runtime-config.json` 并加载高德 JavaScript SDK。不会显示完整 Key。</p>
          <Button onClick={runFrontendMapTest} loading={loading}>测试前端地图加载</Button>
        </Space>
      </Card>

      <Card title="服务器修改命令">
        <pre>{`sudo nano /etc/esports-site-selection/backend.env
sudo nano /etc/esports-site-selection/frontend-runtime.json
sudo systemctl restart esports-site-selection
sudo systemctl reload nginx`}</pre>
      </Card>
    </div>
  );
}
