import {useEffect, useState} from 'react';
import {Alert, Button, Card, Checkbox, Col, Divider, Form, Input, InputNumber, List, message, Modal, Progress, Row, Segmented, Space, Spin, Switch, Tag, Typography} from 'antd';
import {
  CheckCircleOutlined,
  CloseCircleOutlined,
  LoadingOutlined,
  MinusCircleOutlined,
  LinkOutlined,
  UploadOutlined,
} from '@ant-design/icons';
import {useNavigate} from 'react-router-dom';
import {loadImportRecords, type ImportRecord} from '../utils/importRecords';
import {
  checkDataSourceConnectivity,
  getDataSourceStatus,
  type ConnectivityCheck,
  type DataSourceAvailability,
  type DataSourceStatus,
} from '../api/dataSources';
import {
  listProjectCompetitors,
  getProjectCompetitor,
  reviewProjectCompetitor,
  updateProjectCompetitor,
  listProjectSupporting,
  reviewProjectSupporting,
  getProjectSupportingDetail,
  updateProjectSupportingDetail,
  listProjectRent,
  reviewProjectRent,
  getProjectRentDetail,
  updateProjectRentDetail,
  type ProjectCompetitor,
  type ProjectCompetitorStatus,
  type ProjectSupportingCategory,
  type ProjectSupportingItem,
  type ProjectSupportingDetail,
  type ProjectSupportingStatus,
  type ProjectRentItem,
  type ProjectRentDetail,
  type ProjectRentStatus,
  type CrawlerSuggestion,
} from '../api/projects';

const CRAWLER_FIELD_LABELS: Record<string, string> = {
  business_hours: '营业时间', hour_price: '小时价格', member_price: '会员价', machine_count: '机器数量',
  area_sqm: '面积', occupancy_rate: '上座率', rating: '评分', night_operation: '夜间营业', is_24_hours: '24小时',
  monthly_rent: '月租金', rent_per_sqm: '租金单价', property_fee: '物业费', transfer_fee: '转让费',
  floor: '楼层', publish_date: '发布时间', address: '地址',
};

function CrawlerEvidence({suggestion}: {suggestion?: CrawlerSuggestion | null}) {
  if (!suggestion) return null;
  return (
    <div style={{marginTop: 8, padding: '8px 10px', border: '1px solid #ffe58f', borderRadius: 8, background: '#fffbe6'}}>
      <Space direction="vertical" size={4} style={{width: '100%'}}>
        <Space size={[4, 4]} wrap>
          <Tag color="gold">爬虫待确认线索</Tag>
          {Object.entries(suggestion.fields || {}).map(([field, value]) => (
            <Tag key={field}>{CRAWLER_FIELD_LABELS[field] || field}：{String(value)}</Tag>
          ))}
        </Space>
        {(suggestion.field_evidence || []).slice(0, 3).map((item, index) => (
          <Typography.Text key={`${item.field}-${index}`} type="secondary">
            {CRAWLER_FIELD_LABELS[item.field] || item.field}：{item.excerpt || '请打开来源网页核对'}
            {item.confidence != null ? `（置信度 ${Math.round(item.confidence * 100)}%）` : ''}
          </Typography.Text>
        ))}
        {suggestion.source_url && (
          <Typography.Link href={suggestion.source_url} target="_blank" rel="noreferrer">
            <LinkOutlined /> 打开来源网页（{suggestion.source_domain || '公开网页'}）
          </Typography.Link>
        )}
        <Typography.Text type={suggestion.review_status === 'confirmed' ? 'success' : 'warning'}>
          {suggestion.review_status === 'confirmed' ? '该记录已完成人工确认。' : '确认前不会作为最终经营事实。'}
        </Typography.Text>
      </Space>
    </div>
  );
}

type CollectionStatus = 'not_started' | 'collecting' | 'completed' | 'failed';

type CollectionItem = {
  name: string;
  description: string;
  status: CollectionStatus;
  count?: number;
  uploadType?: 'competitor' | 'food' | 'entertainment' | 'rent';
  actionType?: 'supporting';
  missingFields?: string[];
};

const STATUS_VIEW: Record<CollectionStatus, {text: string; color: string; icon: React.ReactNode}> = {
  not_started: {text: '未开始', color: 'default', icon: <MinusCircleOutlined />},
  collecting: {text: '采集中', color: 'processing', icon: <LoadingOutlined />},
  completed: {text: '完成', color: 'success', icon: <CheckCircleOutlined />},
  failed: {text: '失败', color: 'error', icon: <CloseCircleOutlined />},
};

const PROVIDER_STATUS_VIEW: Record<DataSourceAvailability, {text: string; color: string}> = {
  available: {text: '可用', color: 'success'},
  disabled: {text: '已禁用', color: 'default'},
  not_configured: {text: '待配置', color: 'warning'},
};

const CONNECTIVITY_STATUS_VIEW: Record<string, {text: string; color: string}> = {
  ok: {text: '正常', color: 'success'},
  failed: {text: '失败', color: 'error'},
  not_configured: {text: '未配置', color: 'warning'},
  disabled: {text: '已禁用', color: 'default'},
  unsupported: {text: '不支持检测', color: 'default'},
};

type ConnectivityState = {
  loading?: boolean;
  result?: ConnectivityCheck;
  error?: boolean;
};

type CompetitorFilter = 'all' | ProjectCompetitorStatus;

const COMPETITOR_STATUS_VIEW: Record<ProjectCompetitorStatus, {text: string; color: string}> = {
  pending_review: {text: '待确认', color: 'warning'},
  confirmed: {text: '已确认', color: 'success'},
  rejected: {text: '已排除', color: 'default'},
};

const SUPPORTING_STATUS_VIEW: Record<ProjectSupportingStatus, {text: string; color: string}> = {
  pending_review: {text: '待核实', color: 'warning'},
  confirmed: {text: '已确认', color: 'success'},
  rejected: {text: '已排除', color: 'default'},
};

const SUPPORTING_CATEGORY_VIEW: Record<ProjectSupportingCategory, string> = {
  food: '餐饮',
  entertainment: '娱乐',
  night_business: '夜间商业候选',
};

const RENT_STATUS_VIEW: Record<ProjectRentStatus, {text: string; color: string}> = {
  pending_review: {text: '待确认', color: 'warning'},
  confirmed: {text: '已确认', color: 'success'},
  rejected: {text: '已排除', color: 'default'},
};

const COMPETITOR_DETAIL_FIELDS: Array<keyof ProjectCompetitor> = [
  'area_sqm',
  'machine_count',
  'cpu',
  'gpu',
  'monitor',
  'hour_price',
  'member_price',
  'business_hours',
  'opening_date',
  'occupancy_rate',
  'monthly_sales',
  'annual_sales',
  'recharge_info',
  'remark',
];

