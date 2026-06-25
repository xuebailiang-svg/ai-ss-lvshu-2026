import {useEffect, useMemo, useState} from 'react';
import {useNavigate} from 'react-router-dom';
import {
  Alert,
  Button,
  Card,
  Collapse,
  Drawer,
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
import type {CompetitorEnrichment, Evaluation, Poi, PropertySurvey} from '../types';
import {
  collectPois,
  createEvaluation,
  geocode,
  getEvaluation,
  saveCompetitorEnrichment,
  score,
  updateProperty,
} from '../api/client';
import MapPanel from '../components/MapPanel';

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

const propertySwitches: [keyof PropertySurvey, string][] = [
  ['street_facing', '是否临街'],
  ['night_entrance', '独立夜间出入口'],
  ['use_allowed', '允许电竞馆/网咖业态'],
  ['power_sufficient', '供电容量充足'],
  ['power_expansion_allowed', '允许增容'],
  ['dual_line_supported', '支持双线路'],
  ['fire_confirmed', '消防条件已确认'],
  ['sprinkler', '有喷淋'],
  ['smoke_exhaust', '有排烟'],
];

const DRAFT_KEY = 'm15:new-evaluation:draft';

const poiDisplayGroups = [
  {key: 'competitors', title: '竞品', categories: ['竞品']},
  {key: 'sensitive', title: '敏感场所', categories: ['小学', '中学', '幼儿园', '敏感场所']},
  {key: 'traffic', title: '交通', categories: ['交通']},
  {key: 'commercial', title: '商业配套', categories: ['商业配套']},
  {key: 'population', title: '人口代理', categories: ['住宅小区', '公寓', '宿舍', '写字楼', '大学', '中职', '技校']},
  {key: 'other', title: '其他', categories: ['其他']},
];

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
  if (code === 'AMAP_KEY_MISSING' || text.includes('AMAP_WEB_SERVICE_KEY')) return '后端未配置高德 Web 服务 Key，请检查 AMAP_WEB_SERVICE_KEY。';
  if (code === 'AMAP_KEY_PERMISSION' || /KEY|USERKEY|INVALID/i.test(info)) return '高德 Key 类型或接口权限可能不正确，请确认使用的是 Web 服务 API Key。';
  if (code === 'AMAP_INVALID_ADDRESS' || code === 'AMAP_GEOCODE_EMPTY') return '高德未能解析该地址，请补充省、市、区、街道或门牌号后重试。';
  if (code === 'AMAP_ENGINE_RESPONSE_DATA_ERROR' || infocode === '30001') return '高德服务响应失败，可能与地址格式、城市参数或高德服务侧响应有关。系统已尝试备用解析方式，请检查地址是否完整。';
  if (code === 'AMAP_NETWORK_ERROR') return '服务器无法访问高德接口，请检查服务器网络、防火墙或 DNS。';
  return text || '未知问题，请复制诊断信息后排查。';
}

function sanitizedDiagnostics(detail: ApiErrorDetail) {
  return JSON.stringify(detail, (key, value) => (key.toLowerCase().includes('key') ? '***' : value), 2);
}

