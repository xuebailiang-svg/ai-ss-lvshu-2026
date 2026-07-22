import {useEffect, useState} from 'react';
import {
  Alert,
  Button,
  Card,
  Col,
  Form,
  Input,
  InputNumber,
  Row,
  Select,
  Space,
  Typography,
  message,
} from 'antd';
import {ArrowLeftOutlined, DeleteOutlined, PlusOutlined, SaveOutlined} from '@ant-design/icons';
import {useNavigate, useParams, useSearchParams} from 'react-router-dom';
import {submitManualInput} from '../../api/data';
import {getProjectDataQuality, listProjectCompetitors, type ProjectCompetitor} from '../../api/projects';

const {TextArea} = Input;

const EMPTY_VALUES = {
  competitors: [{}],
  rents: [{}],
  populations: [{}],
  supports: [{}],
};

const FOCUS_GUIDE: Record<string, {title: string; description: string; fields: string[]}> = {
  competitor: {
    title: '本次重点：补充竞品经营信息',
    description: '优先核实哪些店是真正竞品，并补充价格、配置、机器数量、上座率和营业时间。',
    fields: ['竞品名称', '距离', '面积', '机器数量', 'CPU/GPU', '价格', '营业时间', '上座率'],
  },
  rent: {
    title: '本次重点：补充租金成本信息',
    description: '优先补齐候选物业或周边商铺的真实租金样本，后续才能判断成本压力。',
    fields: ['月租金', '面积', '物业费', '转让费', '租金来源', '位置说明'],
  },
  support: {
    title: '本次重点：补充夜间消费和配套',
    description: '优先确认餐饮、便利店、娱乐设施是否真实夜间营业，不能默认便利店就是 24 小时。',
    fields: ['夜市', '24小时便利店', '餐饮营业时间', '娱乐设施', '夜间人流', '备注'],
  },
  population: {
    title: '本次重点：补充客群人口信息',
    description: '优先记录大学、高职、技校、公寓、年轻住宅和夜间年轻人流情况。',
    fields: ['大学', '技校', '公寓', '住宅情况', '年轻人口情况'],
  },
  property: {
    title: '本次重点：补充物业落地条件',
    description: '优先核实面积、供电、网络、消防、停车、门头和其他开店落地风险。',
    fields: ['可用面积', '供电', '网络', '消防', '停车', '门头', '备注'],
  },
  general: {
    title: '人工补充建议',
    description: '请根据现场调研结果补充高德和 AI 无法直接确认的数据，不确定的信息可以留空。',
    fields: ['竞品经营', '租金成本', '客群人口', '夜间配套'],
  },
};

function NumberField({name, label, suffix}: {name: string; label: string; suffix?: string}) {
  return (
    <Form.Item name={name} label={label}>
      <InputNumber min={0} style={{width: '100%'}} addonAfter={suffix} />
    </Form.Item>
  );
}

function cleanPayload(data: Record<string, any>) {
  return Object.fromEntries(
    Object.entries(data || {}).filter(([, value]) => value !== undefined && value !== null && value !== ''),
  );
}

function hasMeaningfulValue(data: Record<string, any>) {
  return Object.keys(cleanPayload(data)).length > 0;
}

function competitorPayload(row: Record<string, any>) {
  const payload = cleanPayload({
    name: row.name,
    distance_meters: row.distance_meters,
    area_sqm: row.area_sqm,
    machine_count: row.machine_count,
    cpu: row.cpu,
    gpu: row.gpu,
    hour_price: row.hour_price,
    business_hours: row.business_hours,
    opening_date: row.opening_date,
    occupancy_rate: row.occupancy_rate,
    monthly_sales: row.monthly_revenue,
  });
  return payload;
}

function competitorToFormRow(item: ProjectCompetitor) {
  return cleanPayload({
    competitor_id: item.id,
    name: item.name,
    distance_meters: item.distance_meters,
    area_sqm: item.area_sqm,
    machine_count: item.machine_count,
    cpu: item.cpu,
    gpu: item.gpu,
    hour_price: item.hour_price,
    business_hours: item.business_hours,
    opening_date: item.opening_date,
    occupancy_rate: item.occupancy_rate,
    monthly_revenue: item.monthly_sales,
  });
}

function rentPayload(row: Record<string, any>) {
  return cleanPayload({
    monthly_rent: row.monthly_rent,
    property_fee: row.property_fee,
    area_sqm: row.area_sqm,
    transfer_fee: row.transfer_fee,
  });
}

