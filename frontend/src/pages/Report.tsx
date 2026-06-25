import {useEffect, useState} from 'react';
import {Alert, Card, Descriptions, List, Progress, Result, Spin, Table, Tag} from 'antd';
import {useParams} from 'react-router-dom';
import ReactECharts from 'echarts-for-react';
import {getEvaluation, report} from '../api/client';
import type {Evaluation} from '../types';

type CompetitorReportItem = {
  id: number;
  name: string;
  distance_m?: number;
  amap_data?: {address?: string};
  manual_data?: {machine_count?: number; normal_price?: number};
  occupancy?: {peak_occupancy_rate?: number; label?: string};
  verified?: boolean;
};

function dataTypeTag(type?: string) {
  if (type === '自动采集') return <Tag color="blue">自动采集</Tag>;
  if (type === '人工填写') return <Tag color="green">人工填写</Tag>;
  if (type === '估算') return <Tag color="purple">估算</Tag>;
  return <Tag color="orange">未核实</Tag>;
}

function ChecklistTable({items}: {items?: any[]}) {
  return (
    <Table
      size="small"
      rowKey={(row, index) => `${row.name}-${index}`}
      pagination={false}
      dataSource={items || []}
      columns={[
        {title: '核查项', dataIndex: 'name'},
        {title: '状态', dataIndex: 'status', render: (value: string) => value === '已确认' ? <Tag color="green">已确认</Tag> : <Tag color="orange">待人工核实</Tag>},
        {title: '数据属性', dataIndex: 'data_type', render: dataTypeTag},
        {title: '结果', dataIndex: 'value', render: (value: any) => {
          if (Array.isArray(value)) return value.length ? value.map(item => item.name || item).join('；') : '未采集到';
          if (value && typeof value === 'object') return Object.entries(value).map(([key, val]) => `${key}: ${val}`).join('；') || '-';
          return value ?? '未采集到';
        }},
        {title: '说明', dataIndex: 'note', render: (value?: string) => value || '-'},
      ]}
    />
  );
}

