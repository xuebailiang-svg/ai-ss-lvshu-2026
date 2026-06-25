import {useEffect, useState} from 'react';
import {Button, Card, Empty, Input, Modal, Progress, Select, Space, Table, Tag, message} from 'antd';
import {useNavigate} from 'react-router-dom';
import ReactECharts from 'echarts-for-react';
import {compareEvaluations, listEvaluations, score} from '../api/client';
import type {Evaluation} from '../types';

export default function History() {
  const [rows, setRows] = useState<Evaluation[]>([]);
  const [q, setQ] = useState('');
  const [city, setCity] = useState('');
  const [recommendation, setRecommendation] = useState<string>();
  const [hasHardRisk, setHasHardRisk] = useState<boolean | undefined>();
  const [sortBy, setSortBy] = useState('created_at');
  const [order, setOrder] = useState('desc');
  const [selectedRowKeys, setSelectedRowKeys] = useState<React.Key[]>([]);
  const [comparison, setComparison] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const nav = useNavigate();

  const load = () => {
    setLoading(true);
    listEvaluations({q, city, recommendation, has_hard_risk: hasHardRisk, sort_by: sortBy, order})
      .then(setRows)
      .finally(() => setLoading(false));
  };

  useEffect(load, []);

  const rescore = async (id: number) => {
    await score(id);
    message.success('已重新评分，原始采集数据已保留');
    load();
  };

  const compare = async () => {
    const ids = selectedRowKeys.map(Number);
    if (ids.length < 2 || ids.length > 5) {
      message.warning('请选择 2～5 个评估记录');
      return;
    }
    const data = await compareEvaluations(ids);
    setComparison(data.items);
  };

  return (
    <div className="page">
      <h2>历史评估</h2>
      <Space wrap>
        <Input placeholder="城市" value={city} onChange={event => setCity(event.target.value)} />
        <Input.Search placeholder="搜索地址" value={q} onChange={event => setQ(event.target.value)} onSearch={load} />
        <Select allowClear placeholder="推荐等级" style={{width: 160}} value={recommendation} onChange={setRecommendation} options={[
          {label: '推荐', value: '推荐'},
          {label: '谨慎评估', value: '谨慎评估'},
          {label: '暂不推荐', value: '暂不推荐'},
          {label: '高风险', value: '高风险，可能不符合准入'},
        ]} />
        <Select allowClear placeholder="硬性风险" style={{width: 140}} value={hasHardRisk} onChange={setHasHardRisk} options={[
          {label: '存在硬性风险', value: true},
          {label: '无硬性风险', value: false},
        ]} />
        <Select value={sortBy} style={{width: 140}} onChange={setSortBy} options={[
          {label: '创建时间', value: 'created_at'},
          {label: '综合评分', value: 'score'},
          {label: '完整度', value: 'completeness'},
          {label: '最近更新', value: 'updated_at'},
        ]} />
        <Select value={order} style={{width: 100}} onChange={setOrder} options={[{label: '降序', value: 'desc'}, {label: '升序', value: 'asc'}]} />
        <Button onClick={load}>筛选</Button>
        <Button onClick={compare} disabled={selectedRowKeys.length < 2}>对比</Button>
      </Space>

      <Table
        loading={loading}
        locale={{emptyText: <Empty description="暂无评估记录" />}}
        rowKey="id"
        rowSelection={{selectedRowKeys, onChange: setSelectedRowKeys}}
        dataSource={rows}
        columns={[
          {title: '评估名称', dataIndex: 'name'},
          {title: '城市', dataIndex: 'city'},
          {title: '地址', dataIndex: 'address'},
          {title: '状态', dataIndex: 'status', render: value => <Tag>{value}</Tag>},
          {title: '推荐等级', render: (_, row) => row.result?.recommendation || '-'},
          {title: '硬性风险', render: (_, row) => row.result?.hard_risks?.length ? <Tag color="red">{row.result.hard_risks.length}</Tag> : <Tag>0</Tag>},
          {title: '评分', render: (_, row) => row.result?.total_score ?? '-'},
          {title: '完整度', render: (_, row) => <Progress percent={row.result?.completeness || 0} size="small" />},
          {title: '最近更新', dataIndex: 'updated_at', render: value => value ? new Date(value).toLocaleString() : '-'},
          {
            title: '操作',
            render: (_, row) => (
              <Space>
                <Button onClick={() => nav(`/reports/${row.id}`)}>打开报告</Button>
                <Button onClick={() => rescore(row.id)}>重新评分</Button>
              </Space>
            ),
          },
        ]}
      />

      <Modal title="候选地址对比" open={comparison.length > 0} width={1100} footer={null} onCancel={() => setComparison([])}>
        <Card size="small">
          <ReactECharts
            style={{height: 260}}
            option={{
              tooltip: {},
              legend: {},
              xAxis: {type: 'category', data: comparison.map(item => item.name)},
              yAxis: {type: 'value'},
              series: [
                {name: '综合评分', type: 'bar', data: comparison.map(item => item.total_score || 0)},
                {name: '完整度', type: 'bar', data: comparison.map(item => item.completeness || 0)},
              ],
            }}
          />
        </Card>
        <Table
          size="small"
          rowKey="id"
          pagination={false}
          dataSource={comparison}
          columns={[
            {title: '地址', dataIndex: 'address'},
            {title: '城市', dataIndex: 'city'},
            {title: '综合评分', dataIndex: 'total_score'},
            {title: '推荐等级', dataIndex: 'recommendation'},
            {title: '硬性风险', dataIndex: 'hard_risk_count'},
            {title: '竞品数量', dataIndex: 'competitor_count'},
            {title: '强竞品', dataIndex: 'strong_competitor_count'},
            {title: '交通', dataIndex: 'transport_score'},
            {title: '人口代理', dataIndex: 'population_score'},
            {title: '商业配套', dataIndex: 'commercial_score'},
            {title: '物业', dataIndex: 'property_score'},
            {title: '完整度', dataIndex: 'completeness'},
            {title: '月租金', dataIndex: 'monthly_rent'},
            {title: '每台分摊租金', dataIndex: 'rent_per_machine_month'},
            {title: '待核实项', dataIndex: 'review_item_count'},
          ]}
        />
      </Modal>
    </div>
  );
}
