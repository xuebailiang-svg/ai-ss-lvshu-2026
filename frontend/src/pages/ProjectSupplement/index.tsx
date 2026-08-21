import {useEffect, useMemo, useState} from 'react';
import {
  Alert, Button, Card, Col, Descriptions, Form, Input, InputNumber, Modal, Row,
  Select, Space, Spin, Switch, Table, Tabs, Tag, Typography, message,
} from 'antd';
import {ArrowLeftOutlined, CheckOutlined, CloseOutlined, EditOutlined, SaveOutlined} from '@ant-design/icons';
import {useNavigate, useParams, useSearchParams} from 'react-router-dom';
import {submitManualInput} from '../../api/data';
import {
  getProjectCompetitor,
  getProjectDataset,
  getProjectRentDetail,
  getProjectSupportingDetail,
  listProjectCompetitors,
  listProjectRent,
  listProjectSupporting,
  reviewProjectCompetitor,
  reviewProjectRent,
  reviewProjectSupporting,
  updateProjectCompetitor,
  updateProjectRentDetail,
  updateProjectSupportingDetail,
  type ProjectCompetitor,
  type ProjectRentDetail,
  type ProjectRentItem,
  type ProjectSupportingDetail,
  type ProjectSupportingItem,
} from '../../api/projects';

const {TextArea} = Input;
const STATUS_VIEW: Record<string, {text: string; color: string}> = {
  pending_review: {text: '待核实', color: 'orange'},
  confirmed: {text: '已确认', color: 'green'},
  rejected: {text: '已排除', color: 'default'},
};

const YES_NO_UNKNOWN = [
  {value: true, label: '是'},
  {value: false, label: '否'},
];

const COMPETITOR_UNKNOWN_OPTIONS = [
  'area_sqm', 'machine_count', 'cpu', 'gpu', 'monitor', 'hour_price', 'member_price',
  'business_hours', 'opening_date', 'occupancy_rate', 'recharge_info',
].map(value => ({value, label: ({
  area_sqm: '面积', machine_count: '机器数量', cpu: 'CPU', gpu: '显卡', monitor: '显示器',
  hour_price: '小时价', member_price: '会员价', business_hours: '营业时间', opening_date: '开业时间',
  occupancy_rate: '现场上座率', recharge_info: '充值活动',
} as Record<string, string>)[value]}));

function StatusTag({status}: {status?: string}) {
  const view = STATUS_VIEW[status || ''] || {text: status || '未知', color: 'default'};
  return <Tag color={view.color}>{view.text}</Tag>;
}

function AuditText({meta}: {meta?: {verified_at?: string | null; history_count?: number; unknown_fields?: string[]}}) {
  if (!meta?.verified_at) return <Typography.Text type="secondary">尚未人工核实</Typography.Text>;
  return (
    <Typography.Text type="secondary">
      最近核实：{new Date(meta.verified_at).toLocaleString()} · 修改 {meta.history_count || 0} 次
      {(meta.unknown_fields?.length || 0) > 0 ? ` · ${meta.unknown_fields?.length} 项明确未知` : ''}
    </Typography.Text>
  );
}

function ReadonlySource({name, address, distance, source}: {name?: string; address?: string | null; distance?: number | null; source?: string}) {
  return (
    <Card size="small" title="高德基础信息（只读）" style={{marginBottom: 16}}>
      <Descriptions size="small" column={2}>
        <Descriptions.Item label="名称">{name || '-'}</Descriptions.Item>
        <Descriptions.Item label="距离">{distance == null ? '-' : `${distance} 米`}</Descriptions.Item>
        <Descriptions.Item label="地址" span={2}>{address || '-'}</Descriptions.Item>
        <Descriptions.Item label="数据来源"><Tag>{source === 'amap' ? '高德' : source || '-'}</Tag></Descriptions.Item>
      </Descriptions>
    </Card>
  );
}