function populationPayload(row: Record<string, any>) {
  const description = [
    row.universities ? `周边大学：${row.universities}` : '',
    row.vocational_schools ? `技校/高职：${row.vocational_schools}` : '',
    row.residential ? `住宅情况：${row.residential}` : '',
    row.apartments ? `公寓情况：${row.apartments}` : '',
    row.young_population ? `年轻人口情况：${row.young_population}` : '',
  ].filter(Boolean).join('\n');
  return cleanPayload({
    target_customer_description: description,
    young_population_indicator: row.young_population,
  });
}

function supportPayload(row: Record<string, any>) {
  const value = [
    row.night_market ? `夜市：${row.night_market}` : '',
    row.convenience_store_24h ? `24小时便利店：${row.convenience_store_24h}` : '',
    row.entertainment ? `娱乐设施：${row.entertainment}` : '',
    row.remark ? `备注：${row.remark}` : '',
  ].filter(Boolean).join('\n');
  if (!value) return {};
  return cleanPayload({
    target_type: 'support',
    field_name: 'manual_support_note',
    value,
    remark: value,
  });
}

function ListSection({
  name,
  title,
  description,
  addText,
  children,
}: {
  name: string;
  title: string;
  description: string;
  addText: string;
  children: (fieldName: number) => React.ReactNode;
}) {
  return (
    <Card title={title} extra={<Typography.Text type="secondary">可填写多条</Typography.Text>}>
      <Typography.Paragraph type="secondary">{description}</Typography.Paragraph>
      <Form.List name={name}>
        {(fields, {add, remove}) => (
          <Space direction="vertical" size={16} style={{width: '100%'}}>
            {fields.map((field, index) => (
              <Card
                key={field.key}
                size="small"
                title={`${title} ${index + 1}`}
                className="supplement-entry-card"
                extra={(
                  <Button danger type="text" icon={<DeleteOutlined />} onClick={() => remove(field.name)}>
                    删除
                  </Button>
                )}
              >
                <Row gutter={12}>{children(field.name)}</Row>
              </Card>
            ))}
            <Button type="dashed" block icon={<PlusOutlined />} onClick={() => add({})}>
              {addText}
            </Button>
          </Space>
        )}
      </Form.List>
    </Card>
  );
}

