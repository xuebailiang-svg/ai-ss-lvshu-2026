import {api, LONG_REQUEST_TIMEOUT_MS} from './client';
import type {RegionalStatistic} from './projects';

function adminHeaders(adminToken: string) {
  return {'X-Admin-Token': adminToken};
}

export const forceGovernmentStatsSync = (
  data: {city: string; district?: string; sources: string[]; force_refresh?: boolean},
  adminToken: string,
) => api
  .post('/system/government-stats/sync', data, {headers: adminHeaders(adminToken)})
  .then(response => response.data);

export const listGovernmentStatsReview = (adminToken: string, status = 'pending_review') => api
  .get<{items: RegionalStatistic[]; total: number}>('/system/government-stats/review', {
    params: {status},
    headers: adminHeaders(adminToken),
  })
  .then(response => response.data);

export const reviewGovernmentStatistic = (
  recordId: number,
  status: 'confirmed' | 'pending_review' | 'rejected',
  adminToken: string,
) => api
  .post<RegionalStatistic>(
    `/system/government-stats/${recordId}/review`,
    {status},
    {headers: adminHeaders(adminToken)},
  )
  .then(response => response.data);

export const uploadGovernmentStatistics = (
  data: {
    file: File;
    source_name: string;
    source_url: string;
    scope_level: string;
    scope_code: string;
    scope_name: string;
    stat_period: string;
  },
  adminToken: string,
) => {
  const form = new FormData();
  Object.entries(data).forEach(([key, value]) => form.append(key, value));
  return api
    .post('/system/government-stats/upload', form, {
      headers: adminHeaders(adminToken),
      timeout: LONG_REQUEST_TIMEOUT_MS,
    })
    .then(response => response.data);
};