export default function NewEvaluation() {
  const [form] = Form.useForm();
  const [competitorForm] = Form.useForm<CompetitorEnrichment>();
  const [ev, setEv] = useState<Evaluation>();
  const [busy, setBusy] = useState('');
  const [error, setError] = useState<ApiErrorDetail | null>(null);
  const [competitor, setCompetitor] = useState<Poi | null>(null);
  const nav = useNavigate();

  useEffect(() => {
    const raw = localStorage.getItem(DRAFT_KEY);
    if (!raw) return;
    try {
      form.setFieldsValue(JSON.parse(raw));
      message.info('已恢复上次未保存的新地址评估草稿');
    } catch {
      localStorage.removeItem(DRAFT_KEY);
    }
  }, [form]);

  const refresh = async (id: number) => {
    const data = await getEvaluation(id);
    setEv(data);
    if (data.site?.property) form.setFieldsValue(data.site.property);
    return data;
  };

  const create = async (values: any) => {
    setBusy(ev ? '正在保存物业调查' : '正在保存候选地址');
    setError(null);
    try {
      if (!ev) {
        const data = await createEvaluation({
          name: values.name,
          city: values.city,
          address: values.address,
          radius: values.radius || 3000,
          property: values,
        });
        setEv(data);
        localStorage.removeItem(DRAFT_KEY);
        message.success('候选地址已保存');
      } else {
        await updateProperty(ev.id, values);
        await refresh(ev.id);
        message.success('物业调查已保存');
      }
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

  const openCompetitor = (poi: Poi) => {
    setCompetitor(poi);
    competitorForm.setFieldsValue({
      ...(poi.enrichment || {}),
      confidence: poi.enrichment?.confidence ?? 0.5,
    });
  };

  const saveCompetitor = async (values: CompetitorEnrichment) => {
    if (!competitor || !ev) return;
    await saveCompetitorEnrichment(competitor.id, values);
    await refresh(ev.id);
    setCompetitor(null);
    message.success('竞品调研已保存');
  };

  const copyDiagnostics = async () => {
    if (!error) return;
    await navigator.clipboard.writeText(sanitizedDiagnostics(error));
    message.success('诊断信息已复制');
  };

  const competitorCount = ev?.pois?.filter(poi => poi.category === '竞品').length || 0;
  const verifiedCompetitorCount = ev?.pois?.filter(poi => poi.category === '竞品' && (poi.enrichment?.is_manually_verified || poi.enrichment?.verified_at)).length || 0;
  const groupedPois = useMemo(() => {
    const pois = ev?.pois || [];
    return poiDisplayGroups.map(group => ({
      ...group,
      items: pois.filter(poi => group.categories.includes(poi.category)),
    }));
  }, [ev?.pois]);

  const poiColumns = [
    {title: '名称', dataIndex: 'name'},
    {title: '分类', dataIndex: 'category', render: (value: string) => <Tag color={value === '竞品' ? 'red' : undefined}>{value}</Tag>},
    {title: '类型码', dataIndex: 'type_code', render: (value?: string) => value || '-'},
    {title: '距离', dataIndex: 'distance_m', render: (value?: number) => value ? `${value}m` : '待核实'},
    {title: '可信度', dataIndex: 'confidence', render: (value?: number) => <Tag>{Math.round((value || 0) * 100)}%</Tag>},
    {title: '人工数据', render: (_: unknown, row: Poi) => row.enrichment ? <Tag color="green">已补充</Tag> : row.category === '竞品' ? <Tag color="orange">待调研</Tag> : '-'},
    {title: '操作', render: (_: unknown, row: Poi) => row.category === '竞品' ? <Button size="small" onClick={() => openCompetitor(row)}>竞品调研</Button> : null},
  ];

  const clearDraft = () => {
    localStorage.removeItem(DRAFT_KEY);
    form.resetFields();
    message.success('草稿已清空');
  };

  return (
    <div className="workspace">
      <aside className="side left">
        <Form
          form={form}
          layout="vertical"
          onFinish={create}
          initialValues={{radius: 3000, confidence: 0.5}}
          onValuesChange={(_, values) => {
            if (!ev) localStorage.setItem(DRAFT_KEY, JSON.stringify(values));
          }}
        >
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
                      <Input disabled={!!ev} />
                    </Form.Item>
                    <div className="form-row">
                      <Form.Item name="city" label="城市" rules={[{required: true}]}>
                        <Input disabled={!!ev} placeholder="例如：西安市" />
                      </Form.Item>
                      <Form.Item name="radius" label="搜索半径（米）">
                        <InputNumber min={100} max={50000} disabled={!!ev} />
                      </Form.Item>
                    </div>
                    <Form.Item name="address" label="详细地址" rules={[{required: true}]}>
                      <Input.TextArea disabled={!!ev} placeholder="例如：雁塔区小寨西路" />
                    </Form.Item>
                  </>
                ),
              },
              {
                key: 'property',
                label: '物业调查表',
                children: (
                  <>
                    <div className="form-row">
                      <Form.Item name="area_sqm" label="建筑面积（㎡）"><InputNumber min={0} /></Form.Item>
                      <Form.Item name="usable_area_sqm" label="实际使用面积（㎡）"><InputNumber min={0} /></Form.Item>
                    </div>
                    <div className="form-row">
                      <Form.Item name="floor" label="楼层"><Input /></Form.Item>
                      <Form.Item name="floor_height_m" label="层高（米）"><InputNumber min={0} /></Form.Item>
                    </div>
                    <div className="form-row">
                      <Form.Item name="monthly_rent" label="月租金（元）"><InputNumber min={0} /></Form.Item>
                      <Form.Item name="rent_per_sqm_day" label="元/㎡/天"><InputNumber min={0} /></Form.Item>
                    </div>
                    <div className="form-row">
                      <Form.Item name="property_fee_monthly" label="物业费/月"><InputNumber min={0} /></Form.Item>
                      <Form.Item name="transfer_fee" label="转让费"><InputNumber min={0} /></Form.Item>
                    </div>
                    <div className="form-row">
                      <Form.Item name="deposit" label="押金"><InputNumber min={0} /></Form.Item>
                      <Form.Item name="rent_free_months" label="免租期（月）"><InputNumber min={0} /></Form.Item>
                    </div>
                    <div className="form-row">
                      <Form.Item name="lease_term_months" label="租期（月）"><InputNumber min={0} /></Form.Item>
                      <Form.Item name="rent_escalation" label="租金递增"><Input /></Form.Item>
                    </div>
                    <div className="form-row">
                      <Form.Item name="power_capacity_kw" label="供电容量（kW）"><InputNumber min={0} /></Form.Item>
                      <Form.Item name="network_carriers" label="网络运营商"><Input /></Form.Item>
                    </div>
                    <div className="form-row">
                      <Form.Item name="safety_exit_count" label="安全出口数量"><InputNumber min={0} /></Form.Item>
                      <Form.Item name="parking_condition" label="停车条件"><Input /></Form.Item>
                    </div>
                    <div className="form-row">
                      <Form.Item name="facade_width_m" label="门头宽度（米）"><InputNumber min={0} /></Form.Item>
                      <Form.Item name="facade_visibility" label="门头可见性"><Input /></Form.Item>
                    </div>
                    <Form.Item name="noise_complaint_risk" label="噪声投诉风险"><Input /></Form.Item>
                    <Form.Item name="required_rectifications" label="需要整改事项"><Input.TextArea /></Form.Item>
                    <Form.Item name="property_contact" label="物业联系人"><Input /></Form.Item>
                    <div className="form-row">
                      <Form.Item name="machine_count" label="规划机器数量"><InputNumber min={0} /></Form.Item>
                      <Form.Item name="source" label="数据来源"><Input /></Form.Item>
                    </div>
                    <div className="form-row">
                      <Form.Item name="surveyed_at" label="调查时间"><Input placeholder="例如：2026-06-23" /></Form.Item>
                      <Form.Item name="confidence" label="可信度（0-1）"><InputNumber min={0} max={1} step={0.05} /></Form.Item>
                    </div>
                    <div className="switch-grid">
                      {propertySwitches.map(([key, label]) => (
                        <Form.Item key={key} name={key} label={label} valuePropName="checked">
                          <Switch />
                        </Form.Item>
                      ))}
                    </div>
                    <Form.Item name="notes" label="备注"><Input.TextArea /></Form.Item>
                  </>
                ),
              },
            ]}
          />
          <Button type="primary" htmlType="submit" block disabled={!!busy}>
            {ev ? '保存物业调查' : '保存候选地址'}
          </Button>
          {!ev && (
            <Button style={{marginTop: 8}} block onClick={clearDraft}>
              清空草稿
            </Button>
          )}
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
            description={<Space direction="vertical"><span>{friendlyError(error)}</span><Button size="small" onClick={copyDiagnostics}>复制诊断信息</Button></Space>}
          />
        )}
        <Card size="small" title={`周边 POI ${ev?.pois?.length || 0} 条`} className="poi-table">
          <Space wrap style={{marginBottom: 8}}>
            {groupedPois.map(group => (
              <Tag key={group.key} color={group.items.length ? 'blue' : undefined}>
                {group.title}：{group.items.length ? `${group.items.length} 条` : '未采集到'}
              </Tag>
            ))}
          </Space>
          <Collapse
            size="small"
            defaultActiveKey={['competitors', 'traffic', 'commercial']}
            items={groupedPois.map(group => ({
              key: group.key,
              label: `${group.title}（${group.items.length ? `${group.items.length} 条` : '未采集到'}）`,
              children: group.items.length ? (
                <Table
                  size="small"
                  rowKey="id"
                  pagination={{pageSize: 5}}
                  dataSource={group.items}
                  columns={poiColumns}
                />
              ) : (
                <Alert type="info" showIcon message={`${group.title}未采集到`} description="这不代表周边不存在该类 POI，建议扩大半径或现场复核。" />
              ),
            }))}
          />
        </Card>
      </main>

      <aside className="side right">
        <Card title="风险摘要" size="small">
          {ev?.result?.hard_risks.length ? (
            <Alert type="error" showIcon message="发现硬性风险" description={ev.result.hard_risks.map(item => <div key={item.message}>{item.message}</div>)} />
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
          <p>竞品人工核实：{verifiedCompetitorCount}/{competitorCount}</p>
        </Card>
      </aside>

      <Drawer title={competitor?.name ? `竞品调研：${competitor.name}` : '竞品调研'} open={!!competitor} width={520} onClose={() => setCompetitor(null)}>
        <Alert type="info" showIcon message="高德基础 POI 与人工调研数据分层保存" description="上座率为人工估算时，报告会标注为估算值。" />
        <Form form={competitorForm} layout="vertical" onFinish={saveCompetitor} initialValues={{confidence: 0.5}}>
          <div className="form-row">
            <Form.Item name="machine_count" label="机器数量"><InputNumber min={0} /></Form.Item>
            <Form.Item name="area_sqm" label="营业面积（㎡）"><InputNumber min={0} /></Form.Item>
          </div>
          <div className="form-row">
            <Form.Item name="cpu" label="CPU"><Input /></Form.Item>
            <Form.Item name="gpu" label="显卡"><Input /></Form.Item>
          </div>
          <div className="form-row">
            <Form.Item name="monitor_size_inch" label="显示器尺寸"><InputNumber min={0} /></Form.Item>
            <Form.Item name="monitor_refresh_rate" label="刷新率"><InputNumber min={0} /></Form.Item>
          </div>
          <div className="form-row">
            <Form.Item name="normal_price" label="普通区价格"><InputNumber min={0} /></Form.Item>
            <Form.Item name="premium_price" label="高配区价格"><InputNumber min={0} /></Form.Item>
          </div>
          <div className="form-row">
            <Form.Item name="private_room_price" label="包间价格"><InputNumber min={0} /></Form.Item>
            <Form.Item name="member_price" label="会员价格"><InputNumber min={0} /></Form.Item>
          </div>
          <Form.Item name="recharge_promotion" label="充值优惠"><Input /></Form.Item>
          <div className="form-row">
            <Form.Item name="opened_at_estimate" label="推测开业时间"><Input /></Form.Item>
            <Form.Item name="opening_basis" label="开业时间依据"><Input /></Form.Item>
          </div>
          <div className="form-row">
            <Form.Item name="peak_occupancy_rate" label="高峰上座率（0-1）"><InputNumber min={0} max={1} step={0.05} /></Form.Item>
            <Form.Item name="offpeak_occupancy_rate" label="平峰上座率（0-1）"><InputNumber min={0} max={1} step={0.05} /></Form.Item>
          </div>
          <div className="form-row">
            <Form.Item name="surveyed_at" label="调查时间"><Input placeholder="例如：2026-06-23" /></Form.Item>
            <Form.Item name="survey_method" label="调查方式"><Input /></Form.Item>
          </div>
          <div className="form-row">
            <Form.Item name="source" label="数据来源"><Input /></Form.Item>
            <Form.Item name="confidence" label="可信度（0-1）"><InputNumber min={0} max={1} step={0.05} /></Form.Item>
          </div>
          <Form.Item name="is_manually_verified" label="是否人工核实" valuePropName="checked"><Switch /></Form.Item>
          <Form.Item name="notes" label="备注"><Input.TextArea /></Form.Item>
          <Button type="primary" htmlType="submit" block>保存竞品调研</Button>
        </Form>
      </Drawer>
    </div>
  );
}
