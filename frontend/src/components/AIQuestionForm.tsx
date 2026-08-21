import {useState} from 'react';
import {Alert, Button, Card, Input, InputNumber, Radio, Select, Space, Tag, Typography, message} from 'antd';
import {
  AIQuestion,
  AIQuestionsResult,
  generateProjectAiQuestions,
  saveProjectAiQuestionAnswers,
} from '../api/projects';

type AnswerMode = 'answer' | 'unknown' | 'skip';
type DraftAnswer = {mode: AnswerMode; value?: string | number | boolean | null};

function answerInput(question: AIQuestion, draft: DraftAnswer, onChange: (value: string | number | boolean | null) => void) {
  if (question.answer_type === 'boolean' || question.answer_type === 'select') {
    const options = question.options.length > 0
      ? question.options
      : [{label: '是', value: 'true'}, {label: '否', value: 'false'}];
    return (
      <Select
        style={{width: 240}}
        placeholder="请选择"
        value={draft.value === undefined || draft.value === null ? undefined : String(draft.value)}
        options={options}
        onChange={value => onChange(question.answer_type === 'boolean' ? value === 'true' : value)}
      />
    );
  }
  if (['number', 'money', 'integer', 'percentage'].includes(question.answer_type)) {
    return (
      <InputNumber
        style={{width: 240}}
        min={0}
        max={question.answer_type === 'percentage' ? 100 : undefined}
        precision={question.answer_type === 'integer' ? 0 : 2}
        addonAfter={question.unit || undefined}
        placeholder="请输入实际核实值"
        value={typeof draft.value === 'number' ? draft.value : undefined}
        onChange={value => onChange(value)}
      />
    );
  }
  return (
    <Input
      style={{maxWidth: 520}}
      placeholder="请输入实际核实信息"
      value={typeof draft.value === 'string' ? draft.value : ''}
      onChange={event => onChange(event.target.value)}
    />
  );
}

export default function AIQuestionForm({projectId, onSaved}: {projectId: string; onSaved?: () => void | Promise<void>}) {
  const [result, setResult] = useState<AIQuestionsResult | null>(null);
  const [drafts, setDrafts] = useState<Record<string, DraftAnswer>>({});
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [canContinue, setCanContinue] = useState(false);

  const loadQuestions = async (continueRound = false) => {
    setLoading(true);
    try {
      const next = await generateProjectAiQuestions(projectId, continueRound);
      setResult(next);
      setDrafts(Object.fromEntries(next.questions.map(item => [item.question_id, {mode: 'answer'}])));
      setCanContinue(false);
      if (next.status === 'skipped') message.warning(next.message);
      else if (next.questions.length === 0) message.info(next.message);
    } catch (error: any) {
      message.error(error?.response?.data?.detail || error?.message || '生成重要问题失败');
    } finally {
      setLoading(false);
    }
  };

  const updateDraft = (questionId: string, patch: Partial<DraftAnswer>) => {
    setDrafts(current => ({...current, [questionId]: {...(current[questionId] || {mode: 'answer'}), ...patch}}));
  };

  const submit = async () => {
    const questions = result?.questions || [];
    const missing = questions.find(question => {
      const draft = drafts[question.question_id] || {mode: 'answer'};
      return draft.mode === 'answer' && (draft.value === undefined || draft.value === null || draft.value === '');
    });
    if (missing) {
      message.warning(`请回答“${missing.title}”，或选择“不知道/暂不提供”`);
      return;
    }
    setSaving(true);
    try {
      const saved = await saveProjectAiQuestionAnswers(projectId, questions.map(question => {
        const draft = drafts[question.question_id] || {mode: 'answer'};
        return {
          question_id: question.question_id,
          value: draft.mode === 'answer' ? draft.value : undefined,
          unknown: draft.mode === 'unknown',
          skip: draft.mode === 'skip',
        };
      }));
      message.success('重要信息已保存到当前项目');
      setResult(current => current ? {...current, status: 'round_complete', questions: [], message: saved.message} : current);
      setCanContinue(Boolean(saved.can_continue));
      await onSaved?.();
    } catch (error: any) {
      message.error(error?.response?.data?.detail || error?.message || '保存回答失败');
    } finally {
      setSaving(false);
    }
  };

  return (
    <Space direction="vertical" size={12} style={{width: '100%', marginTop: 12}}>
      {!result && (
        <Alert
          type="info"
          showIcon
          message="AI 只从系统允许的缺失字段中挑选最重要的问题"
          description="最多两轮、每轮最多 3 个、总计不超过 5 个。AI 不会自行填写经营数据，只有您的回答会保存。"
        />
      )}
      {result?.questions.map((question, index) => {
        const draft = drafts[question.question_id] || {mode: 'answer'};
        return (
          <Card key={question.question_id} size="small" title={<Space wrap><Tag color="blue">问题 {index + 1}</Tag>{question.title}</Space>}>
            {question.help_text && <Typography.Paragraph type="secondary">{question.help_text}</Typography.Paragraph>}
            <Space direction="vertical" size={10} style={{width: '100%'}}>
              <Radio.Group
                value={draft.mode}
                onChange={event => updateDraft(question.question_id, {mode: event.target.value})}
                options={[
                  {label: '填写实际值', value: 'answer'},
                  {label: '不知道', value: 'unknown'},
                  {label: '暂不提供', value: 'skip'},
                ]}
              />
              {draft.mode === 'answer' && answerInput(question, draft, value => updateDraft(question.question_id, {value}))}
            </Space>
          </Card>
        );
      })}
      {result && result.questions.length === 0 && (
        <Alert
          type={result.status === 'skipped' ? 'warning' : 'success'}
          showIcon
          message={result.message}
          description="没有回答的字段不会被 AI 自动补写，也不会阻塞报告生成。"
        />
      )}
      <Space wrap>
        {result?.questions.length ? (
          <Button type="primary" loading={saving} onClick={submit}>保存本轮回答</Button>
        ) : (
          <Button loading={loading} onClick={() => loadQuestions(false)}>生成重要问题</Button>
        )}
        {canContinue && (
          <Button loading={loading} onClick={() => loadQuestions(true)}>继续第二轮（可选）</Button>
        )}
        {result && <Typography.Text type="secondary">已提问 {result.asked_count} / 5</Typography.Text>}
      </Space>
    </Space>
  );
}
