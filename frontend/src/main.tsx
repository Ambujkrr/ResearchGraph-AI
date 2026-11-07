import React from 'react';
import ReactDOM from 'react-dom/client';
import App from './App';
import DemoApp from './DemoApp';
import './style.css';
ReactDOM.createRoot(document.getElementById('root')!).render(<React.StrictMode>{import.meta.env.VITE_DEMO_MODE === 'true' ? <DemoApp /> : <App />}</React.StrictMode>);
