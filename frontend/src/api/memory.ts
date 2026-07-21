import {api} from './client';

export type MemoryStatus = 'pending_review' | 'confirmed' | 'disabled';
export type MemoryScope = 'global' | 'project' | 'user';
export type MemoryType = 'preference' | 'business_rule' | 'case_feedback' | 'project_note' | 'data_source_note';

export type MemoryItem = {
  id: number;
  scope: MemoryScope;
  memory_type: MemoryType;
  title: string;
  content: string;
  tags: string[];
  source: string;
  confidence: number;
  status: MemoryStatus;
  project_id?: string | null;
  user_id?: string | null;
  raw_data?: Record<string, unknown>;
  created_at?: string;
  updated_at?: string;
};

export const listMemory = (params?: {
  project_id?: string;
  scope?: string;
  memory_type?: string;
  status?: string;
}) => api.get<{items: MemoryItem[]; total: number}>('/memory', {params}).then(response => response.data);

export const createMemory = (data: Partial<MemoryItem> & {title: string; content: string}) =>
  api.post<MemoryItem>('/memory', data).then(response => response.data);

export const reviewMemory = (memoryId: number, status: MemoryStatus) =>
  api.post<MemoryItem>(`/memory/${memoryId}/review`, {status}).then(response => response.data);

export const updateMemory = (memoryId: number, data: Partial<MemoryItem>) =>
  api.put<MemoryItem>(`/memory/${memoryId}`, data).then(response => response.data);

export const deleteMemory = (memoryId: number) => api.delete(`/memory/${memoryId}`);
