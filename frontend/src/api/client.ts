import axios from 'axios';
import type {CompetitorEnrichment, Evaluation, PoiListResponse, PoiPublic, PoiTemplates, PropertySurvey, Score} from '../types';

export const api = axios.create({baseURL: '/api', timeout: 20000});

export const createEvaluation = (data: {
  name: string;
  city: string;
  address: string;
  radius: number;
  property: PropertySurvey;
}) => api.post<Evaluation>('/evaluations', data).then(response => response.data);

export const listEvaluations = (params?: {
  city?: string;
  q?: string;
  recommendation?: string;
  has_hard_risk?: boolean;
  sort_by?: string;
  order?: string;
}) => api.get<Evaluation[]>('/evaluations', {params}).then(response => response.data);

export const getEvaluation = (id: string | number) => api.get<Evaluation>(`/evaluations/${id}`).then(response => response.data);
export const updateProperty = (id: number, data: PropertySurvey) => api.put(`/evaluations/${id}/property`, data).then(response => response.data);
export const geocode = (id: number) => api.post(`/evaluations/${id}/geocode`).then(response => response.data);
export const collectPois = (id: number) => api.post(`/evaluations/${id}/collect-pois`).then(response => response.data);
export const poiDiagnostics = (id: number) => api.get(`/evaluations/${id}/poi-diagnostics`).then(response => response.data);
export const poiTemplates = () => api.get<PoiTemplates>('/poi/templates').then(response => response.data);
export const listPois = (id: number) => api.get<PoiListResponse>(`/evaluations/${id}/pois`).then(response => response.data);
export const createManualPoi = (id: number, data: Record<string, any>) => api.post<PoiPublic>(`/evaluations/${id}/pois`, data).then(response => response.data);
export const savePoiEnrichment = (evaluationId: number, poiId: number, data: Record<string, any>) => api.put<PoiPublic>(`/evaluations/${evaluationId}/pois/${poiId}/enrichment`, data).then(response => response.data);
export const importPoisCsv = (id: number, category: string, csv_text: string) => api.post(`/evaluations/${id}/pois/import`, {category, csv_text}).then(response => response.data);
export const exportPoisUrl = (id: number, category: string) => `/api/evaluations/${id}/pois/export?category=${encodeURIComponent(category)}`;
export const score = (id: number) => api.post<Score>(`/evaluations/${id}/score`).then(response => response.data);
export const report = (id: string) => api.get(`/evaluations/${id}/report`).then(response => response.data);
export const saveCompetitorEnrichment = (id: number, data: CompetitorEnrichment) => api.put(`/competitors/${id}/enrichment`, data).then(response => response.data);
export const competitorHistory = (id: number) => api.get(`/competitors/${id}/enrichments`).then(response => response.data);
export const compareEvaluations = (evaluation_ids: number[]) => api.post('/evaluations/compare', {evaluation_ids}).then(response => response.data);
export const configStatus = () => api.get('/system/config-status').then(response => response.data);
export const amapGeocodeTest = (params: {city: string; address: string}) => api.get('/system/amap/geocode-test', {params}).then(response => response.data);
