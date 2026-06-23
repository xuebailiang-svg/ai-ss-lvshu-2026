import {useEffect, useRef, useState} from 'react';
import {EnvironmentOutlined} from '@ant-design/icons';

declare global {
  interface Window {
    AMap: any;
    _AMapSecurityConfig?: {securityJsCode: string};
  }
}

let loader: Promise<void> | undefined;

function loadAmap() {
  const key = import.meta.env.VITE_AMAP_JS_KEY as string | undefined;
  if (!key) return Promise.reject(new Error('未配置 VITE_AMAP_JS_KEY'));
  if (window.AMap) return Promise.resolve();
  if (!loader) {
    const code = import.meta.env.VITE_AMAP_SECURITY_JS_CODE as string | undefined;
    if (code) window._AMapSecurityConfig = {securityJsCode: code};
    loader = new Promise((resolve, reject) => {
      const script = document.createElement('script');
      script.src = `https://webapi.amap.com/maps?v=2.0&key=${encodeURIComponent(key)}`;
      script.onload = () => resolve();
      script.onerror = () => reject(new Error('高德地图 JavaScript API 加载失败'));
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

  useEffect(() => {
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
      })
      .catch(error => setError(error.message));
  }, [site?.longitude, site?.latitude, site?.formatted_address]);

  return (
    <section className="map-panel">
      <div ref={container} className="amap-container" />
      {error && (
        <>
          <div className="map-grid" />
          <div className="map-center">
            <EnvironmentOutlined />
            <strong>{site?.formatted_address || '定位后将在地图中显示候选点'}</strong>
            {site?.longitude && (
              <span>
                {site.longitude.toFixed(6)}, {site.latitude?.toFixed(6)} · GCJ-02
              </span>
            )}
          </div>
        </>
      )}
      <div className="map-note">
        {error || '高德地图 · GCJ-02'}；Web Service Key 仅由后端使用
      </div>
    </section>
  );
}
