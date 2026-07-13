import {api, LONG_REQUEST_TIMEOUT_MS} from './client';

export const createProjectChatSession = (projectId: string) =>
  api.post(`/projects/${projectId}/chat/session`).then(response => response.data);

export const sendProjectChatMessage = (sessionId: string, message: string) =>
  api.post(`/chat/${sessionId}/message`, {message}, {timeout: LONG_REQUEST_TIMEOUT_MS}).then(response => response.data);

export const listProjectChatMessages = (sessionId: string) =>
  api.get(`/chat/${sessionId}/messages`).then(response => response.data);
