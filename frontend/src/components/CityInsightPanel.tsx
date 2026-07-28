import {Alert, Card, Col, Empty, List, Row, Space, Statistic, Tag, Typography} from 'antd';
import ReactECharts from 'echarts-for-react';
import type {CityInsight, RegionalStatistic} from '../api/projects';

type Props = {
  insight: CityInsight;
};

const GROUP_LABELS: Record<string, string> = {
  population: '人口',
  economy: '经济',
  consumption: '消费',
  employment: '就业',
};

const SCOPE_LABELS: Record<string, string> = {
  country: '全国',
  province: '省级',
  city: '城市',
  district: '区县',
};

function flattenMetrics(insight: CityInsight) {
  const rows: RegionalStatistic[] = [];
  Object.values(insight.macro_context || {}).forEach(scopes => {
    Object.values(scopes || {}).forEach(items => rows.push(...(items || [])));
  });
  return rows;
}

function formatMetric(item: RegionalStatistic) {
  const value = item.value_numeric ?? item.value_text ?? '--';
  return `${value}${item.unit || ''}`;
}

function latestMetric(rows: RegionalStatistic[], code: string) {
  return rows
    .filter(item => item.metric_code === code)
    .sort((a, b) => {
      const scopePriority = {district: 4, city: 3, province: 2, country: 1};
      return (scopePriority[b.scope_level] || 0) - (scopePriority[a.scope_level] || 0)
        || String(b.stat_period).localeCompare(String(a.stat_period));
    })[0];
}

export default function CityInsightPanel({insight}: Props) {
  const metrics = flattenMetrics(insight);
  const headlineCodes = [
    'resident_population',
    'gdp',
    'tertiary_industry_share',
    'retail_sales_total',
    'disposable_income_per_capita',
    'consumption_expenditure_per_capita',
  ];
  const headlines = headlineCodes.map(code => latestMetric(metrics, code)).filter(Boolean) as RegionalStatistic[];
  const tertiary = latestMetric(metrics, 'tertiary_industry_share');
  const tertiaryShare = Math.max(0, Math.min(100, Number(tertiary?.value_numeric || 0)));
  const poi = insight.trade_area_context?.poi || {};
  const supporting = insight.trade_area_context?.supporting || {food_count: 0, entertainment_count: 0};
  const radarValues = [
    Number(poi.transport || 0),
    Number(poi.education || 0),
    Number(poi.residential || 0),
    Number(supporting.food_count || 0),
    Number(supporting.entertainment_count || 0),
  ];
  const radarMax = Math.max(10, ...radarValues) * 1.2;

  return (
    <Card title="城市洞察" className="v11-city-insight">
      <Alert
        type={insight.status === 'ready' ? 'info' : insight.status === 'collecting' ? 'warning' : 'error'}
        showIcon
        message={insight.status === 'ready'
          ? `${insight.scope.city || '当前城市'}宏观背景已加载`
          : insight.status === 'collecting'
            ? '政府公开数据正在后台同步'
            : '政府公开数据暂时不可用'}
        description={insight.data_quality?.scope_warning || '城市和区县统计只作为宏观背景，不代表项目1km商圈。'}
      />

      <Typography.Title level={4}>城市与区域宏观背景</Typography.Title>
      {headlines.length ? (
        <Row gutter={[12, 12]}>
          {headlines.map(item => (
            <Col xs={24} sm={12} xl={8} key={`${item.scope_code}-${item.metric_code}`}>
              <Card size="small">
                <Statistic title={item.metric_name} value={formatMetric(item)} />
                <Space size={[4, 4]} wrap>
                  <Tag>{item.scope_name}</Tag>
                  <Tag color="blue">{item.stat_period}</Tag>
                  <Tag>{SCOPE_LABELS[item.scope_level] || item.scope_level}口径</Tag>
                </Space>
                <Typography.Text type="secondary">{item.source_name}</Typography.Text>
              </Card>
            </Col>
          ))}
        </Row>
      ) : (
        <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无已确认的城市宏观指标" />
      )}

      <Row gutter={[12, 12]} style={{marginTop: 12}}>
        <Col xs={24} xl={12}>
          <Card size="small" title="产业结构（宏观统计）">
            {tertiary ? (
              <>
                <ReactECharts
                  style={{height: 250}}
                  option={{
                    tooltip: {trigger: 'item'},
                    legend: {bottom: 0},
                    series: [{
                      type: 'pie',
                      radius: ['45%', '70%'],
                      data: [
                        {name: '第三产业', value: tertiaryShare},
                        {name: '其他产业', value: Math.max(0, 100 - tertiaryShare)},
                      ],
                    }],
                  }}
                />
                <Typography.Text type="secondary">
                  {tertiary.scope_name} · {tertiary.stat_period} · {tertiary.source_name}
                </Typography.Text>
              </>
            ) : (
              <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无第三产业占比数据" />
            )}
          </Card>
        </Col>
        <Col xs={24} xl={12}>
          <Card size="small" title={`${insight.trade_area_context?.scope?.radius_meters || '--'}米商圈配套（项目数据）`}>
            <ReactECharts
              style={{height: 250}}
              option={{
                radar: {
                  indicator: [
                    {name: '交通', max: radarMax},
                    {name: '教育', max: radarMax},
                    {name: '住宅', max: radarMax},
                    {name: '餐饮', max: radarMax},
                    {name: '娱乐', max: radarMax},
                  ],
                },
                series: [{type: 'radar', data: [{name: '商圈POI', value: radarValues}]}],
              }}
            />
            <Typography.Text type="secondary">
              {insight.trade_area_context?.scope?.note || '本图为项目分析半径内POI统计。'}
            </Typography.Text>
          </Card>
        </Col>
      </Row>

      <Row gutter={[12, 12]} style={{marginTop: 12}}>
        {Object.entries(insight.macro_context || {}).map(([group, scopes]) => (
          <Col xs={24} xl={12} key={group}>
            <Card size="small" title={`${GROUP_LABELS[group] || group}指标`}>
              <List
                size="small"
                dataSource={Object.values(scopes || {}).flat()}
                locale={{emptyText: '暂无数据'}}
                renderItem={item => (
                  <List.Item>
                    <List.Item.Meta
                      title={`${item.metric_name}：${formatMetric(item)}`}
                      description={`${item.scope_name} · ${item.stat_period} · ${item.source_name}`}
                    />
                  </List.Item>
                )}
              />
            </Card>
          </Col>
        ))}
      </Row>

      <Alert
        style={{marginTop: 12}}
        type="warning"
        showIcon
        message="微观客流数据缺口"
        description={`${insight.lbs_context?.message || '未接入真实客流数据。'} 缺少：${(insight.lbs_context?.missing || []).join('、') || '无'}`}
      />

      <Typography.Title level={5} style={{marginTop: 16}}>数据来源与口径</Typography.Title>
      <List
        size="small"
        dataSource={insight.sources || []}
        locale={{emptyText: '暂无来源记录'}}
        renderItem={item => (
          <List.Item>
            <Space size={[6, 6]} wrap>
              <Typography.Link href={item.source_url} target="_blank" rel="noreferrer">{item.source_name}</Typography.Link>
              <Tag>{item.scope_name}</Tag>
              <Tag color="blue">{item.stat_period}</Tag>
            </Space>
          </List.Item>
        )}
      />
    </Card>
  );
}
