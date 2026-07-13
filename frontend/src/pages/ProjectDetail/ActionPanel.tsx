import {Button, Card, Space, message} from 'antd';
import {useNavigate} from 'react-router-dom';
import {collectProjectAmap} from '../../api/projects';
import {scoreProject} from '../../api/score';
import {generateAiReport} from '../../api/report';

export default function ActionPanel({
  projectId,
  onCollected,
  onScored,
  onReported,
}: {
  projectId: string;
  onCollected: (result: any) => void;
  onScored: (result: any) => void;
  onReported: (result: any) => void;
}) {
  const navigate = useNavigate();

  const run = async (label: string, fn: () => Promise<any>, done: (result: any) => void) => {
    try {
      const result = await fn();
      done(result);
      message.success(`${label}完成`);
    } catch (error: any) {
      message.error(error?.response?.data?.detail || error.message || `${label}失败`);
    }
  };

  return (
    <Card title="操作流程">
      <Space wrap>
        <Button onClick={() => run('高德采集', () => collectProjectAmap(projectId), onCollected)}>开始高德采集</Button>
        <Button type="primary" onClick={() => run('评分', () => scoreProject(projectId), onScored)}>开始评分</Button>
        <Button onClick={() => run('AI报告', () => generateAiReport(projectId), onReported)}>生成AI报告</Button>
        <Button onClick={() => navigate(`/projects/${projectId}/chat`)}>继续AI咨询</Button>
      </Space>
    </Card>
  );
}