export default function ProjectSupplementPage() {
  const {projectId = ''} = useParams();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const [form] = Form.useForm();
  const [saved, setSaved] = useState(false);
  const [saving, setSaving] = useState(false);
  const [prefillLoading, setPrefillLoading] = useState(false);
  const [prefillCount, setPrefillCount] = useState(0);
  const [submitResult, setSubmitResult] = useState<{imported: number; failed: number; qualityScore?: number; errors: string[]} | null>(null);
  const storageKey = `project-supplement:${projectId}`;
  const focus = searchParams.get('focus') || 'general';
  const focusGuide = FOCUS_GUIDE[focus] || FOCUS_GUIDE.general;

  useEffect(() => {
    const stored = localStorage.getItem(storageKey);
    if (!stored) {
      setPrefillLoading(true);
      listProjectCompetitors(projectId)
        .then(result => {
          const rows = (result.items || []).slice(0, 20).map(competitorToFormRow);
          if (!rows.length) return;
          form.setFieldsValue({competitors: rows});
          setPrefillCount(rows.length);
        })
        .catch(() => undefined)
        .finally(() => setPrefillLoading(false));
      return;
    }
    try {
      form.setFieldsValue(JSON.parse(stored));
      setSaved(true);
    } catch {
      localStorage.removeItem(storageKey);
    }
  }, [form, storageKey]);

  const saveDraft = async (values: typeof EMPTY_VALUES) => {
    localStorage.setItem(storageKey, JSON.stringify(values));
    setSaved(true);
    setSaving(true);
    const errors: string[] = [];
    let imported = 0;

    const submit = async (
      type: 'competitor' | 'rent' | 'population' | 'supplement',
      data: Record<string, any>,
      targetId?: string | number,
    ) => {
      if (!hasMeaningfulValue(data)) return;
      try {
        await submitManualInput(projectId, {type, target_id: targetId != null ? String(targetId) : undefined, data});
        imported += 1;
      } catch (error: any) {
        errors.push(error?.response?.data?.detail || error.message || `${type} 保存失败`);
      }
    };

    try {
      for (const row of values.competitors || []) {
        const competitorRow = row as Record<string, any>;
        await submit('competitor', competitorPayload(competitorRow), competitorRow.competitor_id);
      }
      for (const row of values.rents || []) await submit('rent', rentPayload(row));
      for (const row of values.populations || []) await submit('population', populationPayload(row));
      for (const row of values.supports || []) await submit('supplement', supportPayload(row));

      let qualityScore: number | undefined;
      try {
        const quality = await getProjectDataQuality(projectId);
        qualityScore = Number(quality?.quality_score);
      } catch (error: any) {
        errors.push(error?.response?.data?.detail || error.message || '数据完整度刷新失败');
      }

      setSubmitResult({imported, failed: errors.length, qualityScore, errors});
      if (imported > 0 && errors.length === 0) {
        message.success('人工补充已保存到服务器，并已刷新数据核验');
      } else if (imported > 0) {
        message.warning('部分人工补充已保存，部分内容需要检查');
      } else {
        message.info('已保存本地草稿，没有可提交到服务器的数据');
      }
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="page supplement-page">
      <div className="page-title-row">
        <div>
          <Typography.Title level={2}>人工补充数据</Typography.Title>
          <Typography.Paragraph type="secondary">
            补充高德和 AI 无法直接确认的经营、成本和客群信息。提交后会写入服务器，参与后续数据核验、评分和报告。
          </Typography.Paragraph>
        </div>
        <Button icon={<ArrowLeftOutlined />} onClick={() => navigate(`/projects/${projectId}`)}>
          返回项目工作台
        </Button>
      </div>

      <Alert
        type={saved ? 'success' : 'info'}
        showIcon
        style={{marginBottom: 16}}
        message={saved ? '已恢复本项目的人工补充草稿' : '请按实际调研结果填写，不确定的数据可以留空'}
        description="提交时会先保留本地草稿，再把有效内容保存到服务器；保存成功后会自动刷新数据完整度。"
      />

      {prefillLoading && (
        <Alert
          type="info"
          showIcon
          style={{marginBottom: 16}}
          message="正在读取已采集的竞品数据..."
        />
      )}

      {prefillCount > 0 && !saved && (
        <Alert
          type="success"
          showIcon
          style={{marginBottom: 16}}
          message={`已带入 ${prefillCount} 条已采集竞品`}
          description="已自动填入竞品名称和距离。请在对应行补充价格、配置、上座率、营业时间等人工调研信息。"
        />
      )}

      {submitResult && (
        <Alert
          type={submitResult.failed > 0 ? 'warning' : 'success'}
          showIcon
          style={{marginBottom: 16}}
          message={`服务器保存结果：成功 ${submitResult.imported} 条，失败 ${submitResult.failed} 条`}
          description={(
            <Space direction="vertical" size={4}>
              {Number.isFinite(submitResult.qualityScore) && (
                <Typography.Text>当前数据完整度：{submitResult.qualityScore}%</Typography.Text>
              )}
              {submitResult.errors.map((item, index) => <Typography.Text key={`${item}-${index}`} type="danger">{item}</Typography.Text>)}
            </Space>
          )}
        />
      )}

      <Alert
        type="warning"
        showIcon
        style={{marginBottom: 16}}
        message={focusGuide.title}
        description={(
          <Space direction="vertical" size={8}>
            <Typography.Text>{focusGuide.description}</Typography.Text>
            <Space size={[6, 6]} wrap>
              {focusGuide.fields.map(item => <Typography.Text key={item} code>{item}</Typography.Text>)}
            </Space>
          </Space>
        )}
      />

      <Form form={form} layout="vertical" initialValues={EMPTY_VALUES} onFinish={saveDraft}>
        <Space direction="vertical" size={16} style={{width: '100%'}}>
          <ListSection
            name="competitors"
            title="竞品信息补充"
            description="记录现场调研或电话核实的竞品经营信息。"
            addText="新增一条竞品信息"
          >
            {fieldName => (
              <>
                <Col xs={24} md={8}><Form.Item name={[fieldName, 'name']} label="竞品名称"><Input placeholder="例如：XX电竞馆" /></Form.Item></Col>
                <Form.Item name={[fieldName, 'competitor_id']} hidden><Input /></Form.Item>
                <Col xs={24} md={8}><NumberField name={[fieldName, 'distance_meters'] as any} label="距离" suffix="米" /></Col>
                <Col xs={24} md={8}><NumberField name={[fieldName, 'area_sqm'] as any} label="面积" suffix="㎡" /></Col>
                <Col xs={24} md={8}><NumberField name={[fieldName, 'machine_count'] as any} label="机器数量" suffix="台" /></Col>
                <Col xs={24} md={8}><Form.Item name={[fieldName, 'cpu']} label="CPU"><Input placeholder="例如：i5-13400F" /></Form.Item></Col>
                <Col xs={24} md={8}><Form.Item name={[fieldName, 'gpu']} label="显卡"><Input placeholder="例如：RTX 4060" /></Form.Item></Col>
                <Col xs={24} md={8}><NumberField name={[fieldName, 'hour_price'] as any} label="价格" suffix="元/小时" /></Col>
                <Col xs={24} md={8}><Form.Item name={[fieldName, 'business_hours']} label="营业时间"><Input placeholder="例如：24小时" /></Form.Item></Col>
                <Col xs={24} md={8}><Form.Item name={[fieldName, 'opening_date']} label="开业时间"><Input placeholder="例如：2023年5月" /></Form.Item></Col>
                <Col xs={24} md={8}><NumberField name={[fieldName, 'occupancy_rate'] as any} label="上座率" suffix="%" /></Col>
                <Col xs={24} md={8}><NumberField name={[fieldName, 'monthly_revenue'] as any} label="月营业额" suffix="元" /></Col>
              </>
            )}
          </ListSection>

          <ListSection
            name="rents"
            title="租金信息补充"
            description="记录候选物业的实际报价和一次性成本。"
            addText="新增一条租金信息"
          >
            {fieldName => (
              <>
                <Col xs={24} md={6}><NumberField name={[fieldName, 'monthly_rent'] as any} label="月租金" suffix="元" /></Col>
                <Col xs={24} md={6}><NumberField name={[fieldName, 'property_fee'] as any} label="物业费" suffix="元/月" /></Col>
                <Col xs={24} md={6}><NumberField name={[fieldName, 'area_sqm'] as any} label="面积" suffix="㎡" /></Col>
                <Col xs={24} md={6}><NumberField name={[fieldName, 'transfer_fee'] as any} label="转让费" suffix="元" /></Col>
              </>
            )}
          </ListSection>

          <ListSection
            name="populations"
            title="人口信息补充"
            description="记录现场观察到的学校、住宅和年轻客群情况。"
            addText="新增一条人口信息"
          >
            {fieldName => (
              <>
                <Col xs={24} md={12}><Form.Item name={[fieldName, 'universities']} label="周边大学"><Input placeholder="名称、数量或距离" /></Form.Item></Col>
                <Col xs={24} md={12}><Form.Item name={[fieldName, 'vocational_schools']} label="技校"><Input placeholder="名称、数量或距离" /></Form.Item></Col>
                <Col xs={24} md={12}><Form.Item name={[fieldName, 'residential']} label="住宅情况"><Input placeholder="小区类型、入住情况等" /></Form.Item></Col>
                <Col xs={24} md={12}><Form.Item name={[fieldName, 'apartments']} label="公寓情况"><Input placeholder="公寓数量、入住情况等" /></Form.Item></Col>
                <Col span={24}><Form.Item name={[fieldName, 'young_population']} label="年轻人口情况"><TextArea rows={2} placeholder="描述年轻客群、学生和夜间人流情况" /></Form.Item></Col>
              </>
            )}
          </ListSection>

          <ListSection
            name="supports"
            title="配套补充"
            description="记录夜间消费和周边配套的现场核实结果。"
            addText="新增一条配套信息"
          >
            {fieldName => (
              <>
                <Col xs={24} md={8}>
                  <Form.Item name={[fieldName, 'night_market']} label="夜市">
                    <Select placeholder="请选择" options={[{value: 'yes', label: '有'}, {value: 'no', label: '无'}, {value: 'unknown', label: '待核实'}]} />
                  </Form.Item>
                </Col>
                <Col xs={24} md={8}>
                  <Form.Item name={[fieldName, 'convenience_store_24h']} label="24小时便利店">
                    <Input placeholder="数量、名称或距离" />
                  </Form.Item>
                </Col>
                <Col xs={24} md={8}><Form.Item name={[fieldName, 'entertainment']} label="娱乐设施"><Input placeholder="KTV、酒吧、台球等" /></Form.Item></Col>
                <Col span={24}><Form.Item name={[fieldName, 'remark']} label="备注"><TextArea rows={3} placeholder="补充营业时间、夜间人流或其他现场观察" /></Form.Item></Col>
              </>
            )}
          </ListSection>

          <Card className="supplement-submit-bar">
            <Space>
              <Button type="primary" htmlType="submit" icon={<SaveOutlined />} loading={saving}>保存到服务器并刷新核验</Button>
              <Typography.Text type="secondary">保存成功后可返回工作台，继续进行 AI 数据核验、评分和报告。</Typography.Text>
            </Space>
          </Card>
        </Space>
      </Form>
    </div>
  );
}