export default function ProjectSupplementPage() {
  const {projectId = ''} = useParams();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const [activeTab, setActiveTab] = useState(searchParams.get('focus') === 'support' ? 'supporting' : searchParams.get('focus') === 'rent' || searchParams.get('focus') === 'property' ? 'property' : 'competitor');
  const [search, setSearch] = useState('');
  const [pendingOnly, setPendingOnly] = useState(true);
  const [loading, setLoading] = useState(true);
  const [competitors, setCompetitors] = useState<ProjectCompetitor[]>([]);
  const [supporting, setSupporting] = useState<ProjectSupportingItem[]>([]);
  const [rents, setRents] = useState<ProjectRentItem[]>([]);
  const [savingId, setSavingId] = useState<string>('');
  const [competitorModal, setCompetitorModal] = useState<ProjectCompetitor | null>(null);
  const [supportingModal, setSupportingModal] = useState<ProjectSupportingDetail | null>(null);
  const [rentModal, setRentModal] = useState<ProjectRentDetail | null>(null);
  const [competitorForm] = Form.useForm();
  const [supportingForm] = Form.useForm();
  const [rentForm] = Form.useForm();
  const [propertyForm] = Form.useForm();
  const [propertySaving, setPropertySaving] = useState(false);

  const loadAll = async () => {
    setLoading(true);
    try {
      const [competitorResult, supportingResult, rentResult, dataset] = await Promise.all([
        listProjectCompetitors(projectId), listProjectSupporting(projectId), listProjectRent(projectId), getProjectDataset(projectId),
      ]);
      setCompetitors(competitorResult.items || []);
      setSupporting(supportingResult.items || []);
      setRents(rentResult.items || []);
      const property = (dataset?.supplements || []).find((item: any) => item.target_type === 'candidate_property' && item.field_name === 'manual_detail');
      if (property?.value) propertyForm.setFieldsValue(property.value);
    } catch (error: any) {
      message.error(error?.response?.data?.detail || '人工核实数据加载失败');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { void loadAll(); }, [projectId]);

  const filterItems = <T extends {name?: string; address?: string | null; status?: string}>(items: T[]) => items.filter(item => {
    if (pendingOnly && item.status !== 'pending_review') return false;
    const keyword = search.trim().toLowerCase();
    return !keyword || `${item.name || ''} ${item.address || ''}`.toLowerCase().includes(keyword);
  });

  const filteredCompetitors = useMemo(() => filterItems(competitors), [competitors, pendingOnly, search]);
  const filteredSupporting = useMemo(() => filterItems(supporting), [supporting, pendingOnly, search]);

  const reviewCompetitor = async (item: ProjectCompetitor, status: 'confirmed' | 'rejected') => {
    setSavingId(`competitor:${item.id}`);
    try {
      const updated = await reviewProjectCompetitor(projectId, item.id, status);
      setCompetitors(rows => rows.map(row => row.id === item.id ? updated : row));
      message.success(status === 'confirmed' ? '已确认是真实竞品' : '已排除该疑似竞品');
    } catch { message.error('竞品核实状态保存失败'); }
    finally { setSavingId(''); }
  };

  const openCompetitor = async (item: ProjectCompetitor) => {
    setSavingId(`competitor-load:${item.id}`);
    try {
      const detail = await getProjectCompetitor(projectId, item.id);
      setCompetitorModal(detail);
      competitorForm.setFieldsValue({
        ...detail,
        occupancy_rate: detail.occupancy_rate == null ? undefined : detail.occupancy_rate * 100,
        unknown_fields: detail.manual_meta?.unknown_fields || [],
      });
    } catch { message.error('竞品详情加载失败'); }
    finally { setSavingId(''); }
  };

  const saveCompetitor = async () => {
    if (!competitorModal) return;
    try {
      const values = await competitorForm.validateFields();
      setSavingId(`competitor:${competitorModal.id}`);
      const updated = await updateProjectCompetitor(projectId, competitorModal.id, {
        ...values,
        occupancy_rate: values.occupancy_rate == null ? null : Number(values.occupancy_rate) / 100,
      });
      setCompetitors(rows => rows.map(row => row.id === updated.id ? updated : row));
      setCompetitorModal(null);
      message.success('竞品人工核实信息已保存');
    } catch (error: any) { if (!error?.errorFields) message.error('竞品详情保存失败'); }
    finally { setSavingId(''); }
  };

  const reviewSupportingItem = async (item: ProjectSupportingItem, status: 'confirmed' | 'rejected') => {
    setSavingId(item.id);
    try {
      const updated = await reviewProjectSupporting(projectId, item.id, status);
      setSupporting(rows => rows.map(row => row.id === item.id ? updated : row));
      message.success(status === 'confirmed' ? '配套商户已确认' : '配套商户已排除');
    } catch { message.error('配套核实状态保存失败'); }
    finally { setSavingId(''); }
  };

  const openSupporting = async (item: ProjectSupportingItem) => {
    if (item.status !== 'confirmed') {
      message.info('请先确认该商户真实有效，再补充营业详情');
      return;
    }
    setSavingId(`supporting-load:${item.id}`);
    try {
      const detail = await getProjectSupportingDetail(projectId, item.id);
      setSupportingModal(detail);
      supportingForm.setFieldsValue({...detail.manual_detail, unknown_fields: detail.manual_meta?.unknown_fields || []});
    } catch { message.error('配套详情加载失败'); }
    finally { setSavingId(''); }
  };

  const saveSupporting = async () => {
    if (!supportingModal) return;
    try {
      const values = await supportingForm.validateFields();
      setSavingId(supportingModal.id);
      const updated = await updateProjectSupportingDetail(projectId, supportingModal.id, values);
      setSupporting(rows => rows.map(row => row.id === updated.id ? updated : row));
      setSupportingModal(null);
      message.success('配套营业信息已保存');
    } catch (error: any) { if (!error?.errorFields) message.error('配套详情保存失败'); }
    finally { setSavingId(''); }
  };

  const openRent = async (item: ProjectRentItem) => {
    setSavingId(`rent-load:${item.id}`);
    try {
      const detail = await getProjectRentDetail(projectId, item.id);
      setRentModal(detail);
      rentForm.setFieldsValue({
        ...detail,
        ...detail.manual_detail,
        unknown_fields: detail.manual_meta?.unknown_fields || [],
      });
    } catch { message.error('租金详情加载失败'); }
    finally { setSavingId(''); }
  };

  const saveRent = async () => {
    if (!rentModal) return;
    try {
      const values = await rentForm.validateFields();
      setSavingId(`rent:${rentModal.id}`);
      const updated = await updateProjectRentDetail(projectId, rentModal.id, values);
      setRents(rows => rows.map(row => row.id === updated.id ? updated : row));
      setRentModal(null);
      message.success('租金与物业详情已保存');
    } catch (error: any) { if (!error?.errorFields) message.error('租金详情保存失败'); }
    finally { setSavingId(''); }
  };

  const saveProperty = async () => {
    try {
      const values = await propertyForm.validateFields();
      setPropertySaving(true);
      await submitManualInput(projectId, {type: 'property', target_id: 'primary', data: values});
      message.success('候选物业信息已保存');
    } catch (error: any) {
      if (!error?.errorFields) message.error(error?.response?.data?.detail || '候选物业保存失败');
    } finally { setPropertySaving(false); }
  };

  const competitorColumns = [
    {title: '疑似竞品', key: 'name', render: (_: unknown, item: ProjectCompetitor) => <Space direction="vertical" size={2}><Typography.Text strong>{item.name}</Typography.Text><Typography.Text type="secondary">{item.address || '高德未提供地址'}</Typography.Text></Space>},
    {title: '距离', dataIndex: 'distance_meters', width: 100, sorter: (a: ProjectCompetitor, b: ProjectCompetitor) => (a.distance_meters || 999999) - (b.distance_meters || 999999), defaultSortOrder: 'ascend' as const, render: (value: number | null) => value == null ? '-' : `${value} 米`},
    {title: '状态', dataIndex: 'status', width: 100, render: (value: string) => <StatusTag status={value} />},
    {title: '人工核实', key: 'audit', width: 230, render: (_: unknown, item: ProjectCompetitor) => <AuditText meta={item.manual_meta} />},
    {title: '操作', key: 'action', width: 300, render: (_: unknown, item: ProjectCompetitor) => <Space wrap><Button size="small" type="primary" icon={<CheckOutlined />} loading={savingId === `competitor:${item.id}`} onClick={() => reviewCompetitor(item, 'confirmed')}>确认竞品</Button><Button size="small" icon={<CloseOutlined />} onClick={() => reviewCompetitor(item, 'rejected')}>不是竞品</Button><Button size="small" icon={<EditOutlined />} onClick={() => openCompetitor(item)}>核实详情</Button></Space>},
  ];

  const supportingColumns = [
    {title: '商户', key: 'name', render: (_: unknown, item: ProjectSupportingItem) => <Space direction="vertical" size={2}><Typography.Text strong>{item.name}</Typography.Text><Typography.Text type="secondary">{item.address || '高德未提供地址'}</Typography.Text></Space>},
    {title: '分类', dataIndex: 'category', width: 120, render: (value: string) => ({food: '餐饮', entertainment: '娱乐', night_business: '夜间商业候选'} as Record<string, string>)[value] || value},
    {title: '距离', dataIndex: 'distance_meters', width: 100, render: (value: number | null) => value == null ? '-' : `${value} 米`},
    {title: '状态', dataIndex: 'status', width: 100, render: (value: string) => <StatusTag status={value} />},
    {title: '操作', key: 'action', width: 290, render: (_: unknown, item: ProjectSupportingItem) => <Space wrap><Button size="small" type="primary" onClick={() => reviewSupportingItem(item, 'confirmed')}>确认有效</Button><Button size="small" onClick={() => reviewSupportingItem(item, 'rejected')}>排除</Button><Button size="small" disabled={item.status !== 'confirmed'} onClick={() => openSupporting(item)}>补充营业信息</Button></Space>},
  ];

  const listToolbar = (
    <Space wrap style={{marginBottom: 12}}>
      <Input.Search allowClear placeholder="按名称或地址搜索" style={{width: 280}} onSearch={setSearch} onChange={event => setSearch(event.target.value)} />
      <Space><Switch checked={pendingOnly} onChange={setPendingOnly} /><Typography.Text>只看待核实</Typography.Text></Space>
      <Button onClick={() => void loadAll()}>刷新</Button>
    </Space>
  );

  if (loading) return <div className="page"><Spin tip="正在读取高德候选和人工核实数据..." /></div>;

  return (
    <div className="page supplement-page">
      <div className="page-title-row">
        <div>
          <Typography.Title level={2}>人工核实与补充</Typography.Title>
          <Typography.Paragraph type="secondary">围绕高德已发现对象核实真实性并补齐关键经营信息；不知道的字段可以明确标记，不要求一次补完全部对象。</Typography.Paragraph>
        </div>
        <Button icon={<ArrowLeftOutlined />} onClick={() => navigate(`/projects/${projectId}`)}>返回项目工作台</Button>
      </div>
      <Alert type="info" showIcon style={{marginBottom: 16}} message="数据真实性边界" description="高德名称、地址和距离只读保留；人工核实值单独记录来源、时间和修改历史，不会被后续高德采集覆盖。" />
      <Row gutter={[12, 12]} className="supplement-summary">
        <Col xs={12} md={6}><Card size="small"><Typography.Text type="secondary">疑似竞品</Typography.Text><Typography.Title level={3}>{competitors.length}</Typography.Title><Tag color="orange">{competitors.filter(item => item.status === 'pending_review').length} 待核实</Tag></Card></Col>
        <Col xs={12} md={6}><Card size="small"><Typography.Text type="secondary">周边配套</Typography.Text><Typography.Title level={3}>{supporting.length}</Typography.Title><Tag color="orange">{supporting.filter(item => item.status === 'pending_review').length} 待核实</Tag></Card></Col>
        <Col xs={12} md={6}><Card size="small"><Typography.Text type="secondary">租金记录</Typography.Text><Typography.Title level={3}>{rents.length}</Typography.Title><Tag color="green">{rents.filter(item => item.status === 'confirmed').length} 已确认</Tag></Card></Col>
        <Col xs={12} md={6}><Card size="small"><Typography.Text type="secondary">处理建议</Typography.Text><Typography.Paragraph>先确认对象真实性，再补充关键经营字段。</Typography.Paragraph></Card></Col>
      </Row>
      <Card>
        <Tabs activeKey={activeTab} onChange={key => { setActiveTab(key); setSearch(''); setPendingOnly(key !== 'property'); }} items={[
          {key: 'competitor', label: `竞品核实（${competitors.filter(item => item.status === 'pending_review').length} 待处理）`, children: <>{listToolbar}<Table rowKey="id" size="small" scroll={{x: 980}} columns={competitorColumns} dataSource={filteredCompetitors} pagination={{pageSize: 10}} locale={{emptyText: competitors.length ? '当前筛选条件下没有记录' : '请先采集并整理疑似竞品'}} /></>},
          {key: 'supporting', label: `配套核实（${supporting.filter(item => item.status === 'pending_review').length} 待处理）`, children: <>{listToolbar}<Table rowKey="id" size="small" scroll={{x: 900}} columns={supportingColumns} dataSource={filteredSupporting} pagination={{pageSize: 10}} locale={{emptyText: supporting.length ? '当前筛选条件下没有记录' : '请先采集并整理周边配套'}} /></>},
          {key: 'property', label: '候选物业', children: <PropertyForm form={propertyForm} saving={propertySaving} onSave={saveProperty} rents={rents} onOpenRent={openRent} onReviewRent={async (item, status) => { const updated = await reviewProjectRent(projectId, item.id, status); setRents(rows => rows.map(row => row.id === item.id ? updated : row)); message.success('租金状态已保存'); }} />},
        ]} />
      </Card>

      <Modal title="竞品人工核实" width={820} style={{maxWidth: 'calc(100vw - 24px)'}} open={Boolean(competitorModal)} onCancel={() => setCompetitorModal(null)} onOk={saveCompetitor} okText="保存核实信息" confirmLoading={savingId.startsWith('competitor:')}>
        {competitorModal && <><ReadonlySource {...competitorModal} /><Form form={competitorForm} layout="vertical"><Typography.Title level={5}>规模与硬件</Typography.Title><Row gutter={12}><Col xs={24} md={8}><Form.Item name="area_sqm" label="营业面积（㎡）"><InputNumber min={0} style={{width: '100%'}} /></Form.Item></Col><Col xs={24} md={8}><Form.Item name="machine_count" label="机器数量（台）"><InputNumber min={0} style={{width: '100%'}} /></Form.Item></Col><Col xs={24} md={8}><Form.Item name="opening_date" label="开业时间"><Input /></Form.Item></Col><Col xs={24} md={8}><Form.Item name="cpu" label="CPU"><Input /></Form.Item></Col><Col xs={24} md={8}><Form.Item name="gpu" label="显卡"><Input /></Form.Item></Col><Col xs={24} md={8}><Form.Item name="monitor" label="显示器"><Input /></Form.Item></Col></Row><Typography.Title level={5}>价格与经营</Typography.Title><Row gutter={12}><Col xs={24} md={8}><Form.Item name="hour_price" label="小时价（元）"><InputNumber min={0} style={{width: '100%'}} /></Form.Item></Col><Col xs={24} md={8}><Form.Item name="member_price" label="会员价（元）"><InputNumber min={0} style={{width: '100%'}} /></Form.Item></Col><Col xs={24} md={8}><Form.Item name="business_hours" label="营业时间修正"><Input placeholder="如 10:00-02:00" /></Form.Item></Col><Col xs={24} md={8}><Form.Item name="occupancy_rate" label="现场上座率（%）"><InputNumber min={0} max={100} style={{width: '100%'}} /></Form.Item></Col><Col xs={24} md={8}><Form.Item name="occupancy_observed_at" label="观察时间"><Input placeholder="2026-08-12 20:00" /></Form.Item></Col><Col xs={24} md={8}><Form.Item name="occupancy_period" label="观察时段"><Select allowClear options={[{value: 'weekday_day', label: '工作日白天'}, {value: 'weekday_night', label: '工作日晚间'}, {value: 'weekend_day', label: '周末白天'}, {value: 'weekend_night', label: '周末晚间'}]} /></Form.Item></Col><Col xs={24} md={12}><Form.Item name="survey_method" label="核实方式"><Select allowClear options={[{value: 'onsite', label: '现场观察'}, {value: 'phone', label: '电话询问'}, {value: 'public_info', label: '公开信息'}]} /></Form.Item></Col><Col xs={24} md={12}><Form.Item name="recharge_info" label="充值活动"><Input /></Form.Item></Col><Col xs={24} md={12}><Form.Item name="monthly_sales" label="月营业额（可选，仅可靠来源）"><InputNumber min={0} style={{width: '100%'}} /></Form.Item></Col><Col xs={24} md={12}><Form.Item name="sales_source" label="营业额来源"><Input placeholder="未填写来源时不应作为可靠事实" /></Form.Item></Col><Col span={24}><Form.Item name="unknown_fields" label="明确不知道的字段"><Select mode="multiple" allowClear options={COMPETITOR_UNKNOWN_OPTIONS} placeholder="选择后系统会记录为“人工明确未知”" /></Form.Item></Col><Col span={24}><Form.Item name="remark" label="调研备注"><TextArea rows={3} /></Form.Item></Col></Row></Form></>}
      </Modal>

      <Modal title="配套营业信息核实" width={700} style={{maxWidth: 'calc(100vw - 24px)'}} open={Boolean(supportingModal)} onCancel={() => setSupportingModal(null)} onOk={saveSupporting} okText="保存核实信息" confirmLoading={Boolean(supportingModal && savingId === supportingModal.id)}>
        {supportingModal && <><ReadonlySource {...supportingModal} /><Form form={supportingForm} layout="vertical"><Row gutter={12}><Col xs={24} md={12}><Form.Item name="business_hours" label="人工核实营业时间"><Input /></Form.Item></Col><Col xs={24} md={12}><Form.Item name="opening_date" label="开业时间"><Input /></Form.Item></Col><Col xs={24} md={12}><Form.Item name="night_operation" label="是否夜间营业"><Select allowClear options={YES_NO_UNKNOWN} /></Form.Item></Col>{supportingModal.category === 'night_business' && <Col xs={24} md={12}><Form.Item name="is_24_hours" label="是否24小时营业"><Select allowClear options={YES_NO_UNKNOWN} /></Form.Item></Col>}<Col span={24}><Form.Item name="unknown_fields" label="明确不知道"><Select mode="multiple" options={[{value: 'business_hours', label: '营业时间'}, {value: 'night_operation', label: '夜间营业状态'}, {value: 'is_24_hours', label: '24小时状态'}]} /></Form.Item></Col><Col span={24}><Form.Item name="remark" label="现场备注"><TextArea rows={3} /></Form.Item></Col></Row></Form></>}
      </Modal>

      <Modal title="租金与物业信息" width={760} style={{maxWidth: 'calc(100vw - 24px)'}} open={Boolean(rentModal)} onCancel={() => setRentModal(null)} onOk={saveRent} okText="保存" confirmLoading={Boolean(rentModal && savingId === `rent:${rentModal.id}`)}>
        {rentModal && <Form form={rentForm} layout="vertical"><Row gutter={12}><Col span={24}><Form.Item name="address" label="物业地址"><Input /></Form.Item></Col><Col xs={24} md={8}><Form.Item name="area_sqm" label="面积（㎡）"><InputNumber min={0} style={{width: '100%'}} /></Form.Item></Col><Col xs={24} md={8}><Form.Item name="monthly_rent" label="月租金（元）"><InputNumber min={0} style={{width: '100%'}} /></Form.Item></Col><Col xs={24} md={8}><Form.Item name="property_fee" label="物业费（元/月）"><InputNumber min={0} style={{width: '100%'}} /></Form.Item></Col><Col xs={24} md={8}><Form.Item name="transfer_fee" label="转让费（元）"><InputNumber min={0} style={{width: '100%'}} /></Form.Item></Col><Col xs={24} md={8}><Form.Item name="floor" label="楼层"><Input /></Form.Item></Col><Col xs={24} md={8}><Form.Item name="property_type" label="物业用途"><Input placeholder="商业/办公等" /></Form.Item></Col><Col span={24}><Form.Item name="source_url" label="报价来源"><Input /></Form.Item></Col><Col span={24}><Form.Item name="unknown_fields" label="明确不知道"><Select mode="multiple" options={[{value: 'monthly_rent', label: '月租金'}, {value: 'property_fee', label: '物业费'}, {value: 'transfer_fee', label: '转让费'}, {value: 'property_type', label: '物业用途'}]} /></Form.Item></Col><Col span={24}><Form.Item name="rent_remark" label="备注"><TextArea rows={3} /></Form.Item></Col></Row></Form>}
      </Modal>
    </div>
  );
}

function PropertyForm({form, saving, onSave, rents, onOpenRent, onReviewRent}: {form: any; saving: boolean; onSave: () => void; rents: ProjectRentItem[]; onOpenRent: (item: ProjectRentItem) => void; onReviewRent: (item: ProjectRentItem, status: 'confirmed' | 'rejected') => Promise<void>}) {
  return <Space direction="vertical" size={16} style={{width: '100%'}}><Alert type="info" showIcon message="候选物业独立调查表" description="这里只记录投资者实际考察的候选物业，不把周边商铺租金自动当作当前物业报价。" /><Form form={form} layout="vertical"><Row gutter={12}><Col span={24}><Form.Item name="address" label="候选物业地址"><Input /></Form.Item></Col><Col xs={24} md={8}><Form.Item name="area_sqm" label="可用面积（㎡）"><InputNumber min={0} style={{width: '100%'}} /></Form.Item></Col><Col xs={24} md={8}><Form.Item name="monthly_rent" label="月租金（元）"><InputNumber min={0} style={{width: '100%'}} /></Form.Item></Col><Col xs={24} md={8}><Form.Item name="floor" label="楼层"><Input /></Form.Item></Col><Col xs={24} md={8}><Form.Item name="property_type" label="物业用途"><Input /></Form.Item></Col><Col xs={24} md={8}><Form.Item name="power_capacity_kw" label="供电容量（kW）"><InputNumber min={0} style={{width: '100%'}} /></Form.Item></Col><Col xs={24} md={8}><Form.Item name="network_carriers" label="可用运营商"><Input placeholder="电信、联通等" /></Form.Item></Col><Col xs={24} md={6}><Form.Item name="use_allowed" label="允许电竞馆业态"><Select allowClear options={YES_NO_UNKNOWN} /></Form.Item></Col><Col xs={24} md={6}><Form.Item name="power_sufficient" label="供电满足"><Select allowClear options={YES_NO_UNKNOWN} /></Form.Item></Col><Col xs={24} md={6}><Form.Item name="fire_confirmed" label="消防条件确认"><Select allowClear options={YES_NO_UNKNOWN} /></Form.Item></Col><Col xs={24} md={6}><Form.Item name="dual_line_supported" label="支持双线路"><Select allowClear options={YES_NO_UNKNOWN} /></Form.Item></Col><Col xs={24} md={6}><Form.Item name="night_entrance" label="夜间独立入口"><Select allowClear options={YES_NO_UNKNOWN} /></Form.Item></Col><Col xs={24} md={6}><Form.Item name="independent_entrance" label="独立门头入口"><Select allowClear options={YES_NO_UNKNOWN} /></Form.Item></Col><Col span={24}><Form.Item name="unknown_fields" label="明确不知道"><Select mode="multiple" options={[{value: 'use_allowed', label: '业态许可'}, {value: 'power_capacity_kw', label: '供电容量'}, {value: 'fire_confirmed', label: '消防条件'}, {value: 'dual_line_supported', label: '双线路'}, {value: 'night_entrance', label: '夜间入口'}]} /></Form.Item></Col><Col span={24}><Form.Item name="notes" label="物业备注"><TextArea rows={3} /></Form.Item></Col></Row><Button type="primary" icon={<SaveOutlined />} loading={saving} onClick={onSave}>保存候选物业</Button></Form><Card size="small" title={`周边租金/报价记录（${rents.length}）`}><Table size="small" rowKey="id" dataSource={rents} pagination={false} scroll={{x: 720}} columns={[{title: '地址', dataIndex: 'address', render: value => value || '待补充'}, {title: '面积', dataIndex: 'area_sqm', render: value => value == null ? '-' : `${value}㎡`}, {title: '月租金', dataIndex: 'monthly_rent', render: value => value == null ? '-' : `¥${value}`}, {title: '状态', dataIndex: 'status', render: value => <StatusTag status={value} />}, {title: '操作', render: (_: unknown, item: ProjectRentItem) => <Space><Button size="small" onClick={() => onOpenRent(item)}>补充</Button><Button size="small" type="primary" onClick={() => void onReviewRent(item, 'confirmed')}>确认</Button><Button size="small" onClick={() => void onReviewRent(item, 'rejected')}>排除</Button></Space>}]}/></Card></Space>;
}
