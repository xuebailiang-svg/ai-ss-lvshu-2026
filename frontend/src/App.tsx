import {Layout, Menu} from 'antd';
import {EnvironmentOutlined,HistoryOutlined, SettingOutlined} from '@ant-design/icons';
import {Link, Route, Routes, useLocation} from 'react-router-dom';
import NewEvaluation from './pages/NewEvaluation';
import History from './pages/History';
import ReportPage from './pages/Report';
import SystemConfig from './pages/SystemConfig';
import './styles/app.css';

export default function App() {
  const location = useLocation();
  return (
    <Layout className="app">
      <Layout.Header>
        <div className="brand"><EnvironmentOutlined /> 电竞馆智能选址系统</div>
        <Menu
          theme="dark"
          mode="horizontal"
          selectedKeys={[location.pathname]}
          items={[
            {key: '/', label: <Link to="/">新地址评估</Link>},
            {key: '/history', icon: <HistoryOutlined />, label: <Link to="/history">历史评估</Link>},
            {key: '/system-config', icon: <SettingOutlined />, label: <Link to="/system-config">系统配置</Link>},
          ]}
        />
      </Layout.Header>
      <Layout.Content>
        <Routes>
          <Route path="/" element={<NewEvaluation />} />
          <Route path="/evaluations/:id" element={<NewEvaluation />} />
          <Route path="/history" element={<History />} />
          <Route path="/reports/:id" element={<ReportPage />} />
          <Route path="/system-config" element={<SystemConfig />} />
        </Routes>
      </Layout.Content>
    </Layout>
  );
}
