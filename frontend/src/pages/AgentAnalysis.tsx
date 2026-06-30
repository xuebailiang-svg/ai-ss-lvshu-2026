import {useEffect, useState} from 'react';
import {Alert, Button, Card, Collapse, Descriptions, Form, Input, InputNumber, List, Select, Space, Spin, Steps, Tag} from 'antd';
import {runSiteSelectionAgent, saveSiteFeedback, systemHealth} from '../api/client';

type AgentStep = {
  step: number;
  tool_name: string;
  status: string;
  summary: string;
  duration_ms: number;
  confidence: number;
  sources: string[];
  warnings: string[];
  output?: any;
};

export default function AgentAnalysis() {
  const [form] = Form.useForm();
  const [feedbackForm] = Form.useForm();
  const [busy, setBusy] = useState(false);
  const [feedbackBusy, setFeedbackBusy] = useState(false);
  const [result, setResult] = useState<any>();
  const [error, setError] = useState('');
  const [feedbackMessage, setFeedbackMessage] = useState('');
  const [health, setHealth] = useState<any>();

  useEffect(() => {
    systemHealth()
      .then(setHealth)
      .catch(() => setHealth({status: 'unknown', warnings: ['系统健康检查暂不可用']}));
  }, []);

  const run = async (values: any) => {
    setBusy(true);
    setError('');
    setResult(undefined);
    try {
      const data = await runSiteSelectionAgent({
        address: values.address,
        city: values.city,
        radius_meters: values.radius_meters || 1000,
        business_type: values.business_type || '电竞馆',
      });
      setResult(data);
    } catch (err: any) {
      setError(err?.response?.data?.detail || err.message || 'Agent 分析失败');
    } finally {
      setBusy(false);
    }
  };

  const submitFeedback = async (values: any) => {
    if (!result?.task_id) return;
    setFeedbackBusy(true);
    setFeedbackMessage('');
    try {
      await saveSiteFeedback({
        task_id: result.task_id,
        actual_result: values.actual_result,
        notes: values.notes,
        monthly_revenue_range: values.monthly_revenue_range,
      });
      setFeedbackMessage('已保存真实经营结果回填。后续相似案例检索会使用该反馈。');
    } catch (err: any) {
      setFeedbackMessage(err?.response?.data?.detail || err.message || '反馈保存失败');
    } finally {
      setFeedbackBusy(false);
    }
  };

  const report = result?.report || {};
  const score = result?.final_score || {};
  const steps: AgentStep[] = result?.steps || [];
  const plan = result?.plan || [];
  const reflection = result?.reflection || {};
  const dataQuality = report?.data_quality || {};
  const similarCases = result?.similar_cases || report?.similar_case_analysis?.cases || [];
  const trace = result?.trace || [];
  const debugTraceVisible = Boolean(health?.config?.ENABLE_DEBUG_API && trace.length);

  return (
    <div className="page">
      <h2>选址 Agent 分析</h2>
      <Alert
        type={health?.status === 'warning' ? 'warning' : 'success'}
        showIcon
        message={health?.status === 'warning' ? '系统可用但存在警告' : '系统状态正常'}
        description={(health?.warnings || []).join('；') || 'Agent 核心、配置中心和健康检查可用；当前不接入真实大模型。'}
      />

      <Card title="输入候选地址">
        <Form form={form} layout="vertical" onFinish={run} initialValues={{radius_meters: 1000, business_type: '电竞馆'}}>
          <div className="form-row">
            <Form.Item name="city" label="城市" rules={[{required: true, message: '请输入城市'}]}>
              <Input placeholder="例如：咸阳" />
            </Form.Item>
            <Form.Item name="radius_meters" label="分析半径（米）">
              <InputNumber min={100} max={10000} />
            </Form.Item>
          </div>
          <Form.Item name="address" label="候选地址" rules={[{required: true, message: '请输入候选地址'}]}>
            <Input.TextArea placeholder="例如：用户输入的候选地址" />
          </Form.Item>
          <Form.Item name="business_type" label="业态">
            <Input />
          </Form.Item>
          <Button type="primary" htmlType="submit" disabled={busy}>
            启动 Agent 分析
          </Button>
        </Form>
      </Card>

      {busy && <div className="loading"><Spin /> Agent 正在调用工具</div>}
      {error && <Alert type="error" showIcon message="Agent 分析失败" description={error} />}

      {result && (
        <>
          <Card title="Plan：Agent 计划">
            <Steps
              size="small"
              items={plan.map((item: any) => ({
                title: `${item.order}. ${item.tool_name}`,
                status: 'process',
              }))}
            />
            <List
              size="small"
              header="规划理由"
              dataSource={result.plan_reasoning || []}
              renderItem={(item: string) => <List.Item>{item}</List.Item>}
            />
          </Card>

          <Card title="Execution：实际执行过程">
            <Steps
              direction="vertical"
              items={steps.map(step => ({
                title: `${step.step}. ${step.tool_name}`,
                status: step.status === 'success' ? 'finish' : 'error',
                description: (
                  <Space direction="vertical">
                    <span>{step.summary}</span>
                    <span>耗时：{step.duration_ms}ms；置信度：{Math.round((step.confidence || 0) * 100)}%</span>
                    <Space wrap>
                      {(step.sources || []).map(source => <Tag key={source}>{source}</Tag>)}
                    </Space>
                    {step.output?.data?.partial_success && <Alert type="warning" showIcon message="partial_success：部分关键词采集失败，已保留成功数据。" />}
                    {(step.warnings || []).map(warning => <Alert key={warning} type="warning" showIcon message={warning} />)}
                  </Space>
                ),
              }))}
            />
          </Card>

          <Card title="Reflection：反思结果">
            <Descriptions column={1} items={[
              {key: 'recommendation', label: '建议', children: reflection.recommendation || '-'},
              {key: 'confidence_adjustment', label: '置信度调整', children: reflection.confidence_adjustment ?? 0},
              {key: 'risk_of_overestimate', label: '高估风险', children: reflection.risk_of_overestimate ?? '-'},
              {key: 'risk_of_underestimate', label: '低估风险', children: reflection.risk_of_underestimate ?? '-'},
              {key: 'adjusted_score_suggestion', label: '修正评分建议', children: reflection.adjusted_score_suggestion ?? '-'},
              {key: 'final_confidence', label: '综合置信度', children: reflection.final_confidence != null ? `${Math.round(reflection.final_confidence * 100)}%` : '-'},
            ]} />
            <h3>发现的问题</h3>
            <List size="small" dataSource={reflection.issues || []} renderItem={(item: string) => <List.Item><Tag color="orange">问题</Tag>{item}</List.Item>} />
            <h3>缺失数据</h3>
            <List size="small" dataSource={reflection.missing_data || []} renderItem={(item: string) => <List.Item><Tag>缺失</Tag>{item}</List.Item>} />
          </Card>

          {debugTraceVisible && <Card title="Trace Viewer：完整执行链">
            <Alert
              type="info"
              showIcon
              message={`Trace steps：${trace.length}`}
              description="Debug 模式下用于复盘、调试和回放每一次 Agent 决策。生产模式默认隐藏。"
            />
            <Collapse
              items={trace.map((step: any, index: number) => ({
                key: `${index}-${step.step_name}`,
                label: (
                  <Space wrap>
                    <Tag color={step.status === 'failed' ? 'red' : step.status === 'partial' ? 'orange' : 'green'}>
                      {step.status || 'unknown'}
                    </Tag>
                    <span>{index + 1}. {step.step_name || step.tool_name}</span>
                    <Tag>{step.duration_ms || 0}ms</Tag>
                    <Tag>置信度 {Math.round((step.confidence || 0) * 100)}%</Tag>
                  </Space>
                ),
                children: (
                  <Space direction="vertical" style={{width: '100%'}}>
                    <strong>Input</strong>
                    <pre style={{whiteSpace: 'pre-wrap'}}>{JSON.stringify(step.input || {}, null, 2)}</pre>
                    <strong>Output</strong>
                    <pre style={{whiteSpace: 'pre-wrap'}}>{JSON.stringify(step.output || {}, null, 2)}</pre>
                  </Space>
                ),
              }))}
            />
          </Card>}

          <Card title="历史相似案例">
            <Alert
              type={similarCases.length ? 'info' : 'warning'}
              showIcon
              message={similarCases.length ? `检索到 ${similarCases.length} 个历史相似案例` : '暂无历史相似案例'}
              description={report?.similar_case_analysis?.comparison_summary || '样本会随着真实经营结果回填逐步积累。'}
            />
            <List
              size="small"
              dataSource={similarCases}
              renderItem={(item: any) => (
                <List.Item>
                  <Space direction="vertical">
                    <span>{item.address || item.task_id}</span>
                    <Space wrap>
                      <Tag>相似度 {Math.round((item.similarity || 0) * 100)}%</Tag>
                      <Tag color={item.historical_result === 'profit' ? 'green' : item.historical_result === 'loss' ? 'red' : 'default'}>
                        历史结果 {item.historical_result || 'unknown'}
                      </Tag>
                      <Tag>评分 {item.score ?? '-'}</Tag>
                    </Space>
                    <span>关键差异：{(item.key_differences || []).join('、') || '暂无明显差异'}</span>
                  </Space>
                </List.Item>
              )}
            />
          </Card>

          <Card title="真实结果回填">
            <Alert type="info" showIcon message={`当前 task_id：${result.task_id}`} />
            <Form form={feedbackForm} layout="vertical" onFinish={submitFeedback} initialValues={{actual_result: 'unknown'}}>
              <Form.Item name="actual_result" label="是否真实成功" rules={[{required: true, message: '请选择真实结果'}]}>
                <Select
                  options={[
                    {value: 'profit', label: '盈利 / 成功'},
                    {value: 'loss', label: '亏损 / 失败'},
                    {value: 'unknown', label: '未知 / 暂不确定'},
                  ]}
                />
              </Form.Item>
              <Form.Item name="monthly_revenue_range" label="月营收区间（可选）">
                <Input placeholder="例如：10-20万" />
              </Form.Item>
              <Form.Item name="notes" label="真实经营情况备注">
                <Input.TextArea placeholder="填写开店后的真实情况、风险、经验教训" />
              </Form.Item>
              <Button type="primary" htmlType="submit" loading={feedbackBusy}>保存回填</Button>
            </Form>
            {feedbackMessage && <Alert type={feedbackMessage.includes('失败') ? 'error' : 'success'} showIcon message={feedbackMessage} />}
          </Card>

          <Card title="最终报告">
            <Descriptions column={2} items={[
              {key: 'score', label: '综合评分', children: score.total ?? '-'},
              {key: 'level', label: '适合度等级', children: score.level ?? '-'},
              {key: 'confidence', label: '报告置信度', children: report.confidence != null ? `${Math.round(report.confidence * 100)}%` : '-'},
              {key: 'sources', label: '数据来源', children: (report.data_sources || []).join('；') || '-'},
            ]} />
            <h3>结论摘要</h3>
            <p>{report.summary}</p>
            <h3>核心优势</h3>
            <List size="small" dataSource={report.advantages || []} renderItem={(item: string) => <List.Item>{item}</List.Item>} />
            <h3>决策正向因素</h3>
            <List size="small" dataSource={report.decision_factors || []} renderItem={(item: string) => <List.Item><Tag color="green">正向</Tag>{item}</List.Item>} />
            <h3>主要风险</h3>
            <List size="small" dataSource={report.risks || []} renderItem={(item: string) => <List.Item><Tag color="orange">风险</Tag>{item}</List.Item>} />
            <h3>决策负向因素</h3>
            <List size="small" dataSource={report.negative_factors || []} renderItem={(item: string) => <List.Item><Tag color="red">负向</Tag>{item}</List.Item>} />
            <h3>不确定性来源</h3>
            <List size="small" dataSource={report.uncertainty_analysis || []} renderItem={(item: string) => <List.Item><Tag color="purple">不确定</Tag>{item}</List.Item>} />
            <h3>本次预测 vs 历史类似案例</h3>
            <p>{report?.similar_case_analysis?.comparison_summary || '暂无历史反馈样本可对比。'}</p>
            <h3>数据缺口</h3>
            <List size="small" dataSource={result.data_gaps || report.data_gaps || []} renderItem={(item: string) => <List.Item><Tag>缺失</Tag>{item}</List.Item>} />
            <h3>真实数据来源</h3>
            <Space wrap>
              {(dataQuality.real_data_sources || []).map((source: string) => <Tag color="green" key={source}>{source}</Tag>)}
              {!(dataQuality.real_data_sources || []).length && <Tag>暂无真实数据源</Tag>}
            </Space>
            <h3>mock / 估算警告</h3>
            <List
              size="small"
              dataSource={[...(dataQuality.mock_warnings || []), ...(dataQuality.estimated_warnings || [])]}
              renderItem={(item: string) => <List.Item><Tag color="orange">警告</Tag>{item}</List.Item>}
            />
            <h3>缺失字段</h3>
            <List size="small" dataSource={report.missing_fields || []} renderItem={(item: string) => <List.Item><Tag>字段</Tag>{item}</List.Item>} />
            <h3>人工核实项</h3>
            <List size="small" dataSource={result.manual_check_items || report.manual_check_items || []} renderItem={(item: string) => <List.Item><Tag color="blue">核实</Tag>{item}</List.Item>} />
            <h3>建议</h3>
            <List size="small" dataSource={report.recommendations || []} renderItem={(item: string) => <List.Item>{item}</List.Item>} />
          </Card>
        </>
      )}
    </div>
  );
}
