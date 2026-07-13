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
};

export const listProjects = () => api.get('/projects').then(response => response.data);
export const createProject = (data: ProjectCreatePayload) => api.post('/projects', data).then(response => response.data);
export const getProject = (projectId: string) => api.get(`/projects/${projectId}`).then(response => response.data);
export const getProjectDataset = (projectId: string) => api.get(`/projects/${projectId}/dataset`).then(response => response.data);
export const getProjectDataQuality = (projectId: string) => api.get(`/projects/${projectId}/data-quality`).then(response => response.data);
export const getProjectMissingData = (projectId: string) => api.get(`/projects/${projectId}/missing-data`).then(response => response.data);
export const collectProjectAmap = (projectId: string) => api.post(`/projects/${projectId}/collect/amap`, undefined, {timeout: LONG_REQUEST_TIMEOUT_MS}).then(response => response.data);
