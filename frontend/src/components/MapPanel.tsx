import {useEffect, useRef, useState} from 'react';
import {EnvironmentOutlined} from '@ant-design/icons';
import {loadRuntimeConfig} from '../runtimeConfig';

declare global {
  interface Window {
    AMap: any;
    _AMapSecurityConfig?: {securityJsCode: string};
  }
}

let loader: Promise<void> | undefined;
let loadedKey = '';

async function loadAmap() {
  const config = await loadRuntimeConfig();
  const key = config.amapJsKey;
  if (!key) return Promise.reject(new Error('前端高德地图 JS Key 未配置，请在服务器配置 /etc/esports-site-selection/frontend-runtime.json'));
  if (window.AMap && loadedKey === key) return Promise.resolve();
  if (!loader || loadedKey !== key) {
    const code = config.amapSecurityJsCode;
    if (code) window._AMapSecurityConfig = {securityJsCode: code};
    loader = new Promise((resolve, reject) => {
      const script = document.createElement('script');
      script.src = `https://webapi.amap.com/maps?v=2.0&key=${encodeURIComponent(key)}`;
      script.async = true;
      script.onload = () => {
        if (window.AMap) {
          loadedKey = key;
          resolve();
        }
        else {
          loader = undefined;
          reject(new Error('高德地图 JavaScript SDK 已加载但 AMap 未初始化，请检查 Key、securityJsCode、域名白名单或浏览器 console。'));
        }
      };
      script.onerror = () => {
        loader = undefined;
        reject(new Error('高德地图 JavaScript API 加载失败，请检查网络、Key、域名白名单或安全密钥配置。'));
      };
      document.head.appendChild(script);
    });
  }
  return loader;
}

export default function MapPanel({
  site,
}: {
  site?: {longitude?: number; latitude?: number; formatted_address?: string};
}) {
  const container = useRef<HTMLDivElement>(null);
  const map = useRef<any>(null);
  const marker = useRef<any>(null);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    setError('');
    loadAmap()
      .then(() => {
        if (!container.current) return;
        if (!map.current) {
          map.current = new window.AMap.Map(container.current, {
            zoom: 12,
            center: [116.397428, 39.90923],
            viewMode: '2D',
          });
        }
        if (site?.longitude && site.latitude) {
          const position = [site.longitude, site.latitude];
          if (marker.current) marker.current.setPosition(position);
          else {
            marker.current = new window.AMap.Marker({
              position,
              map: map.current,
              title: site.formatted_address,
            });
          }
          map.current.setZoomAndCenter(15, position);
        }
        setLoading(false);
      })
      .catch(error => {
        setLoading(false);
        setError(error.message);
      });
  }, [site?.longitude, site?.latitude, site?.formatted_address]);

  return (
    <section className="map-panel">
      <div ref={container} className="amap-container" />
      {(error || loading) && (
        <>
          <div className="map-grid" />
          <div className="map-center">
            <EnvironmentOutlined />
            <strong>{error || (site?.formatted_address || '正在加载高德地图')}</strong>
            {site?.longitude && (
              <span>
                {site.longitude.toFixed(6)}, {site.latitude?.toFixed(6)} · GCJ-02
              </span>
            )}
          </div>
        </>
      )}
      <div className="map-note">
        {error || (loading ? '正在加载高德地图' : '高德地图 · GCJ-02')}；Web Service Key 仅由后端使用
      </div>
    </section>
  );
}
