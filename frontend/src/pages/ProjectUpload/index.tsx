import {useEffect, useMemo, useState} from 'react';
import {Alert, Button, Card, Col, Descriptions, List, Row, Select, Space, Statistic, Table, Tag, Typography, Upload, message} from 'antd';
import {ArrowLeftOutlined, DownloadOutlined, FileExcelOutlined, InboxOutlined, UploadOutlined} from '@ant-design/icons';
import {useNavigate, useParams, useSearchParams} from 'react-router-dom';
import {getProject, uploadProjectCsv, uploadProjectRentCsv} from '../../api/projects';
import {loadImportRecords, saveImportRecord, type ImportRecord} from '../../utils/importRecords';

type UploadDataType = 'competitor' | 'food' | 'entertainment' | 'rent';

const DATA_TYPES: Array<{value: UploadDataType; label: string}> = [
  {value: 'competitor', label: '竞品数据'},
  {value: 'food', label: '餐饮数据'},
  {value: 'entertainment', label: '娱乐数据'},
  {value: 'rent', label: '租金数据'},
];

const TEMPLATE_FIELDS: Record<UploadDataType, string[]> = {
  competitor: ['名称', '地址', '距离', '面积', '机器数量', 'CPU', '显卡', '显示器', '价格', '会员价格', '营业时间', '开业时间', '上座率', '月营业额', '年营业额', '充值信息', '备注'],
  food: ['名称', '地址', '距离', '品类', '营业时间', '开业时间', '是否夜间营业', '评分', '备注'],
  entertainment: ['名称', '地址', '距离', '类型', '营业时间', '开业时间', '是否夜间营业', '备注'],
  rent: ['地址', '面积', '月租金', '物业费', '转让费', '单平租金', '来源', '备注'],
};

const REQUIRED_FIELDS: Record<UploadDataType, string[]> = {
  competitor: ['名称', '距离'],
  food: ['名称', '距离'],
  entertainment: ['名称', '距离'],
  rent: ['地址', '面积', '月租金'],
};

type PrecheckResult = {
  status: 'idle' | 'checking' | 'passed' | 'failed' | 'unsupported' | 'error';
  recognized: string[];
  missing: string[];
};

type CsvRow = Record<string, string>;

type ValidationIssue = {
  row: number;
  message: string;
};

const EMPTY_PRECHECK: PrecheckResult = {status: 'idle', recognized: [], missing: []};

