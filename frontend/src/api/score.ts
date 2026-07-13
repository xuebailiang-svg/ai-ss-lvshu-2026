import {api, LONG_REQUEST_TIMEOUT_MS} from './client';

export const scoreProject = (projectId: string) =>
  api.post(`/projects/${projectId}/score`, undefined, {timeout: LONG_REQUEST_TIMEOUT_MS}).then(response => response.data);
