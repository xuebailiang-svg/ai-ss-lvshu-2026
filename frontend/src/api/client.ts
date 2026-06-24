import axios from 'axios';
import type {CompetitorEnrichment, Evaluation, PropertySurvey, Score} from '../types';

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
export const score = (id: number) => api.post<Score>(`/evaluations/${id}/score`).then(response => response.data);
export const report = (id: string) => api.get(`/evaluations/${id}/report`).then(response => response.data);
export const saveCompetitorEnrichment = (id: number, data: CompetitorEnrichment) => api.put(`/competitors/${id}/enrichment`, data).then(response => response.data);
export const competitorHistory = (id: number) => api.get(`/competitors/${id}/enrichments`).then(response => response.data);
export const compareEvaluations = (evaluation_ids: number[]) => api.post('/evaluations/compare', {evaluation_ids}).then(response => response.data);
