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
      .catch(error => setError(error.response?.data?.detail || error.message));
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

      <Card title="4. 数据完整度和可信度">
        <Descriptions column={2} items={[
          {key: 'c', label: '完整度', children: <Progress percent={score.completeness} />},
          {key: 'f', label: '可信度', children: <Progress percent={score.confidence} />},
          {key: 'm', label: '人工竞品调研', children: `${sections.competitors?.manual_survey_count || 0}/${sections.competitors?.auto_collected_count || 0}`},
          {key: 'v', label: '评分规则版本', children: score.model_version},
        ]} />
      </Card>

      <Card title="5. 竞品分析">
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
      </Card>

      <Card title="6. 交通分析">
        {(sections.traffic?.items || []).length ? (
          <List size="small" dataSource={sections.traffic?.items || []} renderItem={(item: any) => <List.Item>{item.name} · {item.distance_m || '-'}m · 自动采集</List.Item>} />
        ) : emptyText('交通')}
      </Card>

      <Card title="6.1 敏感场所">
        {(sections.sensitive_places?.items || []).length ? (
          <List size="small" dataSource={sections.sensitive_places?.items || []} renderItem={(item: any) => <List.Item>{item.name} · {item.distance_m || '-'}m · 自动采集</List.Item>} />
        ) : emptyText('敏感场所')}
      </Card>

      <Card title="7. 人口代理指标">
        <Alert type="warning" showIcon message="人口代理指标不是实际人口" description={sections.population_proxy?.note || rep.data_note} />
        {(sections.population_proxy?.items || []).length ? (
          <List size="small" dataSource={sections.population_proxy?.items || []} renderItem={(item: any) => <List.Item>{item.name} · 自动采集</List.Item>} />
        ) : emptyText('人口代理指标')}
      </Card>

      <Card title="8. 商业配套">
        {(sections.commercial?.items || []).length ? (
          <List size="small" dataSource={sections.commercial?.items || []} renderItem={(item: any) => <List.Item>{item.name} · 自动采集</List.Item>} />
        ) : emptyText('商业配套')}
      </Card>

      <Card title="9. 物业与成本">
        <Descriptions column={2} items={[
          {key: 'rent', label: '月总租金', children: sections.property_cost?.rent_summary?.monthly_rent ?? '-'},
          {key: 'sqm_month', label: '元/㎡/月', children: sections.property_cost?.rent_summary?.rent_per_sqm_month ?? '-'},
          {key: 'sqm_day', label: '元/㎡/天', children: sections.property_cost?.rent_summary?.rent_per_sqm_day ?? '-'},
          {key: 'machine', label: '每台机器分摊月租金', children: sections.property_cost?.rent_summary?.rent_per_machine_month ?? '-'},
          {key: 'source', label: '数据属性', children: <Tag color="blue">人工填写数据</Tag>},
        ]} />
      </Card>

      <Card title="10. 待人工核实事项">
        <List dataSource={score.review_items} renderItem={item => <List.Item><Tag color="orange">待核实</Tag>{item}</List.Item>} />
      </Card>

      <Card title="11. 数据来源">
        <Descriptions column={1} items={[
          {key: 'auto', label: '自动采集数据', children: (sections.data_sources?.auto || []).join('；')},
          {key: 'manual', label: '人工填写数据', children: (sections.data_sources?.manual || []).join('；')},
          {key: 'estimated', label: '估算数据', children: (sections.data_sources?.estimated || []).join('；')},
          {key: 'unverified', label: '未核实数据', children: (sections.data_sources?.unverified || []).join('；')},
        ]} />
      </Card>

      <Card title="12. 评分规则说明">
        <p>评分规则版本：{score.model_version}</p>
        <p>{sections.scoring_rules?.note || '硬性风险与普通评分分离，高分不能覆盖准入风险。'}</p>
      </Card>
    </div>
  );
}
