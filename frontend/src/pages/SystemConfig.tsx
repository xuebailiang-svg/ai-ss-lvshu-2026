import {useEffect, useState} from 'react';
import {Alert, Button, Card, Descriptions, Form, Input, Space, Tag, message} from 'antd';
import {amapGeocodeTest, configStatus} from '../api/client';
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
  const [status, setStatus] = useState<any>();
  const [runtime, setRuntime] = useState<any>();
  const [loading, setLoading] = useState(false);

  const load = async () => {
    const [config, runtimeConfig] = await Promise.all([
      configStatus(),
      loadRuntimeConfig(true).catch(() => ({})),
    ]);
    setStatus(config);
    setRuntime(runtimeConfig);
  };

  useEffect(() => {
    load().catch(error => message.error(error.message));
  }, []);

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

  return (
    <div className="page">
      <h2>系统配置</h2>
      <Alert
        type="info"
        showIcon
        message="本页面只显示配置状态和脱敏信息"
        description="没有登录和管理权限控制，因此浏览器端不提供保存后端 Key 的能力。请到服务器编辑配置文件。"
      />

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
