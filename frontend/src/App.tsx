import {Layout, Menu} from 'antd';
import {ControlOutlined, DesktopOutlined, EnvironmentOutlined} from '@ant-design/icons';
import {Link, Route, Routes, useLocation} from 'react-router-dom';
import WorkbenchPage from './pages/Workbench';
import SystemConfig from './pages/SystemConfig';
import NewEvaluation from './pages/NewEvaluation';
import History from './pages/History';
import ReportPage from './pages/Report';
import AgentAnalysis from './pages/AgentAnalysis';
import ProjectsPage from './pages/Projects';
import ProjectCreatePage from './pages/Projects/Create';
import ProjectDetailPage from './pages/ProjectDetail';
import ProjectSupplementPage from './pages/ProjectSupplement';
import ProjectUploadPage from './pages/ProjectUpload';
import ProjectChat from './pages/ProjectChat';
import './styles/app.css';

export default function App() {
  const location = useLocation();
  const selectedKey = location.pathname.startsWith('/settings') || location.pathname.startsWith('/system-config')
    ? '/settings'
    : '/workbench';

  return (
    <Layout className="app">
      <Layout.Header>
        <div className="brand"><EnvironmentOutlined /> 电竞馆智能选址系统</div>
        <Menu
          theme="dark"
          mode="horizontal"
          selectedKeys={[selectedKey]}
          items={[
            {key: '/workbench', icon: <DesktopOutlined />, label: <Link to="/">工作台</Link>},
            {key: '/settings', icon: <ControlOutlined />, label: <Link to="/settings">配置</Link>},
          ]}
        />
      </Layout.Header>
      <Layout.Content>
        <Routes>
          <Route path="/" element={<WorkbenchPage />} />
          <Route path="/workbench" element={<WorkbenchPage />} />
          <Route path="/settings" element={<SystemConfig />} />

          <Route path="/legacy/new-evaluation" element={<NewEvaluation />} />
          <Route path="/legacy/agent" element={<AgentAnalysis />} />
          <Route path="/legacy/projects" element={<ProjectsPage />} />
          <Route path="/legacy/projects/create" element={<ProjectCreatePage />} />
          <Route path="/legacy/projects/:projectId/supplement" element={<ProjectSupplementPage />} />
          <Route path="/legacy/projects/:projectId/upload" element={<ProjectUploadPage />} />
          <Route path="/legacy/projects/:projectId" element={<ProjectDetailPage />} />
          <Route path="/legacy/projects/:projectId/chat" element={<ProjectChat />} />
          <Route path="/legacy/evaluations/:id" element={<NewEvaluation />} />
          <Route path="/legacy/history" element={<History />} />
          <Route path="/legacy/reports/:id" element={<ReportPage />} />

          <Route path="/agent" element={<AgentAnalysis />} />
          <Route path="/projects" element={<ProjectsPage />} />
          <Route path="/projects/create" element={<ProjectCreatePage />} />
          <Route path="/projects/:projectId/supplement" element={<ProjectSupplementPage />} />
          <Route path="/projects/:projectId/upload" element={<ProjectUploadPage />} />
          <Route path="/projects/:projectId" element={<ProjectDetailPage />} />
          <Route path="/projects/:projectId/chat" element={<ProjectChat />} />
          <Route path="/evaluations/:id" element={<NewEvaluation />} />
          <Route path="/history" element={<History />} />
          <Route path="/reports/:id" element={<ReportPage />} />
          <Route path="/system-config" element={<SystemConfig />} />
        </Routes>
      </Layout.Content>
    </Layout>
  );
}
