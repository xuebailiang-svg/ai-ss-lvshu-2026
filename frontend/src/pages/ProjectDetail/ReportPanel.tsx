import {Button, Card, Space, Typography} from 'antd';

export default function ReportPanel({report}: {report: any}) {
  return (
    <Card
      title="AI报告"
      extra={<Space>{report?.content && <Button onClick={() => window.print()}>打印</Button>}</Space>}
    >
      {report?.success === false ? (
        <Typography.Text type="warning">{report.message}</Typography.Text>
      ) : report?.content ? (
        <Typography.Paragraph style={{whiteSpace: 'pre-wrap'}}>{report.content}</Typography.Paragraph>
      ) : (
        <Typography.Text>尚未生成 AI 报告。</Typography.Text>
      )}
    </Card>
  );
}