function formatFileSize(size?: number) {
  if (!size) return '0 KB';
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`;
  return `${(size / 1024 / 1024).toFixed(2)} MB`;
}

function parseCsv(text: string) {
  const rows: string[][] = [];
  let row: string[] = [];
  let current = '';
  let quoted = false;
  const source = text.replace(/^\uFEFF/, '');

  for (let index = 0; index < source.length; index += 1) {
    const character = source[index];
    if (character === '"') {
      if (quoted && source[index + 1] === '"') {
        current += '"';
        index += 1;
      } else {
        quoted = !quoted;
      }
    } else if (character === ',' && !quoted) {
      row.push(current);
      current = '';
    } else if ((character === '\n' || character === '\r') && !quoted) {
      if (character === '\r' && source[index + 1] === '\n') index += 1;
      row.push(current);
      rows.push(row);
      row = [];
      current = '';
    } else {
      current += character;
    }
  }

  if (quoted) throw new Error('CSV 引号未闭合');
  if (current || row.length > 0) {
    row.push(current);
    rows.push(row);
  }
  return rows.filter(item => item.some(value => value.trim()));
}

function validateRows(dataType: UploadDataType, rows: CsvRow[]): ValidationIssue[] {
  const issues: ValidationIssue[] = [];

  rows.forEach((row, index) => {
    const lineNumber = index + 2;
    const requireText = (field: string) => {
      if (!String(row[field] || '').trim()) issues.push({row: lineNumber, message: `${field}为空`});
    };
    const requireNumber = (field: string, required = false) => {
      const value = String(row[field] || '').trim();
      if (!value) {
        if (required) issues.push({row: lineNumber, message: `${field}为空`});
        return;
      }
      if (!Number.isFinite(Number(value))) issues.push({row: lineNumber, message: `${field}不是数字`});
    };

    if (dataType === 'competitor') {
      requireText('名称');
      requireNumber('距离', true);
      ['面积', '机器数量', '价格'].forEach(field => requireNumber(field));
      const occupancy = String(row['上座率'] || '').trim();
      if (occupancy && !/^\d+(?:\.\d+)?%?$/.test(occupancy)) {
        issues.push({row: lineNumber, message: '上座率格式应为数字或百分比，例如 80 或 80%'});
      }
    } else if (dataType === 'food') {
      requireText('名称');
      requireNumber('距离', true);
      requireText('营业时间');
    } else if (dataType === 'entertainment') {
      requireText('名称');
      requireNumber('距离', true);
    } else if (dataType === 'rent') {
      requireText('地址');
      requireNumber('面积', true);
      requireNumber('月租金', true);
      requireNumber('物业费');
    }
  });

  return issues;
}

export default function ProjectUploadPage() {
  const {projectId = ''} = useParams();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const queryType = searchParams.get('type') as UploadDataType | null;
  const initialType = DATA_TYPES.some(item => item.value === queryType) ? queryType! : 'competitor';
  const [dataType, setDataType] = useState<UploadDataType>(initialType);
  const [fileList, setFileList] = useState<any[]>([]);
  const [precheck, setPrecheck] = useState<PrecheckResult>(EMPTY_PRECHECK);
  const [csvHeaders, setCsvHeaders] = useState<string[]>([]);
  const [csvRows, setCsvRows] = useState<CsvRow[]>([]);
  const [validationIssues, setValidationIssues] = useState<ValidationIssue[]>([]);
  const [uploading, setUploading] = useState(false);
  const [uploadResult, setUploadResult] = useState<any>(null);
  const [uploadError, setUploadError] = useState('');
  const [projectStats, setProjectStats] = useState<Record<string, any>>({});
  const [importRecords, setImportRecords] = useState<ImportRecord[]>([]);

  const selectedFile = fileList[0];
  const selectedLabel = useMemo(
    () => DATA_TYPES.find(item => item.value === dataType)?.label || '数据',
    [dataType],
  );

  useEffect(() => {
    if (!projectId) return;
    setImportRecords(loadImportRecords(projectId));
    getProject(projectId)
      .then(result => setProjectStats(result.stats || {}))
      .catch(() => undefined);
  }, [projectId]);

  const changeType = (value: UploadDataType) => {
    setDataType(value);
    setFileList([]);
    setPrecheck(EMPTY_PRECHECK);
    setCsvHeaders([]);
    setCsvRows([]);
    setValidationIssues([]);
    setUploadResult(null);
    setUploadError('');
    setSearchParams({type: value});
  };

  const downloadTemplate = () => {
    const csv = `\uFEFF${TEMPLATE_FIELDS[dataType].join(',')}\r\n`;
    const url = URL.createObjectURL(new Blob([csv], {type: 'text/csv;charset=utf-8'}));
    const link = document.createElement('a');
    link.href = url;
    link.download = `${dataType}_template.csv`;
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
    message.success(`${selectedLabel}模板已生成`);
  };

  const precheckFile = async (file: File) => {
    setUploadResult(null);
    setUploadError('');
    const lowerName = file.name.toLowerCase();
    if (!lowerName.endsWith('.csv')) {
      setPrecheck({status: 'unsupported', recognized: [], missing: []});
      setCsvHeaders([]);
      setCsvRows([]);
      setValidationIssues([]);
      return;
    }

    setPrecheck({status: 'checking', recognized: [], missing: []});
    try {
      const text = await file.text();
      const parsed = parseCsv(text);
      const headers = (parsed[0] || []).map(field => field.trim());
      const recognized = [...new Set(headers.filter(Boolean))];
      const missing = REQUIRED_FIELDS[dataType].filter(field => !recognized.includes(field));
      const rows = parsed.slice(1).map(values => {
        const row: CsvRow = {};
        headers.forEach((header, index) => {
          if (header) row[header] = String(values[index] || '').trim();
        });
        return row;
      });
      setCsvHeaders(recognized);
      setCsvRows(rows);
      setValidationIssues(validateRows(dataType, rows));
      setPrecheck({status: missing.length === 0 && recognized.length > 0 ? 'passed' : 'failed', recognized, missing});
    } catch {
      setPrecheck({status: 'error', recognized: [], missing: []});
      setCsvHeaders([]);
      setCsvRows([]);
      setValidationIssues([]);
    }
  };

  const precheckStatusTag = () => {
    if (precheck.status === 'passed') return <Tag color="green">预检通过</Tag>;
    if (precheck.status === 'failed') return <Tag color="red">预检未通过</Tag>;
    if (precheck.status === 'checking') return <Tag color="blue">正在预检</Tag>;
    if (precheck.status === 'unsupported') return <Tag color="orange">等待 Excel 解析</Tag>;
    if (precheck.status === 'error') return <Tag color="red">读取失败</Tag>;
    return <Tag color="orange">待预检</Tag>;
  };

  const canUpload = Boolean(
    selectedFile
    && precheck.status === 'passed'
    && csvRows.length > 0
    && validationIssues.length === 0,
  );

  const confirmUpload = async () => {
    if (!canUpload) return;
    const file = selectedFile?.originFileObj as File | undefined;
    if (!file) {
      setUploadError('无法读取所选文件，请重新选择。');
      return;
    }
    setUploading(true);
    setUploadResult(null);
    setUploadError('');
    try {
      const result = dataType === 'rent'
        ? await uploadProjectRentCsv(projectId, file)
        : await uploadProjectCsv(projectId, dataType, file);
      setUploadResult(result);
      setImportRecords(saveImportRecord(projectId, {
        dataType,
        dataTypeLabel: selectedLabel,
        importedRows: Number(result.imported_rows) || 0,
        failedRows: Number(result.failed_rows) || 0,
        duplicateRows: Number(result.duplicate_rows) || 0,
      }));
      try {
        const projectDetail = await getProject(projectId);
        setProjectStats(projectDetail.stats || {});
      } catch {
        message.warning('数据已导入，但项目统计刷新失败，返回工作台后可重新查看。');
      }
      if (result.failed_rows > 0) {
        message.warning(`上传完成：成功 ${result.imported_rows} 条，失败 ${result.failed_rows} 条`);
      } else {
        message.success(`上传完成：成功导入 ${result.imported_rows} 条`);
      }
    } catch (error: any) {
      const reason = error?.response?.data?.detail || error?.message || '上传失败';
      setUploadError(typeof reason === 'string' ? reason : reason?.message || '上传失败，请稍后重试');
      message.error('上传失败');
    } finally {
      setUploading(false);
    }
  };

  return (
    <div className="page project-upload-page">
      <div className="page-title-row">
        <div>
          <Typography.Title level={2}>人工数据上传</Typography.Title>
          <Typography.Paragraph type="secondary">
            为当前选址项目下载数据模板，并在浏览器中检查 CSV 表头。
          </Typography.Paragraph>
        </div>
        <Button icon={<ArrowLeftOutlined />} onClick={() => navigate(`/projects/${projectId}`)}>
          返回项目工作台
        </Button>
      </div>

      <Alert
        type="info"
        showIcon
        style={{marginBottom: 16}}
        message="CSV 数据上传"
        description="文件通过检查后可确认上传。服务器只读取CSV内容，不会永久保存原始文件。"
      />

      <Space direction="vertical" size={16} style={{width: '100%'}}>
        <Card title="第一步：选择数据类型">
          <Select<UploadDataType>
            value={dataType}
            options={DATA_TYPES}
            style={{width: 260}}
            onChange={changeType}
          />
        </Card>

        <Card
          title="第二步：下载模板并查看字段"
          extra={<Button type="primary" icon={<DownloadOutlined />} onClick={downloadTemplate}>下载模板</Button>}
        >
          <Typography.Paragraph>
            <Typography.Text strong>{selectedLabel}</Typography.Text>建议包含以下字段：
          </Typography.Paragraph>
          <Space wrap>
            {TEMPLATE_FIELDS[dataType].map(field => <Tag key={field} color="blue">{field}</Tag>)}
          </Space>
          <Typography.Paragraph type="secondary" style={{margin: '12px 0 0'}}>
            模板格式：UTF-8 CSV，可使用 Excel 打开和编辑。
          </Typography.Paragraph>
        </Card>

        <Card title="第三步：选择文件">
          <Upload.Dragger
            accept=".csv,.xlsx,.xls"
            maxCount={1}
            fileList={fileList}
            beforeUpload={file => {
              const lowerName = file.name.toLowerCase();
              if (!lowerName.endsWith('.csv') && !lowerName.endsWith('.xlsx') && !lowerName.endsWith('.xls')) {
                message.error('请选择 .csv、.xlsx 或 .xls 格式的文件');
                return Upload.LIST_IGNORE;
              }
              void precheckFile(file);
              return false;
            }}
            onChange={({fileList: nextFiles}) => setFileList(nextFiles.slice(-1))}
            onRemove={() => {
              setFileList([]);
              setPrecheck(EMPTY_PRECHECK);
              setCsvHeaders([]);
              setCsvRows([]);
              setValidationIssues([]);
              setUploadResult(null);
              setUploadError('');
              return true;
            }}
          >
            <p className="ant-upload-drag-icon"><InboxOutlined /></p>
            <p className="ant-upload-text">点击或拖拽 CSV / Excel 文件到此区域</p>
            <p className="ant-upload-hint">CSV 将在浏览器中预检表头，文件不会上传到服务器。</p>
          </Upload.Dragger>

          {selectedFile && (
            <Descriptions bordered size="small" column={1} style={{marginTop: 16}}>
              <Descriptions.Item label="文件名称"><FileExcelOutlined /> {selectedFile.name}</Descriptions.Item>
              <Descriptions.Item label="文件大小">{formatFileSize(selectedFile.size || selectedFile.originFileObj?.size)}</Descriptions.Item>
              <Descriptions.Item label="数据类型">{selectedLabel}</Descriptions.Item>
              <Descriptions.Item label="上传状态">{uploadResult ? <Tag color="green">已上传</Tag> : <Tag color="orange">待上传</Tag>}</Descriptions.Item>
              <Descriptions.Item label="预检状态">{precheckStatusTag()}</Descriptions.Item>
              <Descriptions.Item label="数据条数">{csvRows.length} 条</Descriptions.Item>
            </Descriptions>
          )}

          {selectedFile && precheck.status === 'unsupported' && (
            <Alert
              style={{marginTop: 16}}
              type="warning"
              showIcon
              message="当前阶段仅支持 CSV 表头预检"
              description="Excel（.xlsx、.xls）解析将在下一阶段接入。你可以先下载 CSV 模板进行预检。"
            />
          )}

          {selectedFile && precheck.status === 'error' && (
            <Alert style={{marginTop: 16}} type="error" showIcon message="文件读取失败" description="请确认文件未损坏后重新选择。" />
          )}

          {selectedFile && ['passed', 'failed'].includes(precheck.status) && (
            <Card size="small" title="表头预检结果" style={{marginTop: 16}}>
              <Typography.Paragraph>
                <Typography.Text strong>已识别字段：</Typography.Text>
                <Space wrap style={{marginLeft: 8}}>
                  {precheck.recognized.map(field => <Tag key={field} color="blue">{field}</Tag>)}
                </Space>
              </Typography.Paragraph>
              <Typography.Paragraph>
                <Typography.Text strong>缺失必填字段：</Typography.Text>
                <Space wrap style={{marginLeft: 8}}>
                  {precheck.missing.length > 0
                    ? precheck.missing.map(field => <Tag key={field} color="red">{field}</Tag>)
                    : <Tag color="green">无</Tag>}
                </Space>
              </Typography.Paragraph>
              <Alert
                type={precheck.status === 'passed' ? 'success' : 'error'}
                showIcon
                message={precheck.status === 'passed'
                  ? '表头检查通过，可以进入下一步上传解析。'
                  : '请根据模板补充字段后重新上传。'}
              />
            </Card>
          )}

          {selectedFile && ['passed', 'failed'].includes(precheck.status) && (
            <Card size="small" title="数据预览与格式检查" style={{marginTop: 16}}>
              {csvRows.length === 0 ? (
                <Alert type="warning" showIcon message="暂无数据" description="CSV 文件只有表头，没有可预览的数据行。" />
              ) : (
                <>
                  <Typography.Paragraph>
                    共识别 <Typography.Text strong>{csvRows.length}</Typography.Text> 条数据，下面显示前 5 条。
                  </Typography.Paragraph>
                  <Table
                    size="small"
                    bordered
                    pagination={false}
                    scroll={{x: 'max-content'}}
                    columns={csvHeaders.map(header => ({title: header, dataIndex: header, key: header}))}
                    dataSource={csvRows.slice(0, 5).map((row, index) => ({...row, key: index}))}
                  />

                  <div style={{marginTop: 16}}>
                    {validationIssues.length === 0 ? (
                      <Alert
                        type="success"
                        showIcon
                        message={`检查通过：共 ${csvRows.length} 条数据`}
                        description="未发现格式问题。"
                      />
                    ) : (
                      <Alert
                        type="error"
                        showIcon
                        message={`检查失败：发现 ${validationIssues.length} 条异常`}
                        description={(
                          <ul style={{margin: '8px 0 0', paddingLeft: 20}}>
                            {validationIssues.slice(0, 20).map((issue, index) => (
                              <li key={`${issue.row}-${index}`}>第 {issue.row} 行：{issue.message}</li>
                            ))}
                            {validationIssues.length > 20 && <li>其余 {validationIssues.length - 20} 条异常未展开显示</li>}
                          </ul>
                        )}
                      />
                    )}
                  </div>
                </>
              )}
            </Card>
          )}

          {selectedFile && (
            <Card size="small" title="确认上传" style={{marginTop: 16}}>
              <Space direction="vertical" size={12} style={{width: '100%'}}>
                {!canUpload && (
                  <Alert
                    type="warning"
                    showIcon
                    message="暂时不能上传"
                    description="请先确保 CSV 表头检查通过、包含数据行，并修复全部格式异常。"
                  />
                )}
                <Button
                  type="primary"
                  icon={<UploadOutlined />}
                  disabled={!canUpload}
                  loading={uploading}
                  onClick={confirmUpload}
                >
                  {uploading ? '正在上传...' : '确认上传'}
                </Button>

                {uploadError && <Alert type="error" showIcon message="上传失败" description={uploadError} />}

                {uploadResult && (
                  <Alert
                    type={uploadResult.failed_rows > 0 ? 'warning' : 'success'}
                    showIcon
                    message="上传完成"
                    description={(
                      <div>
                        <p style={{margin: '0 0 8px'}}>
                          共 {uploadResult.total_rows} 条，成功导入 {uploadResult.imported_rows} 条，失败 {uploadResult.failed_rows} 条，重复跳过 {uploadResult.duplicate_rows || 0} 条。
                        </p>
                        {Array.isArray(uploadResult.errors) && uploadResult.errors.length > 0 && (
                          <ul style={{margin: 0, paddingLeft: 20}}>
                            {uploadResult.errors.map((item: any, index: number) => (
                              <li key={`${item.row}-${index}`}>第 {item.row} 行：{item.reason}</li>
                            ))}
                          </ul>
                        )}
                        {Array.isArray(uploadResult.duplicates) && uploadResult.duplicates.length > 0 && (
                          <ul style={{margin: '8px 0 0', paddingLeft: 20}}>
                            {uploadResult.duplicates.map((item: any, index: number) => (
                              <li key={`duplicate-${item.row}-${index}`}>第 {item.row} 行：{item.reason}</li>
                            ))}
                          </ul>
                        )}
                      </div>
                    )}
                  />
                )}
              </Space>
            </Card>
          )}
        </Card>

        <Card title="当前项目数据统计">
          <Row gutter={[12, 12]}>
            <Col xs={12} md={6}><Statistic title="竞品数据" value={projectStats.competitor_count || 0} suffix="条" /></Col>
            <Col xs={12} md={6}><Statistic title="餐饮数据" value={projectStats.food_count || 0} suffix="条" /></Col>
            <Col xs={12} md={6}><Statistic title="娱乐数据" value={projectStats.entertainment_count || 0} suffix="条" /></Col>
            <Col xs={12} md={6}><Statistic title="租金数据" value={projectStats.rent_count || 0} suffix="条" /></Col>
          </Row>
        </Card>

        <Card title="最近导入记录">
          <List
            size="small"
            dataSource={importRecords.slice(0, 10)}
            locale={{emptyText: '暂无人工上传记录'}}
            renderItem={record => (
              <List.Item extra={new Date(record.createdAt).toLocaleString()}>
                <Space wrap>
                  <Typography.Text strong>{record.dataTypeLabel}</Typography.Text>
                  <Tag color="blue">来源：{record.source}</Tag>
                  <Tag color="green">成功 {record.importedRows} 条</Tag>
                  <Tag color={record.failedRows > 0 ? 'red' : 'default'}>失败 {record.failedRows} 条</Tag>
                  <Tag color={record.duplicateRows > 0 ? 'orange' : 'default'}>重复 {record.duplicateRows} 条</Tag>
                </Space>
              </List.Item>
            )}
          />
        </Card>
      </Space>
    </div>
  );
}
