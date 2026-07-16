import {Button, Card, Form, Input, InputNumber, Typography, message} from 'antd';
import {useNavigate} from 'react-router-dom';
import {createProject, type ProjectCreatePayload} from '../../api/projects';

export default function ProjectCreatePage() {
  const [form] = Form.useForm<ProjectCreatePayload>();
  const navigate = useNavigate();

  const submit = async (values: ProjectCreatePayload) => {
    try {
      const result = await createProject({
        ...values,
        business_type: values.business_type || '电竞馆',
        radius_meters: values.radius_meters || 1000,
      });
      message.success('项目创建成功');
      navigate(`/projects/${result.project_id}`);
    } catch (error: any) {
      message.error(error?.response?.data?.detail || error.message || '创建项目失败');
    }
  };

  return (
    <div className="page">
      <Typography.Title level={2}>创建选址项目</Typography.Title>
      <Typography.Paragraph type="secondary">
        填写候选地址和基础投资信息，提交后进入项目工作台。
      </Typography.Paragraph>

      <Card title="项目基础信息">
        <Form
          form={form}
          layout="vertical"
          onFinish={submit}
          initialValues={{radius_meters: 1000, business_type: '电竞馆'}}
        >
          <div className="project-form-grid">
            <Form.Item name="name" label="项目名称" rules={[{required: true, message: '请输入项目名称'}]}>
              <Input placeholder="西安小寨电竞馆选址" />
            </Form.Item>
            <Form.Item name="city" label="城市" rules={[{required: true, message: '请输入城市'}]}>
              <Input placeholder="西安市" />
            </Form.Item>
            <Form.Item name="district" label="区域">
              <Input placeholder="雁塔区" />
            </Form.Item>
            <Form.Item name="address" label="详细地址" rules={[{required: true, message: '请输入详细地址'}]}>
              <Input placeholder="小寨地铁站" />
            </Form.Item>
            <Form.Item name="radius_meters" label="分析范围" rules={[{required: true, message: '请输入分析范围'}]}>
              <InputNumber min={100} max={10000} style={{width: '100%'}} addonAfter="米" />
            </Form.Item>
            <Form.Item name="business_type" label="经营类型">
              <Input placeholder="电竞馆" />
            </Form.Item>
            <Form.Item name="expected_area_sqm" label="预计面积">
              <InputNumber min={0} style={{width: '100%'}} addonAfter="㎡" />
            </Form.Item>
            <Form.Item name="investment_budget" label="投资预算">
              <InputNumber min={0} style={{width: '100%'}} addonAfter="元" />
            </Form.Item>
          </div>

          <Button type="primary" htmlType="submit" size="large">
            创建项目并进入工作台
          </Button>
        </Form>
      </Card>
    </div>
  );
}