function competitorDetailCount(competitor: ProjectCompetitor) {
  return COMPETITOR_DETAIL_FIELDS.filter(field => {
    const value = competitor[field];
    return value !== null && value !== undefined && String(value).trim() !== '';
  }).length;
}

function numericCount(...values: unknown[]) {
  return Math.max(0, ...values.map(value => Number(value) || 0));
}

export default function DataCollectionCenter({
  projectId,
  stats,
  collecting,
  collectResult,
  collectError,
  collectingCompetitors,
  competitorCollectResult,
  competitorCollectError,
  onCollectCompetitors,
  collectingSupporting,
  supportingCollectResult,
  supportingCollectError,
  onCollectSupporting,
  onCompetitorReviewed,
  onCompetitorDetailSaved,
}: {
  projectId: string;
  stats: Record<string, any>;
  collecting: boolean;
  collectResult: any;
  collectError: string;
  collectingCompetitors: boolean;
  competitorCollectResult: any;
  competitorCollectError: string;
  onCollectCompetitors: () => void;
  collectingSupporting: boolean;
  supportingCollectResult: any;
  supportingCollectError: string;
  onCollectSupporting: () => void;
  onCompetitorReviewed?: () => void | Promise<void>;
  onCompetitorDetailSaved?: () => Promise<{previousScore: number | null; currentScore: number}>;
}) {
  const navigate = useNavigate();
  const [recentImports, setRecentImports] = useState<ImportRecord[]>([]);
  const [dataSources, setDataSources] = useState<DataSourceStatus[]>([]);
  const [dataSourcesLoading, setDataSourcesLoading] = useState(true);
  const [dataSourcesError, setDataSourcesError] = useState(false);
  const [connectivity, setConnectivity] = useState<Record<string, ConnectivityState>>({});
  const [competitors, setCompetitors] = useState<ProjectCompetitor[]>([]);
  const [competitorsLoading, setCompetitorsLoading] = useState(false);
  const [competitorsError, setCompetitorsError] = useState(false);
  const [reviewingCompetitor, setReviewingCompetitor] = useState<number | null>(null);
  const [competitorFilter, setCompetitorFilter] = useState<CompetitorFilter>('all');
  const [selectedCompetitorIds, setSelectedCompetitorIds] = useState<number[]>([]);
  const [batchReviewing, setBatchReviewing] = useState(false);
  const [detailForm] = Form.useForm();
  const [detailModalOpen, setDetailModalOpen] = useState(false);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailSaving, setDetailSaving] = useState(false);
  const [detailCompetitor, setDetailCompetitor] = useState<ProjectCompetitor | null>(null);
  const [supportingItems, setSupportingItems] = useState<ProjectSupportingItem[]>([]);
  const [supportingItemsLoading, setSupportingItemsLoading] = useState(false);
  const [supportingItemsError, setSupportingItemsError] = useState(false);
  const [supportingFilter, setSupportingFilter] = useState<'all' | ProjectSupportingCategory>('all');
  const [reviewingSupporting, setReviewingSupporting] = useState<string | null>(null);
  const [supportingDetailForm] = Form.useForm();
  const [supportingDetailOpen, setSupportingDetailOpen] = useState(false);
  const [supportingDetailLoading, setSupportingDetailLoading] = useState(false);
  const [supportingDetailSaving, setSupportingDetailSaving] = useState(false);
  const [supportingDetailItem, setSupportingDetailItem] = useState<ProjectSupportingDetail | null>(null);
  const [rentItems, setRentItems] = useState<ProjectRentItem[]>([]);
  const [rentItemsLoading, setRentItemsLoading] = useState(false);
  const [rentItemsError, setRentItemsError] = useState(false);
  const [reviewingRent, setReviewingRent] = useState<number | null>(null);
  const [rentDetailForm] = Form.useForm();
  const [rentDetailOpen, setRentDetailOpen] = useState(false);
  const [rentDetailLoading, setRentDetailLoading] = useState(false);
  const [rentDetailSaving, setRentDetailSaving] = useState(false);
  const [rentDetailItem, setRentDetailItem] = useState<ProjectRentDetail | null>(null);

  useEffect(() => {
    setRecentImports(loadImportRecords(projectId));
  }, [projectId, stats]);

  useEffect(() => {
    let active = true;
    setDataSourcesLoading(true);
    setDataSourcesError(false);
    getDataSourceStatus()
      .then(response => {
        if (active) setDataSources(Array.isArray(response?.items) ? response.items : []);
      })
      .catch(() => {
        if (active) setDataSourcesError(true);
      })
      .finally(() => {
        if (active) setDataSourcesLoading(false);
      });
    return () => {
      active = false;
    };
  }, []);

  useEffect(() => {
    let active = true;
    setCompetitorsLoading(true);
    setCompetitorsError(false);
    listProjectCompetitors(projectId)
      .then(response => {
        if (active) setCompetitors(Array.isArray(response?.items) ? response.items : []);
      })
      .catch(() => {
        if (active) setCompetitorsError(true);
      })
      .finally(() => {
        if (active) setCompetitorsLoading(false);
      });
    return () => {
      active = false;
    };
  }, [projectId, competitorCollectResult]);

  useEffect(() => {
    let active = true;
    setSupportingItemsLoading(true);
    setSupportingItemsError(false);
    listProjectSupporting(projectId)
      .then(response => {
        if (active) setSupportingItems(Array.isArray(response?.items) ? response.items : []);
      })
      .catch(() => {
        if (active) setSupportingItemsError(true);
      })
      .finally(() => {
        if (active) setSupportingItemsLoading(false);
      });
    return () => {
      active = false;
    };
  }, [projectId, supportingCollectResult]);

  useEffect(() => {
    let active = true;
    setRentItemsLoading(true);
    setRentItemsError(false);
    listProjectRent(projectId)
      .then(response => {
        if (active) setRentItems(Array.isArray(response?.items) ? response.items : []);
      })
      .catch(() => {
        if (active) setRentItemsError(true);
      })
      .finally(() => {
        if (active) setRentItemsLoading(false);
      });
    return () => {
      active = false;
    };
  }, [projectId, stats]);

  const checkConnectivity = (providerName: string) => {
    setConnectivity(previous => ({...previous, [providerName]: {loading: true}}));
    checkDataSourceConnectivity(providerName)
      .then(result => {
        setConnectivity(previous => ({...previous, [providerName]: {result}}));
      })
      .catch(() => {
        setConnectivity(previous => ({...previous, [providerName]: {error: true}}));
      });
  };

  const reloadRentItems = async () => {
    const response = await listProjectRent(projectId);
    setRentItems(Array.isArray(response?.items) ? response.items : []);
  };

  const reviewRent = async (rentId: number, status: ProjectRentStatus) => {
    setReviewingRent(rentId);
    try {
      await reviewProjectRent(projectId, rentId, status);
      await reloadRentItems();
      message.success(status === 'confirmed' ? '租金记录已确认' : status === 'rejected' ? '租金记录已排除' : '已标记为待确认');
    } catch {
      message.error('租金状态更新失败，请稍后重试');
    } finally {
      setReviewingRent(null);
    }
  };

  const openRentDetail = async (rent: ProjectRentItem) => {
    setRentDetailOpen(true);
    setRentDetailLoading(true);
    setRentDetailItem(null);
    rentDetailForm.resetFields();
    try {
      const detail = await getProjectRentDetail(projectId, rent.id);
      setRentDetailItem(detail);
      rentDetailForm.setFieldsValue(detail.manual_detail || {});
    } catch {
      message.error('租金详情加载失败，请稍后重试');
      setRentDetailOpen(false);
    } finally {
      setRentDetailLoading(false);
    }
  };

  const saveRentDetail = async () => {
    if (!rentDetailItem) return;
    setRentDetailSaving(true);
    try {
      const values = await rentDetailForm.validateFields();
      await updateProjectRentDetail(projectId, rentDetailItem.id, values);
      await reloadRentItems();
      message.success('租金详情已保存');
      setRentDetailOpen(false);
    } catch (error: any) {
      if (!error?.errorFields) message.error('租金详情保存失败，请稍后重试');
    } finally {
      setRentDetailSaving(false);
    }
  };

  const reviewCompetitor = async (competitorId: number, status: ProjectCompetitorStatus) => {
    setReviewingCompetitor(competitorId);
    setCompetitorsError(false);
    try {
      const updated = await reviewProjectCompetitor(projectId, competitorId, status);
      setCompetitors(previous => previous.map(item => item.id === competitorId ? updated : item));
      setSelectedCompetitorIds(previous => previous.filter(id => id !== competitorId));
      try {
        await onCompetitorReviewed?.();
      } catch {
        // 状态已经保存成功，统计刷新失败不应误报为复核失败。
      }
    } catch {
      setCompetitorsError(true);
    } finally {
      setReviewingCompetitor(null);
    }
  };

  const reviewSupporting = async (supportingId: string, status: ProjectSupportingStatus) => {
    setReviewingSupporting(supportingId);
    setSupportingItemsError(false);
    try {
      const updated = await reviewProjectSupporting(projectId, supportingId, status);
      setSupportingItems(previous => previous.map(item => item.id === supportingId ? updated : item));
      message.success(status === 'confirmed' ? '配套信息已确认' : status === 'rejected' ? '配套信息已排除' : '已标记为待核实');
    } catch {
      message.error('配套状态更新失败，请稍后重试');
    } finally {
      setReviewingSupporting(null);
    }
  };

  const openSupportingDetail = async (item: ProjectSupportingItem) => {
    setSupportingDetailOpen(true);
    setSupportingDetailLoading(true);
    setSupportingDetailItem(null);
    supportingDetailForm.resetFields();
    try {
      const detail = await getProjectSupportingDetail(projectId, item.id);
      setSupportingDetailItem(detail);
      supportingDetailForm.setFieldsValue(detail.manual_detail || {});
    } catch {
      message.error('配套详情加载失败，请稍后重试');
      setSupportingDetailOpen(false);
    } finally {
      setSupportingDetailLoading(false);
    }
  };

  const saveSupportingDetail = async () => {
    if (!supportingDetailItem) return;
    try {
      const values = await supportingDetailForm.validateFields();
      setSupportingDetailSaving(true);
      const updated = await updateProjectSupportingDetail(projectId, supportingDetailItem.id, values);
      setSupportingItems(previous => previous.map(item => item.id === updated.id ? {...item, ...updated} : item));
      setSupportingDetailItem(updated);
      setSupportingDetailOpen(false);
      message.success('周边配套详情已保存');
    } catch (error: any) {
      if (error?.errorFields) return;
      const detail = error?.response?.data?.detail;
      message.error(typeof detail === 'string' ? detail : '保存失败，请稍后重试');
    } finally {
      setSupportingDetailSaving(false);
    }
  };

  const batchReviewCompetitors = async (status: ProjectCompetitorStatus) => {
    if (selectedCompetitorIds.length === 0) return;
    const ids = [...selectedCompetitorIds];
    setBatchReviewing(true);
    setCompetitorsError(false);
    const results = await Promise.allSettled(
      ids.map(competitorId => reviewProjectCompetitor(projectId, competitorId, status)),
    );
    const successCount = results.filter(result => result.status === 'fulfilled').length;
    const failedCount = results.length - successCount;

    try {
      const response = await listProjectCompetitors(projectId);
      setCompetitors(Array.isArray(response?.items) ? response.items : []);
    } catch {
      setCompetitorsError(true);
    }
    setSelectedCompetitorIds([]);
    try {
      await onCompetitorReviewed?.();
    } catch {
      // 批量状态已写入，统计刷新失败不影响本次操作结果。
    }
    if (failedCount === 0) {
      message.success(`已更新 ${successCount} 条竞品状态`);
    } else if (successCount > 0) {
      message.warning(`已更新 ${successCount} 条，部分竞品更新失败，请重试`);
    } else {
      message.error('竞品状态更新失败，请重试');
    }
    setBatchReviewing(false);
  };

  const openCompetitorDetail = async (competitor: ProjectCompetitor) => {
    setDetailModalOpen(true);
    setDetailLoading(true);
    setDetailCompetitor(competitor);
    detailForm.resetFields();
    try {
      const detail = await getProjectCompetitor(projectId, competitor.id);
      setDetailCompetitor(detail);
      detailForm.setFieldsValue({
        ...detail,
        occupancy_rate: detail.occupancy_rate == null ? undefined : `${detail.occupancy_rate * 100}%`,
      });
    } catch {
      message.error('竞品详情加载失败，请稍后重试');
      setDetailModalOpen(false);
    } finally {
      setDetailLoading(false);
    }
  };

  const saveCompetitorDetail = async () => {
    if (!detailCompetitor) return;
    try {
      const values = await detailForm.validateFields();
      const occupancyText = String(values.occupancy_rate ?? '').trim();
      const occupancyNumber = occupancyText === ''
        ? null
        : Number(occupancyText.replace('%', '')) / (
          occupancyText.includes('%') || Number(occupancyText) > 1 ? 100 : 1
        );
      setDetailSaving(true);
      await updateProjectCompetitor(projectId, detailCompetitor.id, {
        ...values,
        occupancy_rate: occupancyNumber,
      });
      try {
        const response = await listProjectCompetitors(projectId);
        setCompetitors(Array.isArray(response?.items) ? response.items : []);
      } catch {
        // 详情已经保存，列表刷新失败不应改变保存结果。
      }
      setDetailModalOpen(false);
      message.loading('竞品详情已保存，正在更新数据完整度...', 1.2);
      if (onCompetitorDetailSaved) {
        try {
          const quality = await onCompetitorDetailSaved();
          if (quality.previousScore !== null && quality.currentScore > quality.previousScore) {
            message.success('竞品信息补充后，数据完整度提升');
          } else {
            message.success('数据完整度已更新');
          }
        } catch {
          message.warning('竞品已保存，数据完整度刷新失败，请手动检查');
        }
      } else {
        message.success('竞品详情已保存');
      }
    } catch (error: any) {
      if (error?.errorFields) return;
      message.error('保存失败，请稍后重试');
    } finally {
      setDetailSaving(false);
    }
  };

  const validateOccupancyRate = (_: unknown, value: unknown) => {
    if (value === undefined || value === null || String(value).trim() === '') return Promise.resolve();
    const text = String(value).trim();
    const number = Number(text.replace('%', ''));
    if (!Number.isFinite(number) || number < 0 || number > 100) {
      return Promise.reject(new Error('请输入 0～100、80% 或 0～1 的上座率'));
    }
    return Promise.resolve();
  };

  const collected = collectResult?.collected || {};
  const collectionFinished = Boolean(collectResult && collectResult?.success !== false);
  const collectionFailed = Boolean(collectError || collectResult?.success === false);
  const hasQualityStats = Array.isArray(stats?.missing_fields);
  const missingFields = hasQualityStats ? stats.missing_fields.map(String) : [];

  const statusForAmapData = (count: number): CollectionStatus => {
    if (collecting) return 'collecting';
    if (count > 0 || collectionFinished) return 'completed';
    if (collectionFailed) return 'failed';
    return 'not_started';
  };

  const poiCount = numericCount(stats?.poi_count, collected?.poi_count);
  const competitorCount = numericCount(stats?.competitor_count, collected?.competitor_count);
  const foodCount = numericCount(stats?.food_count, collected?.food_count);
  const entertainmentCount = numericCount(stats?.entertainment_count, collected?.entertainment_count);
  const rentCount = numericCount(stats?.rent_count, rentItems.length);
  const rentMissingFields = Array.from(new Set(rentItems.flatMap(item => item.missing_fields || [])));
  const rentStatus: CollectionStatus = rentCount > 0 || (hasQualityStats && !missingFields.includes('真实租金'))
    ? 'completed'
    : 'not_started';
  const supportingStatus: CollectionStatus = collectingSupporting
    ? 'collecting'
    : supportingCollectError || supportingCollectResult?.success === false
      ? 'failed'
      : supportingCollectResult?.success === true || foodCount + entertainmentCount > 0
        ? 'completed'
        : 'not_started';

  const items: CollectionItem[] = [
    {name: '高德 POI', description: '周边地点与基础分类数据', status: statusForAmapData(poiCount), count: poiCount},
    {name: '竞品数据', description: '电竞馆、网吧等竞品基础数据', status: statusForAmapData(competitorCount), count: competitorCount, uploadType: 'competitor'},
    {name: '餐饮数据', description: '餐饮与夜间消费配套数据', status: statusForAmapData(foodCount), count: foodCount, uploadType: 'food'},
    {name: '娱乐数据', description: 'KTV、酒吧、影院等娱乐数据', status: statusForAmapData(entertainmentCount), count: entertainmentCount, uploadType: 'entertainment'},
    {name: '周边配套数据', description: '高德餐饮、娱乐与夜间商业候选数据', status: supportingStatus, count: foodCount + entertainmentCount, actionType: 'supporting'},
    {
      name: '租金数据',
      description: '候选物业的真实租金与成本数据',
      status: rentStatus,
      count: rentCount,
      uploadType: 'rent',
      missingFields: rentMissingFields,
    },
  ];

  const completedCount = items.filter(item => item.status === 'completed').length;
  const progress = Math.round((completedCount / items.length) * 100);
  const competitorStatusCounts = {
    all: competitors.length,
    pending_review: competitors.filter(item => item.status === 'pending_review').length,
    confirmed: competitors.filter(item => item.status === 'confirmed').length,
    rejected: competitors.filter(item => item.status === 'rejected').length,
  };
  const filteredCompetitors = competitorFilter === 'all'
    ? competitors
    : competitors.filter(item => item.status === competitorFilter);
  const filteredCompetitorIds = filteredCompetitors.map(item => item.id);
  const selectedInFilterCount = filteredCompetitorIds.filter(id => selectedCompetitorIds.includes(id)).length;
  const allFilteredSelected = filteredCompetitorIds.length > 0 && selectedInFilterCount === filteredCompetitorIds.length;
  const someFilteredSelected = selectedInFilterCount > 0 && !allFilteredSelected;
  const supportingCounts = {
    all: supportingItems.length,
    food: supportingItems.filter(item => item.category === 'food').length,
    entertainment: supportingItems.filter(item => item.category === 'entertainment').length,
    night_business: supportingItems.filter(item => item.category === 'night_business').length,
  };
  const filteredSupportingItems = supportingFilter === 'all'
    ? supportingItems
    : supportingItems.filter(item => item.category === supportingFilter);
  const confirmedSupportingCount = supportingItems.filter(item => item.status === 'confirmed').length;
  const completedSupportingCount = supportingItems.filter(item => item.status === 'confirmed' && item.detail_completed).length;
  const confirmedRentCount = rentItems.filter(item => item.status === 'confirmed').length;
  const completedRentDetailCount = rentItems.filter(item => item.status === 'confirmed' && item.detail_completed).length;

  const toggleFilteredSelection = (checked: boolean) => {
    if (checked) {
      setSelectedCompetitorIds(previous => Array.from(new Set([...previous, ...filteredCompetitorIds])));
    } else {
      setSelectedCompetitorIds(previous => previous.filter(id => !filteredCompetitorIds.includes(id)));
    }
  };

  return (
    <Card className="data-collection-center" title="数据采集中心" style={{marginBottom: 16}}>
      <div className="collection-summary">
        <div>
          <Typography.Text strong>数据采集进度</Typography.Text>
          <Typography.Paragraph type="secondary" style={{marginBottom: 0}}>
            当前统计来自项目已有数据和本次高德采集状态。
          </Typography.Paragraph>
        </div>
        <div className="collection-progress">
          <Progress percent={progress} size="small" />
          <Typography.Text type="secondary">已完成 {completedCount}/{items.length} 类</Typography.Text>
        </div>
      </div>

      <Row gutter={[12, 12]}>
        {items.map(item => {
          const view = STATUS_VIEW[item.status];
          return (
            <Col xs={24} md={12} lg={8} key={item.name}>
              <Card size="small" className={`collection-source-card ${item.status}`}>
                <div className="collection-source-title">
                  <Typography.Text strong>{item.name}</Typography.Text>
                  <Tag color={view.color} icon={view.icon}>{view.text}</Tag>
                </div>
                <Typography.Paragraph type="secondary" style={{margin: '8px 0 4px'}}>
                  {item.description}
                </Typography.Paragraph>
                {item.count !== undefined && (
                  <Typography.Text>当前数据：{item.count} 条</Typography.Text>
                )}
                {item.uploadType === 'rent' && (
                  <div style={{marginTop: 6}}>
                    {rentItemsLoading ? (
                      <Typography.Text type="secondary">正在读取租金数据...</Typography.Text>
                    ) : rentItemsError ? (
                      <Typography.Text type="warning">租金明细暂时不可用</Typography.Text>
                    ) : item.missingFields && item.missingFields.length > 0 ? (
                      <Typography.Text type="warning">
                        缺少字段：{item.missingFields.join('、')}
                      </Typography.Text>
                    ) : rentCount > 0 ? (
                      <Typography.Text type="success">地址、面积和月租金信息完整</Typography.Text>
                    ) : (
                      <Typography.Text type="secondary">尚未导入真实租金数据</Typography.Text>
                    )}
                  </div>
                )}
                {item.uploadType && (
                  <Space wrap style={{marginTop: 10}}>
                    {item.uploadType === 'competitor' && (
                      <Button
                        size="small"
                        type="primary"
                        loading={collectingCompetitors}
                        onClick={onCollectCompetitors}
                      >
                        获取竞品
                      </Button>
                    )}
                    <Button
                      size="small"
                      icon={<UploadOutlined />}
                      onClick={() => navigate(`/projects/${projectId}/upload?type=${item.uploadType}`)}
                    >
                      上传{item.name}
                    </Button>
                  </Space>
                )}
                {item.actionType === 'supporting' && (
                  <Space direction="vertical" size={6} style={{marginTop: 10}}>
                    <Button
                      size="small"
                      type="primary"
                      loading={collectingSupporting}
                      onClick={onCollectSupporting}
                    >
                      {collectingSupporting ? '正在获取周边配套...' : '获取周边配套'}
                    </Button>
                    {supportingCollectResult?.success === true && (
                      <Typography.Text type="secondary">
                        餐饮 {Number(supportingCollectResult.food_count) || 0} 条 · 娱乐 {Number(supportingCollectResult.entertainment_count) || 0} 条 · 夜间商业 {Number(supportingCollectResult.night_business_count) || 0} 条
                      </Typography.Text>
                    )}
                    {supportingCollectError && (
                      <Typography.Text type="danger">{supportingCollectError}</Typography.Text>
                    )}
                  </Space>
                )}
                {item.uploadType === 'competitor' && competitorCollectResult?.success !== false && competitorCollectResult && (
                  <Typography.Paragraph type="secondary" style={{margin: '8px 0 0'}}>
                    发现 {Number(competitorCollectResult.discovered_count) || 0} 个电竞馆相关 POI
                  </Typography.Paragraph>
                )}
                {item.uploadType === 'competitor' && competitorCollectError && (
                  <Typography.Paragraph type="danger" style={{margin: '8px 0 0'}}>
                    {competitorCollectError}
                  </Typography.Paragraph>
                )}
              </Card>
            </Col>
          );
        })}
      </Row>

      <Divider />
      <Typography.Title id="rent-data-section" level={5}>租金数据列表</Typography.Title>
      <Typography.Paragraph type="secondary">
        新导入租金默认等待确认。只有人工确认后的记录才能在后续阶段作为有效租金参考，本阶段不计算最低价或市场均价。
      </Typography.Paragraph>
      <Space wrap style={{marginBottom: 12}}>
        <Tag>全部 {rentItems.length} 条</Tag>
        <Tag color="success">已确认 {confirmedRentCount} 条</Tag>
        <Tag color="blue">详情完整 {completedRentDetailCount} 条</Tag>
      </Space>
      {rentItemsError ? (
        <Alert type="warning" showIcon message="租金数据列表加载失败，请稍后重试" />
      ) : rentItemsLoading ? (
        <Spin size="small" tip="正在读取租金数据..." />
      ) : (
        <List
          size="small"
          bordered
          dataSource={rentItems}
          locale={{emptyText: '尚未导入租金数据'}}
          renderItem={rent => {
            const statusView = RENT_STATUS_VIEW[rent.status] || {text: rent.status, color: 'default'};
            return (
              <List.Item
                id={`rent-item-${rent.id}`}
                actions={[
                  <Button
                    key="confirm"
                    size="small"
                    type={rent.status === 'confirmed' ? 'primary' : 'default'}
                    loading={reviewingRent === rent.id}
                    disabled={reviewingRent !== null || rent.status === 'confirmed'}
                    onClick={() => reviewRent(rent.id, 'confirmed')}
                  >
                    确认
                  </Button>,
                  <Button
                    key="reject"
                    size="small"
                    danger
                    disabled={reviewingRent !== null || rent.status === 'rejected'}
                    onClick={() => reviewRent(rent.id, 'rejected')}
                  >
                    排除
                  </Button>,
                  <Button key="detail" size="small" onClick={() => openRentDetail(rent)}>
                    补充详情
                  </Button>,
                ]}
              >
                <List.Item.Meta
                  title={(
                    <Space wrap>
                      <Typography.Text strong>{rent.address || '地址待补充'}</Typography.Text>
                      <Tag color={statusView.color}>{statusView.text}</Tag>
                      <Tag color={rent.detail_completed ? 'success' : 'default'}>
                        {rent.detail_completed ? '详情完整' : '详情待补充'}
                      </Tag>
                      <Tag>来源：{rent.source === 'manual' ? '人工上传' : rent.source}</Tag>
                    </Space>
                  )}
                  description={(
                    <div>
                      <Space wrap split={<span>·</span>}>
                        <span>面积：{rent.area_sqm == null ? '未填写' : `${rent.area_sqm} ㎡`}</span>
                        <span>月租：{rent.monthly_rent == null ? '未填写' : `${rent.monthly_rent} 元`}</span>
                        <span>单价：{rent.rent_unit_price == null ? '未计算' : `${rent.rent_unit_price} 元/㎡/月`}</span>
                      </Space>
                      <CrawlerEvidence suggestion={rent.crawler_suggestion} />
                    </div>
                  )}
                />
              </List.Item>
            );
          }}
        />
      )}

      <Divider />
      <Typography.Title id="supporting-review-section" level={5}>周边配套结果</Typography.Title>
      <Typography.Paragraph type="secondary">
        高德结果只表示已发现候选商户。便利店、餐厅等是否夜间营业，需要人工确认。
      </Typography.Paragraph>
      {supportingItemsError ? (
        <Alert type="warning" showIcon message="周边配套列表加载或更新失败，请稍后重试" />
      ) : supportingItemsLoading ? (
        <Spin size="small" tip="正在读取周边配套结果..." />
      ) : (
        <Space direction="vertical" size={12} style={{width: '100%'}}>
          <Segmented
            value={supportingFilter}
            options={[
              {label: `全部 ${supportingCounts.all}`, value: 'all'},
              {label: `餐饮 ${supportingCounts.food}`, value: 'food'},
              {label: `娱乐 ${supportingCounts.entertainment}`, value: 'entertainment'},
              {label: `夜间商业候选 ${supportingCounts.night_business}`, value: 'night_business'},
            ]}
            onChange={value => setSupportingFilter(value as 'all' | ProjectSupportingCategory)}
          />
          <Typography.Text type="secondary">
            配套详情完整度：已补充 {completedSupportingCount}/{confirmedSupportingCount} 家已确认配套
          </Typography.Text>
          <List
            bordered
            size="small"
            dataSource={filteredSupportingItems}
            locale={{emptyText: '当前分类暂无周边配套数据'}}
            renderItem={item => {
              const statusView = SUPPORTING_STATUS_VIEW[item.status];
              return (
                <List.Item
                  id={`supporting-item-${item.id.replace(':', '-')}`}
                  actions={[
                    <Button
                      key="detail"
                      size="small"
                      disabled={reviewingSupporting !== null || item.status !== 'confirmed'}
                      onClick={() => openSupportingDetail(item)}
                    >
                      补充详情
                    </Button>,
                    <Button
                      key="confirm"
                      size="small"
                      type={item.status === 'confirmed' ? 'primary' : 'default'}
                      loading={reviewingSupporting === item.id}
                      disabled={reviewingSupporting !== null || item.status === 'confirmed'}
                      onClick={() => reviewSupporting(item.id, 'confirmed')}
                    >
                      确认
                    </Button>,
                    <Button
                      key="reject"
                      size="small"
                      danger
                      disabled={reviewingSupporting !== null || item.status === 'rejected'}
                      onClick={() => reviewSupporting(item.id, 'rejected')}
                    >
                      排除
                    </Button>,
                    <Button
                      key="pending"
                      size="small"
                      disabled={reviewingSupporting !== null || item.status === 'pending_review'}
                      onClick={() => reviewSupporting(item.id, 'pending_review')}
                    >
                      待核实
                    </Button>,
                  ]}
                >
                  <List.Item.Meta
                    title={(
                      <Space wrap>
                        <Typography.Text strong>{item.name}</Typography.Text>
                        <Tag color="blue">{SUPPORTING_CATEGORY_VIEW[item.category]}</Tag>
                        <Tag color={statusView.color}>{statusView.text}</Tag>
                        <Tag>{item.source === 'amap' ? '来源：高德' : '来源：人工'}</Tag>
                        {item.status === 'confirmed' && (
                          <Tag color={item.detail_completed ? 'success' : 'warning'}>
                            {item.detail_completed ? '详情已补充' : '详情待补充'}
                          </Tag>
                        )}
                      </Space>
                    )}
                    description={(
                      <div>
                        <Space wrap split={<span>·</span>}>
                          <span>{item.address || '地址未提供'}</span>
                          <span>{item.distance_meters != null ? `距离 ${item.distance_meters} 米` : '距离未知'}</span>
                        </Space>
                        <CrawlerEvidence suggestion={item.crawler_suggestion} />
                      </div>
                    )}
                  />
                </List.Item>
              );
            }}
          />
        </Space>
      )}

      <Modal
        title={rentDetailItem ? `补充租金详情：${rentDetailItem.address || '未命名物业'}` : '补充租金详情'}
        open={rentDetailOpen}
        width={680}
        confirmLoading={rentDetailSaving}
        okText="保存"
        cancelText="取消"
        onOk={saveRentDetail}
        onCancel={() => setRentDetailOpen(false)}
        destroyOnClose
      >
        <Spin spinning={rentDetailLoading}>
          <Form form={rentDetailForm} layout="vertical">
            <Alert
              type="info"
              showIcon
              message="人工详情与原始租金数据分层保存，不会覆盖上传文件中的原始字段。"
              style={{marginBottom: 16}}
            />
            <Row gutter={16}>
              <Col xs={24} md={12}>
                <Form.Item name="property_type" label="物业类型">
                  <Input placeholder="例如：临街商铺、商场铺位" />
                </Form.Item>
              </Col>
              <Col xs={24} md={12}>
                <Form.Item name="floor" label="楼层">
                  <Input placeholder="例如：一层、二层" />
                </Form.Item>
              </Col>
              <Col span={24}>
                <Form.Item name="location_remark" label="位置说明">
                  <Input.TextArea rows={2} placeholder="补充临街情况、出入口等位置说明" />
                </Form.Item>
              </Col>
              <Col span={24}>
                <Form.Item name="source_url" label="信息来源链接">
                  <Input placeholder="填写房源页面或其他可核验来源链接" />
                </Form.Item>
              </Col>
              <Col xs={24} md={12}>
                <Form.Item name="publish_date" label="发布日期">
                  <Input placeholder="例如：2026-07-15" />
                </Form.Item>
              </Col>
              <Col span={24}>
                <Form.Item name="rent_remark" label="租金备注">
                  <Input.TextArea rows={3} placeholder="填写议价情况、费用口径或现场核实说明" />
                </Form.Item>
              </Col>
            </Row>
          </Form>
        </Spin>
      </Modal>

      <Modal
        title={supportingDetailItem ? `补充配套详情：${supportingDetailItem.name}` : '补充配套详情'}
        open={supportingDetailOpen}
        width={680}
        confirmLoading={supportingDetailSaving}
        okText="保存"
        cancelText="取消"
        onOk={saveSupportingDetail}
        onCancel={() => setSupportingDetailOpen(false)}
        destroyOnClose
      >
        <Spin spinning={supportingDetailLoading}>
          {supportingDetailItem && (
            <Form form={supportingDetailForm} layout="vertical">
              <Alert
                type="info"
                showIcon
                style={{marginBottom: 16}}
                message={`${SUPPORTING_CATEGORY_VIEW[supportingDetailItem.category]}信息由人工填写，系统不会自动推断营业状态。`}
              />
              <Row gutter={16}>
                <Col xs={24} md={12}>
                  <Form.Item name="business_hours" label="营业时间">
                    <Input placeholder="例如：18:00-03:00" />
                  </Form.Item>
                </Col>
                <Col xs={24} md={12}>
                  <Form.Item name="opening_date" label="开业时间">
                    <Input placeholder="例如：2020年" />
                  </Form.Item>
                </Col>
              </Row>

              {supportingDetailItem.category === 'food' && (
                <Form.Item name="food_type" label="餐饮类型">
                  <Input placeholder="例如：烧烤、快餐、火锅" />
                </Form.Item>
              )}
              {supportingDetailItem.category === 'entertainment' && (
                <Form.Item name="entertainment_type" label="娱乐类型">
                  <Input placeholder="例如：KTV、台球、电影院" />
                </Form.Item>
              )}
              {supportingDetailItem.category === 'night_business' && (
                <>
                  <Form.Item name="is_24_hours" label="是否24小时营业" valuePropName="checked">
                    <Switch checkedChildren="是" unCheckedChildren="否" />
                  </Form.Item>
                  <Form.Item name="night_flow_remark" label="夜间客流备注">
                    <Input.TextArea rows={2} placeholder="请填写现场观察，不要估算为真实客流数据" />
                  </Form.Item>
                </>
              )}

              <Form.Item name="night_operation" label="是否夜间营业" valuePropName="checked">
                <Switch checkedChildren="是" unCheckedChildren="否" />
              </Form.Item>
              <Form.Item name="remark" label="备注">
                <Input.TextArea rows={3} placeholder="填写人工核实情况" />
              </Form.Item>
            </Form>
          )}
        </Spin>
      </Modal>

      <Divider />
      <Typography.Title id="competitor-review-section" level={5}>竞品采集结果</Typography.Title>
      <Typography.Paragraph type="secondary">
        高德关键词可能包含普通网络服务点，请确认哪些是真正电竞馆竞品。
      </Typography.Paragraph>
      {competitorsError ? (
        <Alert type="warning" showIcon message="竞品列表加载或更新失败，请稍后重试" />
      ) : competitorsLoading ? (
        <Spin size="small" tip="正在读取竞品列表..." />
      ) : (
        <Space direction="vertical" size={12} style={{width: '100%'}}>
          <Segmented
            value={competitorFilter}
            options={[
              {label: `全部 ${competitorStatusCounts.all}`, value: 'all'},
              {label: `待确认 ${competitorStatusCounts.pending_review}`, value: 'pending_review'},
              {label: `已确认 ${competitorStatusCounts.confirmed}`, value: 'confirmed'},
              {label: `已排除 ${competitorStatusCounts.rejected}`, value: 'rejected'},
            ]}
            onChange={value => {
              setCompetitorFilter(value as CompetitorFilter);
              setSelectedCompetitorIds([]);
            }}
          />
          <Space wrap>
            <Checkbox
              checked={allFilteredSelected}
              indeterminate={someFilteredSelected}
              disabled={filteredCompetitorIds.length === 0 || batchReviewing}
              onChange={event => toggleFilteredSelection(event.target.checked)}
            >
              全选当前筛选结果
            </Checkbox>
            <Button size="small" disabled={selectedCompetitorIds.length === 0 || batchReviewing} onClick={() => setSelectedCompetitorIds([])}>
              取消选择
            </Button>
            <Typography.Text>已选择 {selectedCompetitorIds.length} 条</Typography.Text>
            <Button
              size="small"
              type="primary"
              loading={batchReviewing}
              disabled={selectedCompetitorIds.length === 0}
              onClick={() => batchReviewCompetitors('confirmed')}
            >
              批量确认竞品
            </Button>
            <Button
              size="small"
              danger
              loading={batchReviewing}
              disabled={selectedCompetitorIds.length === 0}
              onClick={() => batchReviewCompetitors('rejected')}
            >
              批量排除
            </Button>
            <Button
              size="small"
              loading={batchReviewing}
              disabled={selectedCompetitorIds.length === 0}
              onClick={() => batchReviewCompetitors('pending_review')}
            >
              批量标记待核实
            </Button>
          </Space>
          <List
            size="small"
            bordered
            dataSource={filteredCompetitors}
            locale={{emptyText: competitors.length === 0 ? '未发现电竞馆相关竞品' : '当前筛选条件下暂无竞品'}}
            renderItem={competitor => {
            const statusView = COMPETITOR_STATUS_VIEW[competitor.status] || {
              text: competitor.status,
              color: 'default',
            };
            const detailCount = competitorDetailCount(competitor);
            return (
              <List.Item
                id={`competitor-item-${competitor.id}`}
                actions={[
                  <Button
                    key="detail"
                    size="small"
                    disabled={competitor.status !== 'confirmed' || batchReviewing}
                    onClick={() => openCompetitorDetail(competitor)}
                  >
                    补充详情
                  </Button>,
                  <Button
                    key="confirm"
                    size="small"
                    type={competitor.status === 'confirmed' ? 'primary' : 'default'}
                    loading={reviewingCompetitor === competitor.id}
                    disabled={reviewingCompetitor !== null || competitor.status === 'confirmed'}
                    onClick={() => reviewCompetitor(competitor.id, 'confirmed')}
                  >
                    确认竞品
                  </Button>,
                  <Button
                    key="reject"
                    size="small"
                    danger
                    disabled={reviewingCompetitor !== null || competitor.status === 'rejected'}
                    onClick={() => reviewCompetitor(competitor.id, 'rejected')}
                  >
                    不是竞品
                  </Button>,
                  <Button
                    key="pending"
                    size="small"
                    disabled={reviewingCompetitor !== null || competitor.status === 'pending_review'}
                    onClick={() => reviewCompetitor(competitor.id, 'pending_review')}
                  >
                    待核实
                  </Button>,
                ]}
              >
                <List.Item.Meta
                  title={(
                    <Space wrap>
                      <Checkbox
                        checked={selectedCompetitorIds.includes(competitor.id)}
                        disabled={batchReviewing || reviewingCompetitor !== null}
                        onChange={event => {
                          setSelectedCompetitorIds(previous => event.target.checked
                            ? Array.from(new Set([...previous, competitor.id]))
                            : previous.filter(id => id !== competitor.id));
                        }}
                      />
                      <Typography.Text strong>{competitor.name}</Typography.Text>
                      <Tag color={statusView.color}>{statusView.text}</Tag>
                      <Tag>{competitor.source === 'amap' ? '来源：高德' : '来源：人工上传'}</Tag>
                      <Tag color={detailCount === 0 ? 'default' : detailCount === COMPETITOR_DETAIL_FIELDS.length ? 'success' : 'blue'}>
                        已补充 {detailCount}/{COMPETITOR_DETAIL_FIELDS.length} 项
                      </Tag>
                    </Space>
                  )}
                  description={(
                    <div>
                      <Space wrap split={<span>·</span>}>
                        <span>{competitor.address || '地址未提供'}</span>
                        <span>{competitor.distance_meters != null ? `距离 ${competitor.distance_meters} 米` : '距离未知'}</span>
                      </Space>
                      <CrawlerEvidence suggestion={competitor.crawler_suggestion} />
                    </div>
                  )}
                />
              </List.Item>
            );
            }}
          />
        </Space>
      )}

      <Modal
        title={detailCompetitor ? `补充竞品详情：${detailCompetitor.name}` : '补充竞品详情'}
        open={detailModalOpen}
        width={780}
        confirmLoading={detailSaving}
        okText="保存"
        cancelText="取消"
        onOk={saveCompetitorDetail}
        onCancel={() => setDetailModalOpen(false)}
        destroyOnClose
      >
        <Spin spinning={detailLoading}>
          <Form form={detailForm} layout="vertical">
            <Typography.Title level={5}>基础经营信息</Typography.Title>
            <Row gutter={16}>
              <Col xs={24} md={12}>
                <Form.Item name="area_sqm" label="面积（㎡）">
                  <InputNumber min={0} style={{width: '100%'}} placeholder="请输入营业面积" />
                </Form.Item>
              </Col>
              <Col xs={24} md={12}>
                <Form.Item name="machine_count" label="机器数量">
                  <InputNumber min={0} precision={0} style={{width: '100%'}} placeholder="请输入机器数量" />
                </Form.Item>
              </Col>
              <Col xs={24} md={12}>
                <Form.Item name="business_hours" label="营业时间">
                  <Input placeholder="例如：24小时" />
                </Form.Item>
              </Col>
              <Col xs={24} md={12}>
                <Form.Item name="opening_date" label="开业时间">
                  <Input placeholder="例如：2024-01" />
                </Form.Item>
              </Col>
            </Row>

            <Typography.Title level={5}>设备配置</Typography.Title>
            <Row gutter={16}>
              <Col xs={24} md={8}><Form.Item name="cpu" label="CPU"><Input /></Form.Item></Col>
              <Col xs={24} md={8}><Form.Item name="gpu" label="显卡"><Input /></Form.Item></Col>
              <Col xs={24} md={8}><Form.Item name="monitor" label="显示器"><Input /></Form.Item></Col>
            </Row>

            <Typography.Title level={5}>价格信息</Typography.Title>
            <Row gutter={16}>
              <Col xs={24} md={12}>
                <Form.Item name="hour_price" label="价格（元/小时）">
                  <InputNumber min={0} style={{width: '100%'}} />
                </Form.Item>
              </Col>
              <Col xs={24} md={12}>
                <Form.Item name="member_price" label="会员价格（元/小时）">
                  <InputNumber min={0} style={{width: '100%'}} />
                </Form.Item>
              </Col>
              <Col span={24}><Form.Item name="recharge_info" label="充值活动"><Input /></Form.Item></Col>
            </Row>

            <Typography.Title level={5}>经营情况</Typography.Title>
            <Row gutter={16}>
              <Col xs={24} md={8}>
                <Form.Item name="occupancy_rate" label="上座率" rules={[{validator: validateOccupancyRate}]}>
                  <Input placeholder="例如：80% 或 0.8" />
                </Form.Item>
              </Col>
              <Col xs={24} md={8}>
                <Form.Item name="monthly_sales" label="月营业额（元）">
                  <InputNumber min={0} style={{width: '100%'}} />
                </Form.Item>
              </Col>
              <Col xs={24} md={8}>
                <Form.Item name="annual_sales" label="年营业额（元）">
                  <InputNumber min={0} style={{width: '100%'}} />
                </Form.Item>
              </Col>
            </Row>

            <Typography.Title level={5}>备注</Typography.Title>
            <Form.Item name="remark">
              <Input.TextArea rows={3} placeholder="填写人工调研备注" />
            </Form.Item>
          </Form>
        </Spin>
      </Modal>

      <Divider />
      <Typography.Title level={5}>数据来源</Typography.Title>
      {dataSourcesError ? (
        <Alert type="warning" showIcon message="数据源状态暂时不可用" />
      ) : dataSourcesLoading ? (
        <Spin size="small" tip="正在读取数据源状态..." />
      ) : (
        <List
          size="small"
          grid={{gutter: 12, xs: 1, sm: 2, lg: 4}}
          dataSource={dataSources}
          locale={{emptyText: '暂无数据源状态'}}
          renderItem={source => {
            const view = PROVIDER_STATUS_VIEW[source.status] || {text: source.status, color: 'default'};
            const check = connectivity[source.name];
            const checkView = check?.result
              ? CONNECTIVITY_STATUS_VIEW[check.result.status] || {text: check.result.status, color: 'default'}
              : null;
            return (
              <List.Item>
                <Card size="small">
                  <Space direction="vertical" size={4}>
                    <Space wrap>
                      <Typography.Text strong>{source.display_name}</Typography.Text>
                      <Tag color={view.color}>{view.text}</Tag>
                    </Space>
                    <Typography.Text type="secondary">{source.description}</Typography.Text>
                    <Button
                      size="small"
                      loading={check?.loading}
                      disabled={!source.check_supported}
                      onClick={() => checkConnectivity(source.name)}
                    >
                      {source.check_supported ? '检测连接' : '暂不支持检测'}
                    </Button>
                    {check?.error && <Typography.Text type="danger">检测失败，请稍后重试。</Typography.Text>}
                    {check?.result && checkView && (
                      <Space direction="vertical" size={2}>
                        <Space wrap>
                          <Tag color={checkView.color}>{checkView.text}</Tag>
                          <Typography.Text type="secondary">延迟：{check.result.latency_ms} ms</Typography.Text>
                        </Space>
                        <Typography.Text type="secondary">{check.result.message}</Typography.Text>
                      </Space>
                    )}
                  </Space>
                </Card>
              </List.Item>
            );
          }}
        />
      )}

      <Divider />
      <Typography.Title level={5}>最近导入记录</Typography.Title>
      {recentImports.length > 0 ? (
        <List
          size="small"
          dataSource={recentImports.slice(0, 5)}
          renderItem={record => (
            <List.Item extra={<Typography.Text type="secondary">{new Date(record.createdAt).toLocaleString()}</Typography.Text>}>
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
      ) : (
        <Typography.Text type="secondary">暂无人工上传记录</Typography.Text>
      )}

      <Typography.Paragraph type="secondary" style={{margin: '12px 0 0'}}>
        爬虫、Excel、人工上传和第三方接口将在后续阶段逐步接入统一采集状态。
      </Typography.Paragraph>
    </Card>
  );
}
