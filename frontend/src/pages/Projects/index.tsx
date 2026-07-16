import {useEffect, useState} from 'react';
import {Button, Card, Space, Table, Tag, Typography, message} from 'antd';
import {PlusOutlined} from '@ant-design/icons';
import {useNavigate} from 'react-router-dom';
import {listProjects} from '../../api/projects';

function projectStatus(record: any) {
  const stats = record?.stats || {};
  const missing = stats.missing_fields || [];
  if (record?.status === 'reported' || record?.latest_report) return {text: '已生成报告', color: 'purple'};
  if (record?.status === 'scored' || record?.latest_score) return {text: '分析完成', color: 'green'};
  if ((stats.poi_count || 0) > 0 && missing.length > 0) return {text: '数据补充中', color: 'orange'};
  if ((stats.poi_count || 0) > 0) return {text: '数据采集中', color: 'blue'};
  return {text: '初始化', color: 'default'};
}

export default function ProjectsPage() {
  const [items, setItems] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);
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

  return (
    <div className="page">
      <div className="page-title-row">
        <div>
          <Typography.Title level={2}>选址项目</Typography.Title>
          <Typography.Paragraph type="secondary">按客户项目管理选址分析、数据补充、评分和报告。</Typography.Paragraph>
        </div>
        <Button type="primary" icon={<PlusOutlined />} onClick={() => navigate('/projects/create')}>
          创建项目
        </Button>
      </div>

      <Card>
        <Table
          rowKey="project_id"
          loading={loading}
          dataSource={items}
          columns={[
            {title: '项目名称', dataIndex: 'name', render: (value: string) => value || '-'},
            {
              title: '地址',
              render: (_: any, record: any) => [record.city, record.district, record.address].filter(Boolean).join(' '),
            },
            {title: '创建时间', dataIndex: 'created_at', render: (value: string) => value ? new Date(value).toLocaleString() : '-'},
            {
              title: '状态',
              render: (_: any, record: any) => {
                const status = projectStatus(record);
                return <Tag color={status.color}>{status.text}</Tag>;
              },
            },
            {
              title: '操作',
              render: (_: any, record: any) => (
                <Space>
                  <Button type="link" onClick={() => navigate(`/projects/${record.project_id}`)}>进入工作台</Button>
                </Space>
              ),
            },
          ]}
        />
      </Card>
    </div>
  );
}
