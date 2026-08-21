import {Layout, Menu} from 'antd';
import {ControlOutlined, EnvironmentOutlined, FolderOpenOutlined} from '@ant-design/icons';
import {Link, Navigate, Route, Routes, useLocation, useParams} from 'react-router-dom';
import ProjectsPage from './pages/Projects';
import ProjectCreatePage from './pages/Projects/Create';
import ProjectDetailPage from './pages/ProjectDetail';
import ProjectSupplementPage from './pages/ProjectSupplement';
import SystemConfig from './pages/SystemConfig';
import './styles/app.css';

function LegacyProjectRedirect() {
  const {projectId} = useParams();
  return <Navigate to={projectId ? `/projects/${projectId}` : '/'} replace />;
}

export default function App() {
  const location = useLocation();
  const selectedKey = location.pathname.startsWith('/settings')
    ? '/settings'
    : '/projects';

  return (
    <Layout className="app">
      <Layout.Header>
        <div className="brand"><EnvironmentOutlined /> 电竞馆智能选址</div>
        <Menu
          theme="dark"
          mode="horizontal"
          selectedKeys={[selectedKey]}
          items={[
            {key: '/projects', icon: <FolderOpenOutlined />, label: <Link to="/">选址项目</Link>},
            {key: '/settings', icon: <ControlOutlined />, label: <Link to="/settings">系统配置</Link>},
          ]}
        />
      </Layout.Header>
      <Layout.Content>
        <Routes>
          <Route path="/" element={<ProjectsPage />} />
          <Route path="/projects" element={<ProjectsPage />} />
          <Route path="/projects/create" element={<ProjectCreatePage />} />
          <Route path="/projects/:projectId" element={<ProjectDetailPage />} />
          <Route path="/projects/:projectId/supplement" element={<ProjectSupplementPage />} />
          <Route path="/settings" element={<SystemConfig />} />

          <Route path="/workbench" element={<Navigate to="/" replace />} />
          <Route path="/system-config" element={<Navigate to="/settings" replace />} />
          <Route path="/projects/:projectId/upload" element={<LegacyProjectRedirect />} />
          <Route path="/projects/:projectId/chat" element={<LegacyProjectRedirect />} />
          <Route path="/legacy/projects/:projectId/*" element={<LegacyProjectRedirect />} />
          <Route path="/legacy/*" element={<Navigate to="/" replace />} />
          <Route path="/agent" element={<Navigate to="/" replace />} />
          <Route path="/evaluations/:id" element={<Navigate to="/" replace />} />
          <Route path="/history" element={<Navigate to="/" replace />} />
          <Route path="/reports/:id" element={<Navigate to="/" replace />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </Layout.Content>
    </Layout>
  );
}
