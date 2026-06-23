import {useState} from 'react';
import {useNavigate} from 'react-router-dom';
import {
  Alert,
  Button,
  Card,
  Collapse,
  Form,
  Input,
  InputNumber,
  Progress,
  Space,
  Spin,
  Switch,
  Table,
  Tag,
  message,
} from 'antd';
import type {Evaluation, PropertySurvey} from '../types';
import {collectPois, createEvaluation, geocode, getEvaluation, score} from '../api/client';
import MapPanel from '../components/MapPanel';

const booleans: [keyof PropertySurvey, string][] = [
  ['street_facing', '临街可见'],
  ['night_entrance', '独立夜间出入口'],
  ['use_allowed', '物业允许电竞/网吧用途'],
  ['power_sufficient', '电力容量充足'],
  ['fire_confirmed', '消防条件已确认'],
];

type ApiErrorDetail = {
  message?: string;
  error_code?: string;
  provider?: string;
  endpoint?: string;
  status?: string;
  info?: string;
  infocode?: string;
  sanitized_params?: Record<string, unknown>;
  raw_response_sanitized?: Record<string, unknown>;
  retry_attempts?: unknown[];
};

function normalizeError(error: any): ApiErrorDetail {
  const detail = error?.response?.data?.detail;
  if (detail && typeof detail === 'object') return detail;
  if (typeof detail === 'string') return {message: detail};
  return {message: error?.message || '未知错误'};
}

function friendlyError(detail: ApiErrorDetail) {
  const code = detail.error_code || '';
  const infocode = detail.infocode || '';
  const info = detail.info || '';
  const text = detail.message || '';

  if (code === 'AMAP_KEY_MISSING' || text.includes('AMAP_WEB_SERVICE_KEY')) {
    return '后端未配置高德 Web 服务 Key，请检查 AMAP_WEB_SERVICE_KEY。';
  }
  if (code === 'AMAP_KEY_PERMISSION' || /KEY|USERKEY|INVALID/i.test(info)) {
    return '高德 Key 类型或接口权限可能不正确，请确认使用的是 Web 服务 API Key。';
  }
  if (code === 'AMAP_INVALID_ADDRESS' || code === 'AMAP_GEOCODE_EMPTY') {
    return '高德未能解析该地址，请补充省、市、区、街道或门牌号后重试。';
  }
  if (code === 'AMAP_ENGINE_RESPONSE_DATA_ERROR' || infocode === '30001') {
    return '高德服务响应失败，可能与地址格式、城市参数或高德服务侧响应有关。系统已尝试备用解析方式，请检查地址是否完整。';
  }
  if (code === 'AMAP_NETWORK_ERROR') {
    return '服务器无法访问高德接口，请检查服务器网络、防火墙或 DNS。';
  }
  return text || '未知问题，请复制诊断信息后排查。';
}

function sanitizedDiagnostics(detail: ApiErrorDetail) {
  return JSON.stringify(detail, (key, value) => {
    if (key.toLowerCase().includes('key')) return '***';
    return value;
  }, 2);
}

