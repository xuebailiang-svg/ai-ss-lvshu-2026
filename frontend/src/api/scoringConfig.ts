import {api} from './client';

export type ScoringFactorConfig = {
  key: string;
  name: string;
  description?: string | null;
  weight: number;
  enabled: boolean;
  data_sources: string[];
  sort_order: number;
  config?: Record<string, unknown>;
};

export type ScoringDimensionConfig = {
  key: string;
  name: string;
  description?: string | null;
  weight: number;
  enabled: boolean;
  data_sources: string[];
  sort_order: number;
  factors: ScoringFactorConfig[];
};

export type ScoringConfigResponse = {
  dimensions: ScoringDimensionConfig[];
  total_weight: number;
  normalized: boolean;
};

export const getScoringConfig = () =>
  api.get<ScoringConfigResponse>('/scoring/config').then(response => response.data);

export const updateScoringConfig = (dimensions: ScoringDimensionConfig[]) =>
  api.put<ScoringConfigResponse>('/scoring/config', {dimensions}).then(response => response.data);

export const resetScoringConfig = () =>
  api.post<ScoringConfigResponse>('/scoring/config/reset').then(response => response.data);
