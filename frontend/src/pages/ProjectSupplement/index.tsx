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
import {useNavigate, useParams} from 'react-router-dom';

const {TextArea} = Input;

const EMPTY_VALUES = {
  competitors: [{}],
  rents: [{}],
  populations: [{}],
  supports: [{}],
};

function NumberField({name, label, suffix}: {name: string; label: string; suffix?: string}) {
  return (
    <Form.Item name={name} label={label}>
      <InputNumber min={0} style={{width: '100%'}} addonAfter={suffix} />
    </Form.Item>
  );
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
  const [form] = Form.useForm();
  const [saved, setSaved] = useState(false);
  const storageKey = `project-supplement:${projectId}`;

  useEffect(() => {
    const stored = localStorage.getItem(storageKey);
    if (!stored) return;
    try {
      form.setFieldsValue(JSON.parse(stored));
      setSaved(true);
    } catch {
      localStorage.removeItem(storageKey);
    }
  }, [form, storageKey]);

  const saveDraft = (values: typeof EMPTY_VALUES) => {
    localStorage.setItem(storageKey, JSON.stringify(values));
    setSaved(true);
    message.success('人工补充完成，等待数据核验');
  };

  return (
    <div className="page supplement-page">
      <div className="page-title-row">
        <div>
          <Typography.Title level={2}>人工补充数据</Typography.Title>
          <Typography.Paragraph type="secondary">
            补充高德暂时无法提供的经营、成本和客群信息。当前内容仅保存在本浏览器，不会写入服务器。
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
        description="提交后会保存到当前浏览器，后续阶段再接入服务器保存和数据核验。"
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
              <Button type="primary" htmlType="submit" icon={<SaveOutlined />}>保存人工补充草稿</Button>
              <Typography.Text type="secondary">保存后可返回工作台，继续进行数据核验。</Typography.Text>
            </Space>
          </Card>
        </Space>
      </Form>
    </div>
  );
}