export default function ReportPage() {
  const {id} = useParams();
  const [ev, setEv] = useState<Evaluation>();
  const [rep, setRep] = useState<any>();
  const [error, setError] = useState('');

  useEffect(() => {
    if (!id) return;
    Promise.all([getEvaluation(id), report(id)])
      .then(([evaluation, reportData]) => {
        setEv(evaluation);
        setRep(reportData);
      })
      .catch(error => {
        const status = error.response?.status;
        const detail = error.response?.data?.detail;
        if (status === 409) setError('请先生成评分。');
        else setError(typeof detail === 'string' ? detail : error.message);
      });
  }, [id]);

  if (error) return <Result status="warning" title="报告暂不可用" subTitle={error} />;
  if (!ev || !rep) return <div className="loading"><Spin /> 正在加载报告</div>;

  const score = ev.result!;
  const sections = rep.sections || {};
  const competitorItems = sections.competitors?.items || [];
  const dimensionEntries = Object.entries(score.dimensions || {});
  const emptyText = (name: string) => <Alert type="info" showIcon message={`${name}未采集到`} description="该结果只表示本次自动采集未返回该类 POI，建议扩大半径或现场复核。" />;

  return (
    <div className="page report">
      <h2>{ev.name} · 选址评估报告</h2>
      <Alert type={rep.hard_risk ? 'error' : 'info'} showIcon message={rep.hard_risk ? '存在硬性风险' : '未发现已知硬性风险'} description={rep.disclaimer} />
      <Alert type="info" showIcon message="M1.5 当前报告为规则评分报告，不调用大模型" description="报告只展示自动采集数据、人工填写数据和规则评分依据，不会凭空生成经营数据。" />

      <Card title="1. 结论摘要">
        <div className="score">{score.total_score}<small>/100</small></div>
        <h3>{score.recommendation}</h3>
        <List size="small" dataSource={(sections.summary?.basis || []) as string[]} renderItem={item => <List.Item>{String(item)}</List.Item>} />
      </Card>

      <Card title="2. 硬性风险">
        {score.hard_risks.length ? (
          <List dataSource={score.hard_risks} renderItem={item => <List.Item><Tag color="red">高风险</Tag>{item.message}</List.Item>} />
        ) : <Alert type="success" message="未发现已知硬性风险" />}
      </Card>

      <Card title="3. 综合评分">
        <div className="score">{score.total_score}<small>/100</small></div>
        <h3>{score.recommendation}</h3>
      </Card>

      <Card title="4. 各维度得分">
        <ReactECharts
          style={{height: Math.max(360, dimensionEntries.length * 34)}}
          option={{
            grid: {left: 150, right: 40, top: 24, bottom: 24},
            tooltip: {trigger: 'axis', axisPointer: {type: 'shadow'}},
            xAxis: {type: 'value', max: 'dataMax'},
            yAxis: {
              type: 'category',
              data: dimensionEntries.map(([name]) => name).reverse(),
              axisLabel: {interval: 0, width: 130, overflow: 'break'},
            },
            series: [{
              type: 'bar',
              data: dimensionEntries.map(([, value]) => value).reverse(),
              label: {show: true, position: 'right'},
              itemStyle: {color: '#2563a6'},
            }],
          }}
        />
      </Card>

      <Card title="数据完整度和核实状态">
        <Descriptions column={2} items={[
          {key: 'c', label: '完整度', children: <Progress percent={score.completeness} />},
          {key: 'm', label: '人工竞品调研', children: `${sections.competitors?.manual_survey_count || 0}/${sections.competitors?.auto_collected_count || 0}`},
          {key: 'v', label: '评分规则版本', children: score.model_version},
        ]} />
      </Card>

      <Card title="5. 竞品分析">
        <Alert type="info" showIcon message="竞品数据分层展示" description="已采集竞品来自高德 POI；价格、机器配置、机器数量、上座率、充值活动、开业年限需要人工调研补充。" />
        <Table
          size="small"
          rowKey="id"
          pagination={false}
          dataSource={competitorItems as CompetitorReportItem[]}
          columns={[
            {title: '竞品', dataIndex: 'name'},
            {title: '距离', dataIndex: 'distance_m', render: value => value ? `${value}m` : '-'},
            {title: '高德数据', render: (_, row: CompetitorReportItem) => row.amap_data?.address || '-'},
            {title: '机器数', render: (_, row: CompetitorReportItem) => row.manual_data?.machine_count ?? '-'},
            {title: '普通价', render: (_, row: CompetitorReportItem) => row.manual_data?.normal_price ?? '-'},
            {title: '高峰上座率', render: (_, row: CompetitorReportItem) => row.occupancy?.peak_occupancy_rate != null ? <span>{Math.round(row.occupancy.peak_occupancy_rate * 100)}% <Tag>估算值</Tag></span> : '-'},
            {title: '核实', render: (_, row: CompetitorReportItem) => row.verified ? <Tag color="green">人工核实</Tag> : <Tag color="orange">未核实</Tag>},
          ]}
        />
        <ChecklistTable items={sections.competitors?.checklist || []} />
      </Card>

      <Card title="6. 周边配套">
        <ChecklistTable items={sections.surroundings?.checklist || sections.commercial?.checklist || []} />
      </Card>

      <Card title="7. 交通与可达性">
        {(sections.traffic?.items || []).length ? (
          <List size="small" dataSource={sections.traffic?.items || []} renderItem={(item: any) => <List.Item>{item.name} · {item.distance_m || '-'}m · 自动采集</List.Item>} />
        ) : emptyText('交通')}
        <ChecklistTable items={sections.traffic?.checklist || []} />
      </Card>

      <Card title="8. 人口代理">
        <Alert type="warning" showIcon message="人口代理指标不是实际人口" description={sections.population_proxy?.note || rep.data_note} />
        {(sections.population_proxy?.items || []).length ? (
          <List size="small" dataSource={sections.population_proxy?.items || []} renderItem={(item: any) => <List.Item>{item.name} · 自动采集</List.Item>} />
        ) : emptyText('人口代理指标')}
        <ChecklistTable items={sections.population_proxy?.checklist || []} />
      </Card>

      <Card title="9. 敏感场所与合规">
        {(sections.sensitive_places?.items || []).length ? (
          <List size="small" dataSource={sections.sensitive_places?.items || []} renderItem={(item: any) => <List.Item>{item.name} · {item.distance_m || '-'}m · 自动采集</List.Item>} />
        ) : emptyText('敏感场所')}
        <ChecklistTable items={sections.sensitive_places?.checklist || []} />
      </Card>

      <Card title="10. 物业与租金">
        <Descriptions column={2} items={[
          {key: 'rent', label: '月总租金', children: sections.property_cost?.rent_summary?.monthly_rent ?? '-'},
          {key: 'sqm_month', label: '元/㎡/月', children: sections.property_cost?.rent_summary?.rent_per_sqm_month ?? '-'},
          {key: 'sqm_day', label: '元/㎡/天', children: sections.property_cost?.rent_summary?.rent_per_sqm_day ?? '-'},
          {key: 'machine', label: '每台机器分摊月租金', children: sections.property_cost?.rent_summary?.rent_per_machine_month ?? '-'},
          {key: 'source', label: '数据属性', children: <Tag color="blue">人工填写数据</Tag>},
        ]} />
        <ChecklistTable items={sections.property_cost?.checklist || []} />
      </Card>

      <Card title="11. 消防、供电、网络、夜间入口">
        <ChecklistTable items={sections.infrastructure?.checklist || []} />
      </Card>

      <Card title="12. 数据来源和核实状态">
        <Descriptions column={1} items={[
          {key: 'quality', label: '数据完整度', children: `${score.completeness}%`},
          {key: 'auto', label: '自动采集数据', children: (sections.data_sources?.auto || []).join('；')},
          {key: 'manual', label: '人工填写数据', children: (sections.data_sources?.manual || []).join('；')},
          {key: 'estimated', label: '估算数据', children: (sections.data_sources?.estimated || []).join('；')},
          {key: 'unverified', label: '未核实数据', children: (sections.data_sources?.unverified || []).join('；')},
        ]} />
      </Card>

      <Card title="13. 人工核实清单">
        <List dataSource={sections.manual_checklist?.items || score.review_items} renderItem={(item: string) => <List.Item><Tag color="orange">待核实</Tag>{item}</List.Item>} />
      </Card>

      <Card title="14. 下一步调研建议">
        <List dataSource={sections.next_steps?.items || []} renderItem={(item: string) => <List.Item>{item}</List.Item>} />
      </Card>

      <Card title="评分规则说明">
        <p>评分规则版本：{score.model_version}</p>
        <p>{sections.scoring_rules?.note || '硬性风险与普通评分分离，高分不能覆盖准入风险。'}</p>
      </Card>
    </div>
  );
}
