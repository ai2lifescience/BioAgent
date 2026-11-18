import { createRoot } from 'react-dom/client';
import App from './App';
import AssistantPage from './features/assistant/AssistantPage';
import AssistantDemoPage from '../../web_bridge/frontend/demo/AssistantDemoPage';
import { AppErrorBoundary } from './components/AppErrorBoundary';
import { AuthGate, installAuthEvents } from './components/AuthGate';
import { WebsiteProvider } from '../../web_bridge/frontend/WebsiteProvider';

const root = document.getElementById('root');
if (!root) throw new Error('Pipeline2Agent mount point is missing.');
const base = new URL(import.meta.env.BASE_URL, window.location.origin).pathname;
const pathname = window.location.pathname;
const appPath = pathname.startsWith(base) ? '/' + pathname.slice(base.length) : pathname;
const path = appPath.replace(/\/+$/, '') || '/';
const Page = path === '/assistant' || path === '/assistant.html' ? AssistantPage : path === '/assistant-demo' ? AssistantDemoPage : App;
installAuthEvents();
const Gate = Page === AssistantPage && new URLSearchParams(window.location.search).get('website_auth') === '1' ? WebsiteProvider : AuthGate;
createRoot(root).render(<AppErrorBoundary><Gate><Page /></Gate></AppErrorBoundary>);
