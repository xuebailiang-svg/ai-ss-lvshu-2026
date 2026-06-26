import {useEffect, useMemo, useState} from 'react';
import {useNavigate, useParams} from 'react-router-dom';
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
  Select,
  Space,
  Spin,
  Switch,
  Table,
  Tag,
  Tooltip,
  Upload,
  message,
} from 'antd';
import type {Evaluation, PoiPublic, PoiTemplates, PropertySurvey} from '../types';
import {
  collectPois,
  createManualPoi,
  createEvaluation,
  exportPoisUrl,
  geocode,
  getEvaluation,
  importPoisCsv,
  listPois,
  poiTemplates,
  savePoiEnrichment,
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
const CURRENT_EVALUATION_KEY = 'm2a:current-evaluation-id';

const fallbackTemplateCategories = ['竞品', '住宅', '交通', '娱乐', '餐饮', '夜间配套', '敏感场所', '物业线索', '其他'];

const fieldUnits: Record<string, string> = {
  distance_m: '米',
  walking_distance_m: '米',
  walking_time_min: '分钟',
  normal_price: '元/小时',
  premium_price: '元/小时',
  private_room_price: '元/小时',
  member_price: '元/小时',
  night_package_price: '元/包时',
  avg_spend: '元/人',
  area_sqm: '㎡',
  machine_count: '台',
  parking_space_count: '个/位',
  review_count: '条',
  monthly_sales: '单/月',
  annual_sales: '单/年',
};

const numericFields = new Set([
  'distance_m', 'walking_distance_m', 'walking_time_min', 'normal_price', 'premium_price',
  'private_room_price', 'member_price', 'night_package_price', 'avg_spend', 'area_sqm',
  'machine_count', 'parking_space_count', 'review_count', 'monthly_sales', 'annual_sales',
  'opening_years', 'monitor_size_inch', 'monitor_refresh_rate', 'online_rating',
  'reservation_rate', 'weekday_daytime_occupancy', 'weekday_evening_occupancy',
  'weekend_daytime_occupancy', 'weekend_evening_occupancy', 'estimated_population',
  'young_population_18_35',
]);

const enumOptions: Record<string, string[]> = {
  street_facing: ['是', '否', '未知'],
  visible_signboard: ['醒目', '一般', '不醒目', '未知'],
  is_chain: ['是', '否', '未知'],
  decoration_level: ['高', '中', '低', '未知'],
  foot_traffic_level: ['高', '中', '低', '未知'],
  consumption_level: ['高', '中', '低', '未知'],
  night_open: ['是', '否', '未知'],
  open_24h: ['是', '否', '未知'],
  matches_esports_users: ['匹配', '一般', '不匹配', '未知'],
  suitable_for_esports_users: ['匹配', '一般', '不匹配', '未知'],
  night_accessible: ['方便', '一般', '不方便', '未知'],
  has_viaduct_barrier: ['是', '否', '未知'],
  has_railway_barrier: ['是', '否', '未知'],
  has_river_barrier: ['是', '否', '未知'],
  has_greenbelt_barrier: ['是', '否', '未知'],
  parking_fee_unit: ['元/小时', '元/次', '免费', '未知'],
  night_parking_supported: ['是', '否', '未知'],
  easy_to_fill: ['是', '否', '未知'],
  entrance_convenient: ['方便', '一般', '不方便', '未知'],
  within_200m: ['是', '否', '未知'],
  needs_onsite_review: ['是', '否', '未知'],
  young_renters_main: ['是', '否', '未知'],
  relocation_housing: ['是', '否', '未知'],
  is_apartment: ['是', '否', '未知'],
  urban_village: ['是', '否', '未知'],
};

const timeLikeFields = new Set(['business_hours', 'first_service_time', 'last_service_time', 'opened_at', 'peak_period']);

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
  const {id: routeEvaluationId} = useParams();
  const [form] = Form.useForm();
  const [poiForm] = Form.useForm();
  const [manualPoiForm] = Form.useForm();
  const [ev, setEv] = useState<Evaluation>();
  const [poiRows, setPoiRows] = useState<PoiPublic[]>([]);
  const [templates, setTemplates] = useState<PoiTemplates>();
  const [poiStats, setPoiStats] = useState<Record<string, Record<string, number | string>>>({});
  const [busy, setBusy] = useState('');
  const [error, setError] = useState<ApiErrorDetail | null>(null);
  const [editingPoi, setEditingPoi] = useState<PoiPublic | null>(null);
  const [manualPoiOpen, setManualPoiOpen] = useState(false);
  const nav = useNavigate();
  const editCategory = Form.useWatch('business_category', poiForm) || editingPoi?.business_category;
  const manualCategory = Form.useWatch('business_category', manualPoiForm) || '竞品';

  useEffect(() => {
    poiTemplates().then(setTemplates).catch(() => message.warning('POI 模板加载失败，分类编辑功能可能不可用'));
  }, []);

  useEffect(() => {
    const idFromRoute = routeEvaluationId ? Number(routeEvaluationId) : undefined;
    const idFromStorage = Number(localStorage.getItem(CURRENT_EVALUATION_KEY) || '');
    const targetId = idFromRoute || idFromStorage;
    if (targetId && Number.isFinite(targetId)) {
      void refresh(targetId);
    }
  }, [routeEvaluationId]);

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

  const loadPoiRows = async (id: number) => {
    const data = await listPois(id);
    setPoiRows(data.items);
    setPoiStats(data.statistics || {});
    return data.items;
  };

  const refresh = async (id: number) => {
    const data = await getEvaluation(id);
    setEv(data);
    localStorage.setItem(CURRENT_EVALUATION_KEY, String(data.id));
    if (data.site?.property) form.setFieldsValue(data.site.property);
    await loadPoiRows(id);
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
        localStorage.setItem(CURRENT_EVALUATION_KEY, String(data.id));
        nav(`/evaluations/${data.id}`, {replace: true});
        await loadPoiRows(data.id);
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

  const categoryOptions = Object.keys(templates?.categories || {}).length
    ? Object.keys(templates?.categories || {})
    : fallbackTemplateCategories;

  const openPoiEditor = (poi: PoiPublic) => {
    setEditingPoi(poi);
    poiForm.setFieldsValue({
      ...(poi.supplement || {}),
      name: poi.name,
      business_category: poi.business_category,
      subcategory: poi.subcategory,
      address: poi.address,
      distance_m: poi.distance_m,
      walking_distance_m: poi.walking_distance_m,
      walking_time_min: poi.walking_time_min,
      data_source: poi.data_source || '人工',
      verification_status: poi.verification_status || '未核实',
      notes: poi.notes,
    });
  };

  const collectTemplatePayload = (values: Record<string, any>, category: string) => {
    const fields = templates?.categories?.[category]?.fields || [];
    const payload: Record<string, any> = {};
    fields.forEach(field => {
      if (values[field.key] !== undefined && values[field.key] !== '') payload[field.key] = values[field.key];
    });
    return payload;
  };

  const savePoi = async (values: Record<string, any>) => {
    if (!editingPoi || !ev) return;
    const category = values.business_category || editingPoi.business_category;
    await savePoiEnrichment(ev.id, editingPoi.poi_id, {
      name: values.name,
      business_category: category,
      subcategory: values.subcategory,
      address: values.address,
      distance_m: values.distance_m,
      walking_distance_m: values.walking_distance_m,
      walking_time_min: values.walking_time_min,
      data_source: values.data_source || '人工',
      verification_status: values.verification_status || '未核实',
      notes: values.notes,
      payload: collectTemplatePayload(values, category),
    });
    await loadPoiRows(ev.id);
    setEditingPoi(null);
    message.success('POI 补充信息已保存');
  };

  const saveManualPoi = async (values: Record<string, any>) => {
    if (!ev) return;
    const category = values.business_category || '其他';
    await createManualPoi(ev.id, {
      ...values,
      business_category: category,
      data_source: values.data_source || '人工',
      verification_status: values.verification_status || '未核实',
      payload: collectTemplatePayload(values, category),
    });
    await loadPoiRows(ev.id);
    setManualPoiOpen(false);
    manualPoiForm.resetFields();
    message.success('人工 POI 已新增');
  };

  const importCsv = async (categoryKey: string, file: File) => {
    if (!ev) return false;
    const text = await file.text();
    const result = await importPoisCsv(ev.id, categoryKey, text);
    await loadPoiRows(ev.id);
    if (result.failed_count) {
      message.warning(`CSV 导入完成：成功 ${result.success_count} 行，失败 ${result.failed_count} 行`);
    } else {
      message.success(`CSV 导入完成：成功 ${result.success_count} 行`);
    }
    return false;
  };

  const copyDiagnostics = async () => {
    if (!error) return;
    await navigator.clipboard.writeText(sanitizedDiagnostics(error));
    message.success('诊断信息已复制');
  };

  const competitorCount = poiRows.filter(poi => poi.business_category === '竞品').length;
  const verifiedCompetitorCount = poiRows.filter(poi => poi.business_category === '竞品' && poi.verification_status === '已人工核实').length;
  const groupedPois = useMemo(() => {
    const sortByDistance = (items: PoiPublic[]) => [...items].sort((a, b) => {
      const da = typeof a.distance_m === 'number' ? a.distance_m : Number.MAX_SAFE_INTEGER;
      const db = typeof b.distance_m === 'number' ? b.distance_m : Number.MAX_SAFE_INTEGER;
      return da - db || a.name.localeCompare(b.name);
    });
    return categoryOptions.map(category => {
      const cfg = templates?.categories?.[category];
      return {
        key: cfg?.export_key || category,
        category,
        title: category,
        exportKey: cfg?.export_key || category,
        items: sortByDistance(poiRows.filter(poi => poi.business_category === category)),
      };
    });
  }, [categoryOptions, poiRows, templates]);

  const poiColumns = [
    {title: '名称', dataIndex: 'name'},
    {title: '业务类别', dataIndex: 'business_category', render: (value: string) => <Tag color={value === '竞品' ? 'red' : 'blue'}>{value}</Tag>},
    {title: '细分类', dataIndex: 'subcategory', render: (value?: string) => value || '待补充'},
    {title: '地址', dataIndex: 'address', render: (value?: string) => value || '待补充'},
    {title: '直线距离', dataIndex: 'distance_m', render: (value?: number) => value ? `${value}m` : '待核实'},
    {title: '步行距离', dataIndex: 'walking_distance_m', render: (value?: number) => value ? `${value}m` : '待补充'},
    {title: '步行时间', dataIndex: 'walking_time_min', render: (value?: number) => value ? `${value}分钟` : '待补充'},
    {title: '数据来源', dataIndex: 'data_source', render: (value?: string) => <Tag>{value || '未标注'}</Tag>},
    {title: '核实状态', dataIndex: 'verification_status', render: (value?: string) => <Tag color={value === '已人工核实' ? 'green' : 'orange'}>{value || '未核实'}</Tag>},
    {title: '待补充项', dataIndex: 'missing_items_text', render: (value?: string) => value || '资料较完整'},
    {title: '备注', dataIndex: 'notes', render: (value?: string) => value || '-'},
    {title: '操作', render: (_: unknown, row: PoiPublic) => <Button size="small" onClick={() => openPoiEditor(row)}>编辑补充</Button>},
  ];

  const clearDraft = () => {
    localStorage.removeItem(DRAFT_KEY);
    localStorage.removeItem(CURRENT_EVALUATION_KEY);
    setEv(undefined);
    setPoiRows([]);
    setPoiStats({});
    form.resetFields();
    nav('/', {replace: true});
    message.success('草稿已清空');
  };

  const renderPoiSupplementFields = (category?: string, formInstance = poiForm) => {
    const subcategory = formInstance.getFieldValue('subcategory') || editingPoi?.subcategory;
    const cfg = templates?.categories?.[category || ''];
    const subtypeKeys = Object.entries(cfg?.subtype_templates || {}).find(([name]) => String(subcategory || '').includes(name) || name.includes(String(subcategory || '')))?.[1];
    const fields = (cfg?.fields || []).filter(field => !subtypeKeys || field.key === 'notes' || subtypeKeys.includes(field.key));
    if (!fields.length) {
      return <Alert type="info" showIcon message="该分类暂无专用模板字段，可先填写基础信息和备注。" />;
    }
    return fields.map(field => (
      <Form.Item key={field.key} name={field.key} label={field.label}>
        {renderPoiFieldControl(field.key)}
      </Form.Item>
    ));
  };

  const renderPoiFieldControl = (key: string) => {
    if (key === 'notes') return <Input.TextArea />;
    if (enumOptions[key]) {
      return <Select options={enumOptions[key].map(value => ({label: value, value}))} />;
    }
    if (numericFields.has(key)) {
      return <InputNumber min={0} step={key.includes('rate') || key.includes('rating') ? 0.1 : 1} addonAfter={fieldUnits[key]} style={{width: '100%'}} />;
    }
    if (timeLikeFields.has(key)) {
      return <Input placeholder={key === 'opened_at' ? '例如：2023-05 或 2023' : '例如：10:00-02:00，支持跨天'} />;
    }
    return <Input />;
  };

  const renderBasePoiFormItems = () => (
    <>
      <Form.Item name="name" label="名称" rules={[{required: true, message: '请填写名称'}]}>
        <Input />
      </Form.Item>
      <div className="form-row">
        <Form.Item name="business_category" label="业务类别" rules={[{required: true, message: '请选择业务类别'}]}>
          <Select options={categoryOptions.map(category => ({label: category, value: category}))} />
        </Form.Item>
        <Form.Item name="subcategory" label="细分类">
          <Input />
        </Form.Item>
      </div>
      <Form.Item name="address" label="地址">
        <Input.TextArea />
      </Form.Item>
      <div className="form-row">
        <Form.Item name="distance_m" label="直线距离（米）">
          <InputNumber min={0} addonAfter="米" style={{width: '100%'}} />
        </Form.Item>
        <Form.Item name="walking_distance_m" label="步行距离（米）">
          <InputNumber min={0} addonAfter="米" style={{width: '100%'}} />
        </Form.Item>
      </div>
      <div className="form-row">
        <Form.Item name="walking_time_min" label="步行时间（分钟）">
          <InputNumber min={0} addonAfter="分钟" style={{width: '100%'}} />
        </Form.Item>
        <Form.Item name="data_source" label="数据来源">
          <Input placeholder="例如：现场调研/电话核实/大众点评" />
        </Form.Item>
      </div>
      <Form.Item name="verification_status" label="核实状态">
        <Select options={[{label: '未核实', value: '未核实'}, {label: '已人工核实', value: '已人工核实'}, {label: '待复核', value: '待复核'}]} />
      </Form.Item>
      <Form.Item name="notes" label="备注">
        <Input.TextArea />
      </Form.Item>
    </>
  );

  const renderStats = (category: string) => {
    const stats = poiStats[category] || (category === '餐饮' ? poiStats['餐饮/夜间配套'] : undefined);
    if (!stats) return <Alert type="info" showIcon message="该分类暂无统计数据" description="未采集或未补充的数据不会参与统计。" />;
    return (
      <Space wrap>
        {Object.entries(stats).map(([label, value]) => (
          <Tag key={label} color="geekblue">{label}：{value ?? '未补充'}</Tag>
        ))}
      </Space>
    );
  };

  return (
    <div className="workspace">
      <aside className="side left">
        <Form
          form={form}
          layout="vertical"
          onFinish={create}
          initialValues={{radius: 3000}}
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
                    <Form.Item name="surveyed_at" label="调查时间"><Input placeholder="例如：2026-06-23" /></Form.Item>
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
          <Button style={{marginTop: 8}} block onClick={clearDraft}>
            {ev ? '新建评估 / 清空当前' : '清空草稿'}
          </Button>
        </Form>
      </aside>

      <main>
        <MapPanel site={ev?.site} />
        <div className="actionbar">
          <Button onClick={() => run('geo')} disabled={!ev || !!busy}>1 定位地址</Button>
          <Button onClick={() => run('poi')} disabled={!ev?.site?.longitude || !!busy}>2 采集 POI</Button>
          <Button type="primary" onClick={() => run('score')} disabled={!ev || !!busy}>3 生成评分/报告</Button>
          <Tooltip title={ev?.result ? '打开本次评估报告' : '请先点击“3 生成评分/报告”'}>
            <Button onClick={() => ev && nav(`/reports/${ev.id}`)} disabled={!ev?.result || !!busy}>4 查看报告</Button>
          </Tooltip>
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
        <Card
          size="small"
          title={`周边 POI ${poiRows.length} 条`}
          extra={<Button size="small" disabled={!ev} onClick={() => { manualPoiForm.resetFields(); manualPoiForm.setFieldsValue({business_category: '竞品', data_source: '人工', verification_status: '未核实'}); setManualPoiOpen(true); }}>新增人工 POI</Button>}
          className="poi-table"
        >
          <Space wrap style={{marginBottom: 8}}>
            {groupedPois.map(group => (
              <Tag key={group.key} color={group.items.length ? 'blue' : undefined}>
                {group.title}：{group.items.length ? `${group.items.length} 条` : '未采集到'}
              </Tag>
            ))}
          </Space>
          <Collapse
            size="small"
            defaultActiveKey={['competitor', 'traffic', 'food', 'residential']}
            items={groupedPois.map(group => ({
              key: group.key,
              label: `${group.title}（${group.items.length ? `${group.items.length} 条` : '未采集到'}）`,
              children: (
                <Space direction="vertical" style={{width: '100%'}}>
                  {renderStats(group.category)}
                  <Space wrap>
                    <Button size="small" disabled={!ev} onClick={() => ev && window.open(exportPoisUrl(ev.id, group.exportKey), '_blank')}>
                      导出 CSV
                    </Button>
                    <Upload
                      accept=".csv,text/csv"
                      showUploadList={false}
                      beforeUpload={file => {
                        void importCsv(group.exportKey, file);
                        return false;
                      }}
                    >
                      <Button size="small" disabled={!ev}>导入 CSV</Button>
                    </Upload>
                  </Space>
                  {group.items.length ? (
                    <Table
                      size="small"
                      rowKey="poi_id"
                      pagination={{pageSize: 5}}
                      dataSource={group.items}
                      columns={poiColumns}
                      scroll={{x: 1200}}
                    />
                  ) : (
                    <Alert type="info" showIcon message={`${group.title}未采集到`} description="这不代表周边不存在该类 POI，建议扩大半径或现场复核。" />
                  )}
                </Space>
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
          <p>竞品人工核实：{verifiedCompetitorCount}/{competitorCount}</p>
        </Card>
      </aside>

      <Drawer title={editingPoi?.name ? `编辑 POI：${editingPoi.name}` : '编辑 POI'} open={!!editingPoi} width={560} onClose={() => setEditingPoi(null)}>
        <Alert type="info" showIcon message="基础 POI 与人工补充数据分层保存" description="本表单只展示客户可理解、可补充的业务字段，不展示技术字段。" />
        <Form form={poiForm} layout="vertical" onFinish={savePoi} initialValues={{data_source: '人工', verification_status: '未核实'}}>
          {renderBasePoiFormItems()}
          {renderPoiSupplementFields(editCategory, poiForm)}
          <Button type="primary" htmlType="submit" block>保存 POI 补充信息</Button>
        </Form>
      </Drawer>

      <Drawer title="新增人工 POI" open={manualPoiOpen} width={560} onClose={() => setManualPoiOpen(false)}>
        <Alert type="info" showIcon message="人工新增 POI 可只填写业务字段" description="新增后会保存到当前评估，刷新页面和历史记录中仍可查看。" />
        <Form form={manualPoiForm} layout="vertical" onFinish={saveManualPoi} initialValues={{business_category: '竞品', data_source: '人工', verification_status: '未核实'}}>
          {renderBasePoiFormItems()}
          {renderPoiSupplementFields(manualCategory, manualPoiForm)}
          <Button type="primary" htmlType="submit" block>新增人工 POI</Button>
        </Form>
      </Drawer>
    </div>
  );
}
