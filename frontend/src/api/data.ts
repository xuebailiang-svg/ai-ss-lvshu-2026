import {api} from './client';

export const submitManualInput = (
  projectId: string,
  data: {type: 'competitor' | 'rent' | 'population' | 'supplement'; target_id?: string; data: Record<string, any>},
) => api.post(`/projects/${projectId}/manual-input`, data).then(response => response.data);

export const listManualInputs = (projectId: string) => api.get(`/projects/${projectId}/manual-inputs`).then(response => response.data);