export default function NewEvaluation() {
  const [form] = Form.useForm();
  const [ev, setEv] = useState<Evaluation>();
  const [busy, setBusy] = useState('');
  const [error, setError] = useState<ApiErrorDetail | null>(null);
  const nav = useNavigate();

  const refresh = async (id: number) => setEv(await getEvaluation(id));

  const create = async (values: any) => {
    setBusy('正在保存候选地址');
    setError(null);
    try {
      const data = await createEvaluation({
        name: values.name,
        city: values.city,
        address: values.address,
        radius: values.radius,
        property: values,
      });
      setEv(data);
      message.success('候选地址已保存');
    } catch (e: any) {
      setError(normalizeError(e));
    } finally {
      setBusy('');
    }
  };

  const run = async (type: 'geo' | 'poi' | 'score') => {
    if (!ev) return;
    setBusy(type === 'geo' ? '正在定位地址' : type === 'poi' ? '正在采集周边 POI' : '正在计算评分');
    setError(null);
    try {
      if (type === 'geo') await geocode(ev.id);
      if (type === 'poi') await collectPois(ev.id);
      if (type === 'score') await score(ev.id);
      await refresh(ev.id);
    } catch (e: any) {
      setError(normalizeError(e));
    } finally {
      setBusy('');
    }
  };

  const copyDiagnostics = async () => {
    if (!error) return;
    await navigator.clipboard.writeText(sanitizedDiagnostics(error));
    message.success('诊断信息已复制');
  };

  return (
    <div className="workspace">
      <aside className="side left">
        <Form form={form} layout="vertical" onFinish={create} initialValues={{radius: 3000}}>
          <Collapse
            defaultActiveKey={['site', 'property']}
            ghost
            items={[
              {
                key: 'site',
                label: '候选地址',
                children: (
                  <>
                    <Form.Item name="name" label="评估名称" rules={[{required: true}]}>
                      <Input />
                    </Form.Item>
                    <div className="form-row">
                      <Form.Item name="city" label="城市" rules={[{required: true}]}>
                        <Input placeholder="例如：西安市" />
                      </Form.Item>
                      <Form.Item name="radius" label="搜索半径（米）">
                        <InputNumber min={100} max={50000} />
                      </Form.Item>
                    </div>
                    <Form.Item name="address" label="详细地址" rules={[{required: true}]}>
                      <Input.TextArea placeholder="例如：雁塔区小寨西路" />
                    </Form.Item>
                    <Button type="primary" htmlType="submit" block disabled={!!busy}>
                      保存候选地址
                    </Button>
                  </>
                ),
              },
              {
                key: 'property',
                label: '物业与租金',
                children: (
                  <>
                    <div className="form-row">
                      <Form.Item name="area_sqm" label="营业面积（㎡）">
                        <InputNumber />
                      </Form.Item>
                      <Form.Item name="monthly_rent" label="月租金（元）">
                        <InputNumber />
                      </Form.Item>
                    </div>
                    <Form.Item name="floor" label="楼层">
                      <Input />
                    </Form.Item>
                    {booleans.map(([key, label]) => (
                      <Form.Item key={key} name={key} label={label} valuePropName="checked">
                        <Switch />
                      </Form.Item>
                    ))}
                    <Form.Item name="notes" label="备注">
                      <Input.TextArea />
                    </Form.Item>
                  </>
                ),
              },
            ]}
          />
        </Form>
      </aside>

      <main>
        <MapPanel site={ev?.site} />
        <div className="actionbar">
          <Button onClick={() => run('geo')} disabled={!ev || !!busy}>1 定位地址</Button>
          <Button onClick={() => run('poi')} disabled={!ev?.site?.longitude || !!busy}>2 采集 POI</Button>
          <Button type="primary" onClick={() => run('score')} disabled={!ev || !!busy}>3 生成评分</Button>
          {ev?.result && <Button onClick={() => nav(`/reports/${ev.id}`)}>查看报告</Button>}
        </div>
        {busy && <div className="loading"><Spin /> {busy}</div>}
        {error && (
          <Alert
            type="error"
            showIcon
            message="操作失败"
            description={
              <Space direction="vertical">
                <span>{friendlyError(error)}</span>
                <Button size="small" onClick={copyDiagnostics}>复制诊断信息</Button>
              </Space>
            }
          />
        )}
        <Card size="small" title={`周边 POI ${ev?.pois?.length || 0} 条`} className="poi-table">
          <Table
            size="small"
            rowKey="id"
            pagination={{pageSize: 6}}
            dataSource={ev?.pois || []}
            columns={[
              {title: '名称', dataIndex: 'name'},
              {title: '分类', dataIndex: 'category', render: value => <Tag>{value}</Tag>},
              {title: '距离', dataIndex: 'distance_m', render: value => value ? `${value}m` : '待核实'},
              {title: '来源', dataIndex: 'source'},
            ]}
          />
        </Card>
      </main>

      <aside className="side right">
        <Card title="风险摘要" size="small">
          {ev?.result?.hard_risks.length ? (
            <Alert
              type="error"
              showIcon
              message="发现硬性风险"
              description={ev.result.hard_risks.map(item => <div key={item.message}>{item.message}</div>)}
            />
          ) : (
            <Alert type="info" message="完成评分后显示合规初筛结果" />
          )}
        </Card>
        <Card title="综合评分" size="small">
          <div className="score">{ev?.result?.total_score ?? '--'}<small>/ 100</small></div>
          <strong>{ev?.result?.recommendation || '尚未评分'}</strong>
        </Card>
        <Card title="数据质量" size="small">
          <span>完整度</span>
          <Progress percent={ev?.result?.completeness || 0} />
          <span>整体可信度</span>
          <Progress percent={ev?.result?.confidence || 0} />
        </Card>
      </aside>
    </div>
  );
}
