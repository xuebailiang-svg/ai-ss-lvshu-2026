import {useEffect, useState} from 'react';
import {Alert, Card, Col, Row, Typography, message} from 'antd';
import {useParams} from 'react-router-dom';
import {getProject, getProjectDataQuality, getProjectDataset} from '../../api/projects';
import ActionPanel from './ActionPanel';
import DataPanel from './DataPanel';
import ProjectOverview from './ProjectOverview';
import ReportPanel from './ReportPanel';
import ScorePanel from './ScorePanel';

export default function ProjectDetailPage() {
  const {projectId = ''} = useParams();
  const [project, setProject] = useState<any>(null);
  const [dataset, setDataset] = useState<any>(null);
  const [quality, setQuality] = useState<any>(null);
  const [score, setScore] = useState<any>(null);
  const [report, setReport] = useState<any>(null);
  const [collectResult, setCollectResult] = useState<any>(null);

  const load = async () => {
    if (!projectId) return;
    try {
      const [detail, data, qualityData] = await Promise.all([
        getProject(projectId),
        getProjectDataset(projectId),
        getProjectDataQuality(projectId),
      ]);
      setProject(detail.project);
      setDataset(data);
      setQuality(qualityData);
    } catch (error: any) {
      message.error(error?.response?.data?.detail || error.message || '加载项目失败');
    }
  };

  useEffect(() => {
    load();
  }, [projectId]);

  return (
    <div className="page">
      <Typography.Title level={2}>项目详情工作台</Typography.Title>
      <Row gutter={[16, 16]}>
        <Col span={24}><ProjectOverview project={project} quality={quality} /></Col>
        <Col span={24}>
          <ActionPanel
            projectId={projectId}
            onCollected={result => {
              setCollectResult(result);
              load();
            }}
            onScored={setScore}
            onReported={setReport}
          />
        </Col>
        {collectResult && (
          <Col span={24}>
            <Alert
              type={collectResult.success ? 'success' : 'warning'}
              showIcon
              message="采集结果"
              description={JSON.stringify(collectResult.collected || collectResult, null, 2)}
            />
          </Col>
        )}
        <Col span={14}><DataPanel projectId={projectId} dataset={dataset || {}} quality={quality || {}} onRefresh={load} /></Col>
        <Col span={10}><ScorePanel score={score} /></Col>
        <Col span={24}><ReportPanel report={report} /></Col>
        <Col span={24}>
          <Card title="原始数据预览">
            <pre className="json-preview">{JSON.stringify(dataset || {}, null, 2)}</pre>
          </Card>
        </Col>
      </Row>
    </div>
  );
}
