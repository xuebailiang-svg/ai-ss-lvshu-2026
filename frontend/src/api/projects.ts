import {api, LONG_REQUEST_TIMEOUT_MS} from './client';

export type ProjectCreatePayload = {
  name: string;
  city: string;
  district?: string;
  address: string;
  longitude?: number;
  latitude?: number;
  radius_meters: number;
  business_type: string;
  expected_area_sqm?: number;
  investment_budget?: number;
};

export const listProjects = () => api.get('/projects').then(response => response.data);
export const createProject = (data: ProjectCreatePayload) => api.post('/projects', data).then(response => response.data);
export const getProject = (projectId: string) => api.get(`/projects/${projectId}`).then(response => response.data);
export const deleteProject = (projectId: string) => api.delete(`/projects/${projectId}`).then(response => response.data);
export const getProjectDataset = (projectId: string) => api.get(`/projects/${projectId}/dataset`).then(response => response.data);
export const getProjectDataQuality = (projectId: string) => api.get(`/projects/${projectId}/data-quality`).then(response => response.data);
export const getProjectMissingData = (projectId: string) => api.get(`/projects/${projectId}/missing-data`).then(response => response.data);
export const collectProjectAmap = (projectId: string) => api.post(`/projects/${projectId}/collect/amap`, undefined, {timeout: LONG_REQUEST_TIMEOUT_MS}).then(response => response.data);
export const collectProjectCompetitors = (projectId: string) => api.post(`/projects/${projectId}/collect/competitors`, undefined, {timeout: LONG_REQUEST_TIMEOUT_MS}).then(response => response.data);
export const collectProjectSupporting = (projectId: string) => api.post(`/projects/${projectId}/collect/supporting`, undefined, {timeout: LONG_REQUEST_TIMEOUT_MS}).then(response => response.data);
export const generateProjectAiReview = (projectId: string) => api.post(`/projects/${projectId}/ai-review`, undefined, {timeout: LONG_REQUEST_TIMEOUT_MS}).then(response => response.data);

export type CrawlerEnrichType = 'competitor' | 'supporting' | 'rent';

export const enrichProjectCrawler = (
  projectId: string,
  types: CrawlerEnrichType[],
  maxItems = 20,
) => api
  .post(`/projects/${projectId}/crawl/enrich`, {types, max_items: maxItems}, {timeout: LONG_REQUEST_TIMEOUT_MS})
  .then(response => response.data);

export const listProjectCrawlTasks = (projectId: string) => api
  .get(`/projects/${projectId}/crawl/tasks`)
  .then(response => response.data);

export type ProjectSupportingStatus = 'pending_review' | 'confirmed' | 'rejected';
export type ProjectSupportingCategory = 'food' | 'entertainment' | 'night_business';

export type ProjectSupportingItem = {
  id: string;
  name: string;
  category: ProjectSupportingCategory;
  address?: string | null;
  distance_meters?: number | null;
  source: string;
  status: ProjectSupportingStatus;
  detail_completed: boolean;
};

export type ProjectSupportingManualDetail = {
  business_hours?: string | null;
  opening_date?: string | null;
  remark?: string | null;
  food_type?: string | null;
  entertainment_type?: string | null;
  night_operation?: boolean | null;
  is_24_hours?: boolean | null;
  night_flow_remark?: string | null;
};

export type ProjectSupportingDetail = ProjectSupportingItem & {
  manual_detail: ProjectSupportingManualDetail;
};

export type ProjectSupportingList = {
  items: ProjectSupportingItem[];
  total: number;
  effective_count: number;
  stats: Record<ProjectSupportingCategory, {
    total: number;
    confirmed: number;
    pending_review: number;
    rejected: number;
  }>;
};

export const listProjectSupporting = (projectId: string) => api
  .get<ProjectSupportingList>(`/projects/${projectId}/supporting`)
  .then(response => response.data);

export const reviewProjectSupporting = (
  projectId: string,
  supportingId: string,
  status: ProjectSupportingStatus,
) => api
  .post<ProjectSupportingItem>(`/projects/${projectId}/supporting/${encodeURIComponent(supportingId)}/review`, {status})
  .then(response => response.data);

export const getProjectSupportingDetail = (projectId: string, supportingId: string) => api
  .get<ProjectSupportingDetail>(`/projects/${projectId}/supporting/${encodeURIComponent(supportingId)}`)
  .then(response => response.data);

export const updateProjectSupportingDetail = (
  projectId: string,
  supportingId: string,
  data: ProjectSupportingManualDetail,
) => api
  .put<ProjectSupportingDetail>(`/projects/${projectId}/supporting/${encodeURIComponent(supportingId)}`, data)
  .then(response => response.data);

