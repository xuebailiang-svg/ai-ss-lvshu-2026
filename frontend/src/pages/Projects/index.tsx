import {useEffect, useState} from 'react';
import {Button, Card, Col, Empty, Popconfirm, Row, Space, Tag, Typography, message} from 'antd';
import {DeleteOutlined, FolderOpenOutlined, PlusOutlined} from '@ant-design/icons';
import {useNavigate} from 'react-router-dom';
import {deleteProject, listProjects} from '../../api/projects';

function projectStatus(record: any) {
  const stats = record?.stats || {};
  const missing = stats.missing_fields || [];
  if (record?.status === 'reported' || record?.latest_report) return {text: '已生成报告', color: 'purple'};
  if (record?.status === 'scored' || record?.latest_score) return {text: '数据已整理', color: 'green'};
  if ((stats.poi_count || 0) > 0 && missing.length > 0) return {text: '数据补充中', color: 'orange'};
  if ((stats.poi_count || 0) > 0) return {text: '数据采集中', color: 'blue'};
  return {text: '初始化', color: 'default'};
}

function projectProgress(record: any) {
  const stats = record?.stats || {};
  if (record?.status === 'reported' || record?.latest_report) return {step: 6, text: '报告已生成'};
  if (record?.status === 'scored' || record?.latest_score) return {step: 5, text: '数据已整理'};
  if ((stats.poi_count || 0) > 0) return {step: 3, text: '待人工核实'};
  if (record?.longitude != null && record?.latitude != null) return {step: 2, text: '待采集高德数据'};
  return {step: 1, text: '待确认地址'};
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

  const remove = async (projectId: string) => {
    try {
      await deleteProject(projectId);
      message.success('项目已删除');
      await load();
    } catch (error: any) {
      const detail = error?.response?.data?.detail;
      message.error(typeof detail === 'string' ? detail : error?.message || '删除项目失败');
    }
  };

  return (
    <div className="page">
      <div className="page-title-row">
        <div>
          <Typography.Title level={2}>选址项目</Typography.Title>
          <Typography.Paragraph type="secondary">创建候选地址，依次完成高德采集、人工补充、数据检查和 AI 报告。</Typography.Paragraph>
        </div>
        <Button type="primary" icon={<PlusOutlined />} onClick={() => navigate('/projects/create')}>
          创建项目
        </Button>
      </div>

      <Card loading={loading} className="project-list-shell">
        {!loading && items.length === 0 ? (
          <Empty description="还没有选址项目" image={Empty.PRESENTED_IMAGE_SIMPLE}>
            <Button type="primary" icon={<PlusOutlined />} onClick={() => navigate('/projects/create')}>创建第一个项目</Button>
          </Empty>
        ) : (
          <Row gutter={[14, 14]}>
            {items.map(record => {
              const status = projectStatus(record);
              const progress = projectProgress(record);
              const address = [record.city, record.district, record.address].filter(Boolean).join(' ') || '地址待补充';
              return (
                <Col xs={24} md={12} xl={8} key={record.project_id}>
                  <Card size="small" className="project-list-card" data-testid="project-list-card">
                    <div className="project-card-heading">
                      <Typography.Title level={4} ellipsis={{tooltip: record.name}}>{record.name || '未命名项目'}</Typography.Title>
                      <Tag color={status.color}>{status.text}</Tag>
                    </div>
                    <Typography.Paragraph className="project-card-address" type="secondary" ellipsis={{rows: 2, tooltip: address}}>
                      {address}
                    </Typography.Paragraph>
                    <div className="project-card-progress">
                      <Typography.Text strong>Step {progress.step} / 6</Typography.Text>
                      <Typography.Text type="secondary">{progress.text}</Typography.Text>
                    </div>
                    <div className="project-card-actions">
                      <Button type="primary" icon={<FolderOpenOutlined />} onClick={() => navigate(`/projects/${record.project_id}`)}>打开</Button>
                      <Popconfirm
                        title="删除这个项目？"
                        description="项目将从列表隐藏，已有生产数据不会被物理清空。"
                        okText="删除"
                        cancelText="取消"
                        onConfirm={() => remove(record.project_id)}
                      >
                        <Button danger icon={<DeleteOutlined />}>删除</Button>
                      </Popconfirm>
                    </div>
                  </Card>
                </Col>
              );
            })}
          </Row>
        )}
      </Card>
    </div>
  );
}
