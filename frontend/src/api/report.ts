import {api, LONG_REQUEST_TIMEOUT_MS} from './client';

export const generateAiReport = (projectId: string) =>
  api.post(`/projects/${projectId}/ai-report`, undefined, {timeout: LONG_REQUEST_TIMEOUT_MS}).then(response => response.data);