export type ProjectCompetitorStatus = 'confirmed' | 'rejected' | 'pending_review';

export type ProjectCompetitor = {
  id: number;
  name: string;
  address?: string | null;
  distance_meters?: number | null;
  source: string;
  status: ProjectCompetitorStatus;
  raw_category?: string | null;
  created_at?: string | null;
  area_sqm?: number | null;
  machine_count?: number | null;
  cpu?: string | null;
  gpu?: string | null;
  monitor?: string | null;
  hour_price?: number | null;
  member_price?: number | null;
  business_hours?: string | null;
  opening_date?: string | null;
  occupancy_rate?: number | null;
  monthly_sales?: number | null;
  annual_sales?: number | null;
  recharge_info?: string | null;
  remark?: string | null;
};

export type ProjectCompetitorDetailUpdate = Pick<
  ProjectCompetitor,
  | 'area_sqm'
  | 'machine_count'
  | 'cpu'
  | 'gpu'
  | 'monitor'
  | 'hour_price'
  | 'member_price'
  | 'business_hours'
  | 'opening_date'
  | 'occupancy_rate'
  | 'monthly_sales'
  | 'annual_sales'
  | 'recharge_info'
  | 'remark'
>;

export const listProjectCompetitors = (projectId: string) => api
  .get<{items: ProjectCompetitor[]; total: number}>(`/projects/${projectId}/competitors`)
  .then(response => response.data);

export const reviewProjectCompetitor = (
  projectId: string,
  competitorId: number,
  status: ProjectCompetitorStatus,
) => api
  .post<ProjectCompetitor>(`/projects/${projectId}/competitors/${competitorId}/review`, {status})
  .then(response => response.data);

export const getProjectCompetitor = (projectId: string, competitorId: number) => api
  .get<ProjectCompetitor>(`/projects/${projectId}/competitors/${competitorId}`)
  .then(response => response.data);

export const updateProjectCompetitor = (
  projectId: string,
  competitorId: number,
  data: ProjectCompetitorDetailUpdate,
) => api
  .put<ProjectCompetitor>(`/projects/${projectId}/competitors/${competitorId}`, data)
  .then(response => response.data);

export const uploadProjectCsv = (projectId: string, dataType: string, file: File) => {
  const formData = new FormData();
  formData.append('data_type', dataType);
  formData.append('file', file);
  return api.post(`/projects/${projectId}/data/upload`, formData, {timeout: LONG_REQUEST_TIMEOUT_MS}).then(response => response.data);
};

export type ProjectRentItem = {
  id: number;
  address?: string | null;
  area_sqm?: number | null;
  monthly_rent?: number | null;
  rent_unit_price?: number | null;
  property_fee?: number | null;
  transfer_fee?: number | null;
  source: string;
  status: ProjectRentStatus;
  timestamp?: string | null;
  missing_fields: string[];
  detail_completed: boolean;
};

export type ProjectRentStatus = 'pending_review' | 'confirmed' | 'rejected';

export type ProjectRentManualDetail = {
  property_type?: string | null;
  floor?: string | null;
  location_remark?: string | null;
  source_url?: string | null;
  publish_date?: string | null;
  rent_remark?: string | null;
};

export type ProjectRentDetail = ProjectRentItem & {
  manual_detail: ProjectRentManualDetail;
};

export type ProjectRentList = {
  items: ProjectRentItem[];
  total: number;
  incomplete_count: number;
  confirmed_count: number;
  detail_completed_count: number;
};

export const uploadProjectRentCsv = (projectId: string, file: File) => {
  const formData = new FormData();
  formData.append('file', file);
  return api
    .post(`/projects/${projectId}/rent/import`, formData, {timeout: LONG_REQUEST_TIMEOUT_MS})
    .then(response => response.data);
};

export const listProjectRent = (projectId: string) => api
  .get<ProjectRentList>(`/projects/${projectId}/rent`)
  .then(response => response.data);

export const reviewProjectRent = (projectId: string, rentId: number, status: ProjectRentStatus) => api
  .post<ProjectRentItem>(`/projects/${projectId}/rent/${rentId}/review`, {status})
  .then(response => response.data);

export const getProjectRentDetail = (projectId: string, rentId: number) => api
  .get<ProjectRentDetail>(`/projects/${projectId}/rent/${rentId}`)
  .then(response => response.data);

export const updateProjectRentDetail = (
  projectId: string,
  rentId: number,
  data: ProjectRentManualDetail,
) => api
  .put<ProjectRentDetail>(`/projects/${projectId}/rent/${rentId}`, data)
  .then(response => response.data);
