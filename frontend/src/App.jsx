import { useState } from 'react';
import './App.css';
import TopBar from './components/TopBar';
import MacroPanel from './components/MacroPanel';
import AlphaTable from './components/AlphaTable';
import SentimentPanel from './components/SentimentPanel';
import PortfolioPanel from './components/PortfolioPanel';
import BacktestPanel from './components/BacktestPanel';
import InsightsPanel from './components/InsightsPanel';

const TABS = [
  { key: 'overview',  label: 'Overview' },
  { key: 'alpha',     label: 'Alpha & Sentiment' },
  { key: 'portfolio', label: 'Portfolio' },
  { key: 'backtest',  label: 'Backtest' },
  { key: 'insights',  label: 'Insights' },
];

export default function App() {
  const [activeTab, setActiveTab] = useState('overview');

  return (
    <div className="app-shell">
      <TopBar />

      <div className="tab-bar">
        <div className="nav-tabs">
          {TABS.map(tab => (
            <button
              key={tab.key}
              className={`nav-tab ${activeTab === tab.key ? 'active' : ''}`}
              onClick={() => setActiveTab(tab.key)}
            >
              {tab.label}
            </button>
          ))}
        </div>
      </div>

      <main className="main-content">
        {activeTab === 'overview' && (
          <div className="main-grid fade-in">
            <div className="grid-left">
              <MacroPanel />
              <SentimentPanel />
            </div>
            <div className="grid-right">
              <PortfolioPanel />
            </div>
          </div>
        )}

        {activeTab === 'alpha' && (
          <div className="full-width fade-in">
            <AlphaTable />
            <SentimentPanel />
          </div>
        )}

        {activeTab === 'portfolio' && (
          <div className="full-width fade-in">
            <PortfolioPanel />
          </div>
        )}

        {activeTab === 'backtest' && (
          <div className="full-width fade-in">
            <BacktestPanel />
          </div>
        )}

        {activeTab === 'insights' && (
          <div className="full-width fade-in">
            <InsightsPanel />
          </div>
        )}
      </main>

      <footer className="app-footer">
        <span>MarketOS © 2026 · Quantitative Intelligence Platform</span>
        <span className="footer-dot">·</span>
        <span style={{ color: 'var(--text-dim)' }}>Data refreshes every 30s</span>
      </footer>
    </div>
  );
}
