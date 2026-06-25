export type RuntimeConfig = {
  amapJsKey?: string;
  amapSecurityJsCode?: string;
  mapProvider?: string;
  invalid?: boolean;
};

let cached: Promise<RuntimeConfig> | undefined;

async function fetchJson(url: string) {
  const response = await fetch(url, {cache: 'no-store'});
  if (!response.ok) throw new Error(`${url} returned ${response.status}`);
  return response.json();
}

export async function loadRuntimeConfig(force = false): Promise<RuntimeConfig> {
  if (!cached || force) {
    cached = fetchJson('/runtime-config.json').catch(() => fetchJson('/api/system/runtime-config'));
  }
  const data = await cached;
  return {
    amapJsKey: String(data.amapJsKey || ''),
    amapSecurityJsCode: String(data.amapSecurityJsCode || ''),
    mapProvider: String(data.mapProvider || 'amap'),
    invalid: Boolean(data.invalid),
  };
}

export function maskKey(value?: string | null) {
  const key = String(value || '');
  if (!key) return '未配置';
  if (key.length <= 8) return '***';
  return `${key.slice(0, 4)}****${key.slice(-4)}`;
}
