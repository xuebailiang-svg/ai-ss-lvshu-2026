import {Card, Descriptions, Tag} from 'antd';

export default function ProjectOverview({project, quality}: {project: any; quality?: any}) {
  return (
    <Card title="项目基本信息">
      <Descriptions column={3} size="small">
        <Descriptions.Item label="项目名称">{project?.name || '-'}</Descriptions.Item>
        <Descriptions.Item label="城市">{project?.city || '-'}</Descriptions.Item>
        <Descriptions.Item label="区域">{project?.district || '-'}</Descriptions.Item>
        <Descriptions.Item label="地址">{project?.address || '-'}</Descriptions.Item>
        <Descriptions.Item label="半径">{project?.radius_meters ? `${project.radius_meters} 米` : '-'}</Descriptions.Item>
        <Descriptions.Item label="业务类型">{project?.business_type || '-'}</Descriptions.Item>
        <Descriptions.Item label="数据质量">
          {quality ? <Tag color={quality.quality_score >= 80 ? 'green' : quality.quality_score >= 60 ? 'orange' : 'red'}>{quality.quality_score}</Tag> : '-'}
        </Descriptions.Item>
      </Descriptions>
    </Card>
  );
}
