import {Card, Progress, Space, Statistic, Tag} from 'antd';

const names: Record<string, string> = {
  population: '人口',
  traffic: '交通',
  support: '配套',
  competitor: '竞品',
  rent: '成本',
};

export default function ScorePanel({score}: {score: any}) {
  if (!score) {
    return <Card title="评分结果">尚未评分。</Card>;
  }
  return (
    <Card title="评分结果">
      <Space wrap size="large" style={{marginBottom: 16}}>
        <Statistic title="综合评分" value={score.total_score} />
        <Statistic title="推荐等级" value={score.level} />
        <Statistic title="置信度" value={score.confidence} />
      </Space>
      {Object.entries(score.dimensions || {}).map(([key, value]: [string, any]) => (
        <div key={key} style={{marginBottom: 12}}>
          <Space>
            <strong>{names[key] || key}</strong>
            <Tag>{value.score}/{value.max}</Tag>
          </Space>
          <Progress percent={Math.round((Number(value.score || 0) / Number(value.max || 1)) * 100)} />
        </div>
      ))}
    </Card>
  );
}
