import {Layout, Menu} from 'antd';
import {EnvironmentOutlined, FolderOpenOutlined, HistoryOutlined, SettingOutlined} from '@ant-design/icons';
import {Link, Route, Routes, useLocation} from 'react-router-dom';
import NewEvaluation from './pages/NewEvaluation';
import History from './pages/History';
import ReportPage from './pages/Report';
import SystemConfig from './pages/SystemConfig';
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
  const selectedKey = location.pathname.startsWith('/projects') ? '/projects' : location.pathname;

  return (
    <Layout className="app">
      <Layout.Header>
        <div className="brand"><EnvironmentOutlined /> 电竞馆智能选址系统</div>
        <Menu
          theme="dark"
          mode="horizontal"
          selectedKeys={[selectedKey]}
          items={[
            {key: '/', label: <Link to="/">新地址评估</Link>},
            {key: '/projects', icon: <FolderOpenOutlined />, label: <Link to="/projects">项目工作台</Link>},
            {key: '/agent', label: <Link to="/agent">Agent 分析</Link>},
            {key: '/history', icon: <HistoryOutlined />, label: <Link to="/history">历史评估</Link>},
            {key: '/system-config', icon: <SettingOutlined />, label: <Link to="/system-config">系统配置</Link>},
          ]}
        />
      </Layout.Header>
      <Layout.Content>
        <Routes>
          <Route path="/" element={<NewEvaluation />} />
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
