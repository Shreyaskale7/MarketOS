import './PortfolioPanel.css';
import useApi from '../hooks/useApi';

function getRegimeClass(label) {
  if (!label) return 'neutral';
  const l = label.toUpperCase();
  if (l.includes('BULL')) return 'bull';
  if (l.includes('BEAR')) return 'bear';
  return 'neutral';
}

function formatPct(val) {
  if (val == null) return '—';
  return Number(val).toFixed(2) + '%';
}

function formatNum(val, decimals = 2) {
  if (val == null) return '—';
  return Number(val).toFixed(decimals);
}

function getSeverityColor(severity) {
  if (!severity) return '';
  const s = severity.toUpperCase();
  if (s === 'LOW' || s === 'NONE') return 'cyan';
  if (s === 'MEDIUM' || s === 'MODERATE') return 'amber';
  if (s === 'HIGH' || s === 'CRITICAL') return 'red';
  return '';
}

export default function PortfolioPanel() {
  const { data, loading, error } = useApi('/api/portfolio', 30000);

  if (error) {
    return (
      <div className="glass-card portfolio-panel">
        <div className="section-title">Portfolio</div>
        <div className="empty-state">
          <div className="icon">⚠</div>
          <div className="text">{error}</div>
        </div>
      </div>
    );
  }

  if (loading || !data) {
    return (
      <div className="glass-card portfolio-panel">
        <div className="section-title">Portfolio</div>
        <div className="portfolio-skeleton-metrics">
          {[1, 2, 3, 4, 5, 6].map((i) => (
            <div key={i} className="skeleton portfolio-skeleton-card" />
          ))}
        </div>
        {[1, 2, 3, 4].map((i) => (
          <div key={i} className="skeleton portfolio-skeleton-row" />
        ))}
      </div>
    );
  }

  const positions = data.positions || [];

  return (
    <div className="glass-card portfolio-panel fade-in">
      <div className="section-title">Portfolio</div>

      {/* Top metrics */}
      <div className="portfolio-metrics">
        <div className="portfolio-metric-card">
          <span className="metric-label">Expected Return</span>
          <span className={`metric-value ${Number(data.expected_return) >= 0 ? 'green' : 'red'}`}>
            {formatPct(data.expected_return)}
          </span>
        </div>
        <div className="portfolio-metric-card">
          <span className="metric-label">Portfolio Vol</span>
          <span className="metric-value amber">{formatPct(data.portfolio_vol)}</span>
        </div>
        <div className="portfolio-metric-card">
          <span className="metric-label">Sharpe-Like</span>
          <span className="metric-value cyan">{formatNum(data.sharpe_like)}</span>
        </div>
        <div className="portfolio-metric-card">
          <span className="metric-label">Total Exposure</span>
          <span className="metric-value purple">{formatPct(data.total_exposure_pct)}</span>
        </div>
        <div className="portfolio-metric-card">
          <span className="metric-label">Regime</span>
          <span className={`regime-badge ${getRegimeClass(data.regime_label)}`}>
            {data.regime_label || '—'}
          </span>
        </div>
        <div className="portfolio-metric-card">
          <span className="metric-label">Severity</span>
          <span className={`metric-value ${getSeverityColor(data.severity)}`}>
            {data.severity || '—'}
          </span>
        </div>
      </div>

      {/* Rules applied */}
      {data.rules_applied && data.rules_applied.length > 0 && (
        <div className="portfolio-rules">
          <span className="portfolio-rules-label">Rules:</span>
          {data.rules_applied.map((rule, i) => (
            <span key={i} className="pill amber">{rule}</span>
          ))}
        </div>
      )}

      {/* Positions table */}
      <div className="portfolio-table-wrapper">
        <table className="data-table">
          <thead>
            <tr>
              <th>Subsector</th>
              <th>Sector</th>
              <th>Weight %</th>
              <th>Adj Weight %</th>
              <th>Exp Return</th>
              <th>Volatility</th>
              <th>Alpha</th>
            </tr>
          </thead>
          <tbody>
            {positions.map((pos, idx) => (
              <tr key={pos.subsector || idx}>
                <td>{pos.subsector || '—'}</td>
                <td>{pos.sector || '—'}</td>
                <td>{formatPct(pos.weight)}</td>
                <td>{formatPct(pos.adjusted_weight)}</td>
                <td>
                  <span className={`change ${Number(pos.expected_return_pct) >= 0 ? 'pos' : 'neg'}`}>
                    {formatPct(pos.expected_return_pct)}
                  </span>
                </td>
                <td>{formatPct(pos.volatility_pct)}</td>
                <td>{formatNum(pos.alpha_score, 3)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {positions.length === 0 && (
        <div className="empty-state">
          <div className="icon">📁</div>
          <div className="text">No positions in portfolio</div>
        </div>
      )}
    </div>
  );
}
