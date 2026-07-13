import {useEffect, useMemo, useState} from 'react';
import {Alert, Button, Card, Col, Input, List, Row, Space, Tag, Typography, message as antdMessage} from 'antd';
import {useParams} from 'react-router-dom';
import {createProjectChatSession, listProjectChatMessages, sendProjectChatMessage} from '../../api/chat';

type ChatMessage = {
  id?: number;
  role: 'user' | 'assistant';
  content: string;
  references?: string[];
  simulation?: Record<string, any> | null;
};

export default function ProjectChat() {
  const {projectId = ''} = useParams();
  const [sessionId, setSessionId] = useState<string>('');
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [conversationSummary, setConversationSummary] = useState<string | null>(null);
  const [question, setQuestion] = useState('');
  const [loading, setLoading] = useState(false);

  const canSend = useMemo(() => Boolean(sessionId && question.trim()), [sessionId, question]);

  useEffect(() => {
    if (!projectId) return;
    createProjectChatSession(projectId)
      .then(data => setSessionId(String(data.session_id)))
      .catch(error => antdMessage.error(error?.response?.data?.detail || error.message || '创建聊天失败'));
  }, [projectId]);

  const reloadMessages = async (id = sessionId) => {
    if (!id) return;
    const data = await listProjectChatMessages(id);
    setMessages(data.messages || []);
    setConversationSummary(data.conversation_summary || null);
  };

  const send = async () => {
    if (!canSend) return;
    const text = question.trim();
    setQuestion('');
    setMessages(prev => [...prev, {role: 'user', content: text}]);
    setLoading(true);
    try {
      const result = await sendProjectChatMessage(sessionId, text);
      setMessages(prev => [...prev, {role: 'assistant', content: result.answer, references: result.references || [], simulation: result.simulation}]);
      await reloadMessages(sessionId);
    } catch (error: any) {
      antdMessage.error(error?.response?.data?.detail || error.message || '发送失败');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="page">
      <Row gutter={16}>
        <Col span={7}>
          <Card title="项目上下文">
            <p>项目 ID：{projectId || '未指定'}</p>
            <p>聊天 Session：{sessionId || '创建中...'}</p>
            <Alert type="info" showIcon message="AI 会读取项目数据、评分结果、最新报告和最近 20 轮聊天。" />
            {conversationSummary && (
              <Alert style={{marginTop: 12}} type="warning" showIcon message="已有历史摘要" description={conversationSummary} />
            )}
          </Card>
        </Col>
        <Col span={17}>
          <Card title="AI 聊天助手">
            <List
              bordered
              style={{minHeight: 420, maxHeight: 560, overflow: 'auto', marginBottom: 16}}
              dataSource={messages}
              locale={{emptyText: '可以询问：为什么评分低？如果租金降低30%会怎样？'}}
              renderItem={item => (
                <List.Item>
                  <div style={{width: '100%'}}>
                    <Space style={{marginBottom: 6}}>
                      <Tag color={item.role === 'user' ? 'blue' : 'green'}>{item.role === 'user' ? '用户' : 'AI'}</Tag>
                      {(item.references || []).map(ref => <Tag key={ref}>{ref}</Tag>)}
                    </Space>
                    <Typography.Paragraph style={{whiteSpace: 'pre-wrap', marginBottom: 0}}>{item.content}</Typography.Paragraph>
                    {item.simulation && (
                      <Alert
                        style={{marginTop: 8}}
                        type="warning"
                        showIcon
                        message="临时模拟分析"
                        description={<pre style={{whiteSpace: 'pre-wrap', margin: 0}}>{JSON.stringify(item.simulation, null, 2)}</pre>}
                      />
                    )}
                  </div>
                </List.Item>
              )}
            />
            <Space.Compact style={{width: '100%'}}>
              <Input.TextArea
                autoSize={{minRows: 2, maxRows: 5}}
                value={question}
                onChange={event => setQuestion(event.target.value)}
                placeholder="输入你的问题，例如：为什么这个地址不推荐？"
                onPressEnter={event => {
                  if (!event.shiftKey) {
                    event.preventDefault();
                    send();
                  }
                }}
              />
              <Button type="primary" loading={loading} disabled={!canSend} onClick={send}>发送</Button>
            </Space.Compact>
          </Card>
        </Col>
      </Row>
    </div>
  );
}
