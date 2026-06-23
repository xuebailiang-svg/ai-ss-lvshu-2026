import {useEffect, useState} from 'react';
import {Alert, Card, Descriptions, List, Progress, Result, Spin} from 'antd';
import {useParams} from 'react-router-dom';
import ReactECharts from 'echarts-for-react';
import {getEvaluation, report} from '../api/client';
import type {Evaluation} from '../types';

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
  if (!ev || !rep) {
    return (
      <div className="loading">
        <Spin /> 正在加载报告
      </div>
    );
  }

  const score = ev.result!;
  return (
    <div className="page report">
      <h2>{ev.name} · 选址评估报告</h2>
      <Alert
        type={rep.hard_risk ? 'error' : 'info'}
        showIcon
        message={rep.hard_risk ? '存在硬性风险' : '未发现已知硬性风险'}
        description={rep.disclaimer}
      />
      <Alert
        type="info"
        showIcon
        message="M1 当前报告为规则评分报告，不调用大模型"
        description="系统根据高德 POI、人工物业信息和内置评分规则生成结论；当前版本不会调用 OpenAI、DeepSeek、通义千问或其他 LLM API。"
      />
      <Card title="综合结论">
        <div className="score">
          {score.total_score}
          <small>/100</small>
        </div>
        <h3>{score.recommendation}</h3>
        <Progress percent={score.confidence} format={percent => `可信度 ${percent}%`} />
      </Card>
      <Card title="各维度得分">
        <ReactECharts
          style={{height: 300}}
          option={{
            tooltip: {},
            xAxis: {
              type: 'category',
              data: Object.keys(score.dimensions),
              axisLabel: {interval: 0, rotate: 16},
            },
            yAxis: {type: 'value'},
            series: [{type: 'bar', data: Object.values(score.dimensions), itemStyle: {color: '#2563a6'}}],
          }}
        />
      </Card>
      <Card title="证据与风险">
        <Descriptions
          column={1}
          items={[
            {key: 'p', label: '加分证据', children: score.positive_evidence.join('；')},
            {key: 'n', label: '扣分证据', children: score.negative_evidence.join('；')},
            {
              key: 'r',
              label: '硬性风险',
              children: score.hard_risks.map(item => item.message).join('；') || '无',
            },
          ]}
        />
      </Card>
      <Card title="待人工调查清单">
        <List dataSource={score.review_items} renderItem={item => <List.Item>{item}</List.Item>} />
      </Card>
      <Card title="数据来源">
        <p>高德地图 Web 服务（GCJ-02 原始坐标）与用户人工填写物业信息；采集结果保留来源、时间、可信度和原始响应。</p>
        <p>{rep.data_note}</p>
        <p>评分规则版本：{score.model_version}</p>
      </Card>
    </div>
  );
}
