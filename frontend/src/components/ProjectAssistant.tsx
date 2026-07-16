import {useEffect, useMemo, useState} from 'react';
import {Alert, Button, Card, Input, List, Space, Typography} from 'antd';
import {RobotOutlined, SendOutlined, UserOutlined} from '@ant-design/icons';
import {createProjectChatSession, sendProjectChatMessage} from '../api/chat';

type AssistantMessage = {
  role: 'user' | 'assistant';
  content: string;
};

const SUGGESTED_QUESTIONS = [
  '为什么这个项目评分不高？',
  '周边竞品压力大吗？',
  '这个位置适合开电竞馆吗？',
];

export default function ProjectAssistant({projectId}: {projectId: string}) {
  const [sessionId, setSessionId] = useState('');
  const [messages, setMessages] = useState<AssistantMessage[]>([]);
  const [question, setQuestion] = useState('');
  const [initializing, setInitializing] = useState(false);
  const [sending, setSending] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    if (!projectId) return;
    let active = true;
    setSessionId('');
    setMessages([]);
    setQuestion('');
    setInitializing(true);
    setError('');
    createProjectChatSession(projectId)
      .then(result => {
        if (active) setSessionId(String(result.session_id));
      })
      .catch(() => {
        if (active) setError('AI助手暂时不可用，请稍后重试。');
      })
      .finally(() => {
        if (active) setInitializing(false);
      });
    return () => {
      active = false;
    };
  }, [projectId]);

  const canSend = useMemo(
    () => Boolean(sessionId && question.trim() && !sending),
    [question, sending, sessionId],
  );

  const send = async () => {
    if (!canSend) return;
    const content = question.trim();
    setQuestion('');
    setError('');
    setMessages(previous => [...previous, {role: 'user', content}]);
    setSending(true);
    try {
      const result = await sendProjectChatMessage(sessionId, content);
      const answer = String(result?.answer || '').trim();
      if (!answer || answer.includes('API Key未配置')) {
        throw new Error('assistant_unavailable');
      }
      setMessages(previous => [...previous, {role: 'assistant', content: answer}]);
    } catch {
      setError('AI助手暂时不可用，请稍后重试。');
    } finally {
      setSending(false);
    }
  };

  return (
    <Card
      className="project-assistant"
      title={<Space><RobotOutlined />AI助手</Space>}
      extra={<Typography.Text type="secondary">围绕当前选址项目咨询</Typography.Text>}
    >
      <Typography.Paragraph type="secondary">
        助手会结合当前项目地址、已采集数据、评分结果和最新报告回答问题。
      </Typography.Paragraph>

      {error && <Alert type="error" showIcon message="AI助手暂时不可用" description="请稍后重试。" style={{marginBottom: 12}} />}

      <List
        className="assistant-message-list"
        dataSource={messages}
        locale={{emptyText: '可以询问当前项目的评分、竞品、交通、人口或投资风险。'}}
        renderItem={item => (
          <List.Item className={`assistant-message ${item.role}`}>
            <Space align="start">
              {item.role === 'user' ? <UserOutlined /> : <RobotOutlined />}
              <div>
                <Typography.Text strong>{item.role === 'user' ? '你' : 'AI助手'}</Typography.Text>
                <Typography.Paragraph style={{whiteSpace: 'pre-wrap', margin: '4px 0 0'}}>
                  {item.content}
                </Typography.Paragraph>
              </div>
            </Space>
          </List.Item>
        )}
      />

      {sending && <Typography.Paragraph type="secondary">AI正在分析当前项目...</Typography.Paragraph>}

      <Space wrap style={{marginBottom: 10}}>
        {SUGGESTED_QUESTIONS.map(item => (
          <Button key={item} size="small" onClick={() => setQuestion(item)}>{item}</Button>
        ))}
      </Space>

      <Space.Compact style={{width: '100%'}}>
        <Input.TextArea
          value={question}
          disabled={initializing || !sessionId}
          autoSize={{minRows: 2, maxRows: 5}}
          placeholder={initializing ? 'AI助手正在准备...' : '输入关于当前选址项目的问题'}
          onChange={event => setQuestion(event.target.value)}
          onPressEnter={event => {
            if (!event.shiftKey) {
              event.preventDefault();
              void send();
            }
          }}
        />
        <Button type="primary" icon={<SendOutlined />} loading={sending} disabled={!canSend} onClick={() => void send()}>
          发送
        </Button>
      </Space.Compact>
    </Card>
  );
}
