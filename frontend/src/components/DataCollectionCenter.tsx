import {Alert, Button, Card, Col, Row, Space, Statistic, Tag, Typography} from 'antd';
import {FormOutlined, ReloadOutlined} from '@ant-design/icons';
import {useNavigate} from 'react-router-dom';

function numberValue(value: unknown) {
  return Math.max(0, Number(value) || 0);
}

export default function DataCollectionCenter({
  projectId,
  stats,
  collecting,
  collectResult,
  collectError,
  collectingCompetitors,
  competitorCollectResult,
  competitorCollectError,
  onCollectCompetitors,
  collectingSupporting,
  supportingCollectResult,
  supportingCollectError,
  onCollectSupporting,
}: {
  projectId: string;
  stats: Record<string, any>;
  collecting: boolean;
  collectResult: any;
  collectError: string;
  collectingCompetitors: boolean;
  competitorCollectResult: any;
  competitorCollectError: string;
  onCollectCompetitors: () => void;
  collectingSupporting: boolean;
  supportingCollectResult: any;
  supportingCollectError: string;
  onCollectSupporting: () => void;
  onCompetitorReviewed?: () => void | Promise<void>;
  onCompetitorDetailSaved?: () => Promise<{previousScore: number | null; currentScore: number}>;
}) {
  const navigate = useNavigate();
  const poiCount = numberValue(stats?.poi_count ?? collectResult?.collected?.poi_count);
  const competitorCount = numberValue(stats?.competitor_count ?? competitorCollectResult?.saved_count);
  const foodCount = numberValue(stats?.food_count ?? supportingCollectResult?.food_count);
  const entertainmentCount = numberValue(stats?.entertainment_count ?? supportingCollectResult?.entertainment_count);

  return (
    <Card
      className="data-collection-center"
      title="数据采集概览"
      extra={<Tag color={poiCount > 0 ? 'green' : 'default'}>{poiCount > 0 ? '已有高德数据' : '等待采集'}</Tag>}
      style={{marginBottom: 16}}
    >
      <Typography.Paragraph type="secondary">
        这里仅展示自动采集进度。竞品有效性、配套营业状态和候选物业条件统一进入独立的“人工核实”页面处理。
      </Typography.Paragraph>
      {(collectError || competitorCollectError || supportingCollectError) && (
        <Alert
          type="warning"
          showIcon
          style={{marginBottom: 12}}
          message="部分采集任务未完成"
          description={[collectError, competitorCollectError, supportingCollectError].filter(Boolean).join('；')}
        />
      )}
      <Row gutter={[12, 12]}>
        <Col xs={12} md={6}><Statistic title="周边 POI" value={poiCount} /></Col>
        <Col xs={12} md={6}><Statistic title="疑似竞品" value={competitorCount} suffix="家" /></Col>
        <Col xs={12} md={6}><Statistic title="餐饮候选" value={foodCount} suffix="家" /></Col>
        <Col xs={12} md={6}><Statistic title="娱乐候选" value={entertainmentCount} suffix="家" /></Col>
      </Row>
      <Space wrap style={{marginTop: 16}}>
        <Button icon={<ReloadOutlined />} loading={collectingCompetitors} onClick={onCollectCompetitors}>
          {competitorCount > 0 ? '重新整理疑似竞品' : '整理疑似竞品'}
        </Button>
        <Button icon={<ReloadOutlined />} loading={collectingSupporting} onClick={onCollectSupporting}>
          {foodCount + entertainmentCount > 0 ? '重新整理周边配套' : '整理周边配套'}
        </Button>
        <Button type="primary" icon={<FormOutlined />} onClick={() => navigate(`/projects/${projectId}/supplement`)}>
          进入人工核实
        </Button>
      </Space>
      {collecting && <Typography.Text type="secondary" style={{display: 'block', marginTop: 12}}>高德基础 POI 正在采集中…</Typography.Text>}
    </Card>
  );
}
