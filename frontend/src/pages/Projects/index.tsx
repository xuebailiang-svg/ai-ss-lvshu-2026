import {useEffect, useState} from 'react';
import {Button, Card, Form, Input, InputNumber, Space, Table, Tag, Typography, message} from 'antd';
import {useNavigate} from 'react-router-dom';
import {createProject, listProjects, type ProjectCreatePayload} from '../../api/projects';

function statusOf(record: any) {
  const missing = record?.stats?.missing_fields || [];
  if (missing.length === 0 && record?.stats?.poi_count > 0) return {text: '数据就绪', color: 'green'};
  if (record?.stats?.poi_count > 0) return {text: '已采集', color: 'blue'};
  return {text: '草稿', color: 'default'};
}

export default function ProjectsPage() {
  const [items, setItems] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);
  const [creating, setCreating] = useState(false);
  const [form] = Form.useForm<ProjectCreatePayload>();
  const navigate = useNavigate();

  const load = async () => {
    setLoading(true);
    try {
      const data = await listProjects();
      setItems(data.items || []);
    } catch (error: any) {
      message.error(error?.response?.data?.detail || error.message || '加载项目失败');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    load();
  }, []);

  const onCreate = async (values: ProjectCreatePayload) => {
    setCreating(true);
    try {
      const data = await createProject({...values, business_type: values.business_type || '电竞馆'});
      message.success('项目创建成功');
      navigate(`/projects/${data.project_id}`);
    } catch (error: any) {
      message.error(error?.response?.data?.detail || error.message || '创建项目失败');
    } finally {
      setCreating(false);
    }
  };

  return (
    <div className="page">
      <Typography.Title level={2}>选址项目工作台</Typography.Title>
      <Card title="创建项目" style={{marginBottom: 16}}>
        <Form form={form} layout="vertical" onFinish={onCreate} initialValues={{radius_meters: 1000, business_type: '电竞馆'}}>
          <div className="project-form-grid">
            <Form.Item name="name" label="项目名称" rules={[{required: true, message: '请输入项目名称'}]}>
              <Input placeholder="西安小寨电竞馆" />
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
            <Form.Item name="radius_meters" label="分析半径">
              <InputNumber min={100} max={10000} style={{width: '100%'}} addonAfter="米" />
            </Form.Item>
            <Form.Item name="business_type" label="业务类型">
              <Input />
            </Form.Item>
          </div>
          <Button type="primary" htmlType="submit" loading={creating}>创建并进入项目</Button>
        </Form>
      </Card>

      <Card title="项目列表">
        <Table
          rowKey="project_id"
          loading={loading}
          dataSource={items}
          columns={[
            {title: '项目名称', dataIndex: 'name', render: (value: string) => value || '-'},
            {title: '城市', dataIndex: 'city'},
            {title: '地址', dataIndex: 'address'},
            {title: '创建时间', dataIndex: 'created_at', render: (value: string) => value ? new Date(value).toLocaleString() : '-'},
            {
              title: '当前状态',
              render: (_: any, record: any) => {
                const status = statusOf(record);
                return <Tag color={status.color}>{status.text}</Tag>;
              },
            },
            {
              title: '操作',
              render: (_: any, record: any) => (
                <Space>
                  <Button type="link" onClick={() => navigate(`/projects/${record.project_id}`)}>进入项目</Button>
                </Space>
              ),
            },
          ]}
        />
      </Card>
    </div>
  );
}
