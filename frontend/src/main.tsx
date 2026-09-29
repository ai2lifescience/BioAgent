import { createRoot } from 'react-dom/client';
import App from './App';
import AssistantPage from './features/assistant/AssistantPage';
import AssistantDemoPage from './features/demo/AssistantDemoPage';
import { AppErrorBoundary } from './components/AppErrorBoundary';

const root = document.getElementById('root');
if (!root) throw new Error('Pipeline2Agent mount point is missing.');
const path = window.location.pathname.replace(/\/+$/, '') || '/';
const Page = path === '/assistant' || path === '/assistant.html' ? AssistantPage : path === '/assistant-demo' ? AssistantDemoPage : App;
createRoot(root).render(<AppErrorBoundary><Page /></AppErrorBoundary>);
