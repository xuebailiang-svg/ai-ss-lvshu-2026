import {useEffect, useState} from 'react';
import {Alert, Button, Card, Form, Input, List, Select, Space, Tag, Typography, message} from 'antd';
import {
  forceGovernmentStatsSync,
  listGovernmentStatsReview,
  reviewGovernmentStatistic,
  uploadGovernmentStatistics,
} from '../api/governmentStats';
import type {RegionalStatistic} from '../api/projects';

type Props = {
  adminToken: string;
};

export default function GovernmentStatsAdminPanel({adminToken}: Props) {
  const [syncForm] = Form.useForm();
  const [uploadForm] = Form.useForm();
  const [pending, setPending] = useState<RegionalStatistic[]>([]);
  const [file, setFile] = useState<File | null>(null);
  const [loading, setLoading] = useState('');

  const ensureToken = () => {
    if (adminToken.trim()) return true;
    message.warning('请先输入并验证 ADMIN_CONFIG_TOKEN');
    return false;
  };

  const loadPending = async () => {
    if (!adminToken.trim()) {
      setPending([]);
      return;
    }
    setLoading('review');
    try {
      const result = await listGovernmentStatsReview(adminToken.trim());
      setPending(result.items || []);
    } catch (error: any) {
      message.error(error?.response?.data?.detail || error.message || '待审核指标加载失败');
    } finally {
      setLoading('');
    }
  };

  useEffect(() => {
    if (adminToken.trim()) void loadPending();
  }, [adminToken]);

  const startSync = async (values: any) => {
    if (!ensureToken()) return;
    setLoading('sync');
    try {
      await forceGovernmentStatsSync({
        city: values.city,
        district: values.district || undefined,
        sources: values.sources,
        force_refresh: true,
      }, adminToken.trim());
      message.success('政府公开数据同步任务已创建');
    } catch (error: any) {
      message.error(error?.response?.data?.detail || error.message || '同步任务创建失败');
    } finally {
      setLoading('');
    }
  };

  const review = async (recordId: number, status: 'confirmed' | 'rejected') => {
    if (!ensureToken()) return;
    setLoading(`review-${recordId}`);
    try {
      await reviewGovernmentStatistic(recordId, status, adminToken.trim());
      message.success(status === 'confirmed' ? '指标已确认' : '指标已排除');
      await loadPending();
    } catch (error: any) {
      message.error(error?.response?.data?.detail || error.message || '审核失败');
    } finally {
      setLoading('');
    }
  };

  const upload = async (values: any) => {
    if (!ensureToken() || !file) {
      if (!file) message.warning('请选择 CSV、XLSX 或 PDF 文件');
      return;
    }
    setLoading('upload');
    try {
      const result = await uploadGovernmentStatistics({...values, file}, adminToken.trim());
      message.success(`导入完成：成功 ${result.imported_count || 0}，失败 ${result.failed_count || 0}`);
      setFile(null);
      await loadPending();
    } catch (error: any) {
      message.error(error?.response?.data?.detail || error.message || '政府数据文件导入失败');
    } finally {
      setLoading('');
    }
  };

  return (
    <Card title="政府公开数据运维">
      <Alert
        type="info"
        showIcon
        message="官方数据按行政区缓存并供项目复用"
        description="优先同步官方结构化数据与HTML；PDF抽取默认待审核。城市和区县数据不得换算为项目1km真实人口或客流。"
        style={{marginBottom: 12}}
      />
      <Space direction="vertical" size={16} style={{width: '100%'}}>
        <Card size="small" title="强制同步">
          <Form
            form={syncForm}
            layout="inline"
            initialValues={{city: '西安市', district: '雁塔区', sources: ['national', 'shaanxi', 'xian']}}
            onFinish={startSync}
          >
            <Form.Item name="city" rules={[{required: true}]}><Input placeholder="城市" /></Form.Item>
            <Form.Item name="district"><Input placeholder="区县" /></Form.Item>
            <Form.Item name="sources">
              <Select
                mode="multiple"
                style={{minWidth: 280}}
                options={[
                  {label: '国家统计局', value: 'national'},
                  {label: '陕西省统计局', value: 'shaanxi'},
                  {label: '西安市统计局', value: 'xian'},
                ]}
              />
            </Form.Item>
            <Button type="primary" htmlType="submit" loading={loading === 'sync'}>强制同步</Button>
          </Form>
        </Card>

        <Card size="small" title="官方文件上传兜底">
          <Form
            form={uploadForm}
            layout="vertical"
            initialValues={{
              source_name: '西安市统计局',
              source_url: 'https://tjj.xa.gov.cn/',
              scope_level: 'city',
              scope_code: '610100',
              scope_name: '西安市',
            }}
            onFinish={upload}
          >
            <Space size={[8, 8]} wrap>
              <Form.Item name="source_name" label="来源名称" rules={[{required: true}]}><Input /></Form.Item>
              <Form.Item name="source_url" label="官方来源链接" rules={[{required: true, type: 'url'}]}><Input style={{width: 280}} /></Form.Item>
              <Form.Item name="scope_level" label="空间口径">
                <Select style={{width: 120}} options={[
                  {label: '全国', value: 'country'},
                  {label: '省级', value: 'province'},
                  {label: '城市', value: 'city'},
                  {label: '区县', value: 'district'},
                ]} />
              </Form.Item>
              <Form.Item name="scope_code" label="行政区代码" rules={[{required: true}]}><Input /></Form.Item>
              <Form.Item name="scope_name" label="行政区名称" rules={[{required: true}]}><Input /></Form.Item>
              <Form.Item name="stat_period" label="统计期"><Input placeholder="例如：2025" /></Form.Item>
            </Space>
            <Space wrap>
              <input
                type="file"
                accept=".csv,.xlsx,.pdf"
                onChange={event => setFile(event.target.files?.[0] || null)}
              />
              <Button type="primary" htmlType="submit" loading={loading === 'upload'}>导入官方文件</Button>
              <Typography.Text type="secondary">{file ? `${file.name} · ${(file.size / 1024).toFixed(1)}KB` : '未选择文件'}</Typography.Text>
            </Space>
          </Form>
        </Card>

        <Card
          size="small"
          title={`待审核指标（${pending.length}）`}
          extra={<Button size="small" loading={loading === 'review'} onClick={loadPending}>刷新</Button>}
        >
          <List
            size="small"
            dataSource={pending}
            locale={{emptyText: adminToken.trim() ? '暂无待审核指标' : '验证管理员 Token 后查看'}}
            renderItem={item => (
              <List.Item
                actions={[
                  <Button key="confirm" size="small" type="primary" loading={loading === `review-${item.id}`} onClick={() => review(item.id, 'confirmed')}>确认</Button>,
                  <Button key="reject" size="small" danger loading={loading === `review-${item.id}`} onClick={() => review(item.id, 'rejected')}>排除</Button>,
                ]}
              >
                <List.Item.Meta
                  title={<Space><span>{item.metric_name}</span><Tag>{item.scope_name}</Tag><Tag>{item.stat_period}</Tag></Space>}
                  description={`${item.value_numeric ?? item.value_text ?? '--'}${item.unit || ''} · ${item.source_name} · ${item.source_format.toUpperCase()}`}
                />
              </List.Item>
            )}
          />
        </Card>
      </Space>
    </Card>
  );
}
