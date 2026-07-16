import {api} from './client';

export type DataSourceAvailability = 'available' | 'disabled' | 'not_configured';

export type DataSourceStatus = {
  name: string;
  display_name: string;
  status: DataSourceAvailability;
  description: string;
  capabilities: string[];
  check_supported: boolean;
};

export type ConnectivityStatus = 'ok' | 'failed' | 'not_configured' | 'disabled' | 'unsupported';

export type ConnectivityCheck = {
  name: string;
  configured: boolean;
  reachable: boolean;
  status: ConnectivityStatus;
  message: string;
  latency_ms: number;
  checked_at: string;
};

export const getDataSourceStatus = () => api
  .get<{items: DataSourceStatus[]}>('/data-sources/status')
  .then(response => response.data);

export const checkDataSourceConnectivity = (providerName: string) => api
  .post<ConnectivityCheck>(`/data-sources/${encodeURIComponent(providerName)}/check`)
  .then(response => response.data);
