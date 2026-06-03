import './AlphaTable.css';
import useApi from '../hooks/useApi';

function formatScore(val) {
  if (val == null) return '—';
  return Number(val).toFixed(3);
}

function getScoreBarWidth(score, maxScore) {
  if (score == null || maxScore === 0) return 0;
  return Math.min((Math.abs(Number(score)) / maxScore) * 100, 100);
}

export default function AlphaTable() {
  const { data, loading, error } = useApi('/api/alpha', 30000);

  if (error) {
    return (
      <div className="glass-card alpha-table-panel">
        <div className="section-title">Alpha Signals</div>
        <div className="empty-state">
          <div className="icon">⚠</div>
          <div className="text">{error}</div>
        </div>
      </div>
    );
  }

  if (loading || !data) {
    return (
      <div className="glass-card alpha-table-panel">
        <div className="section-title">Alpha Signals</div>
        {[1, 2, 3, 4, 5, 6].map((i) => (
          <div key={i} className="skeleton alpha-skeleton-row" />
        ))}
      </div>
    );
  }

  const signals = [...(data.signals || [])].sort(
    (a, b) => (b.alpha_score || 0) - (a.alpha_score || 0)
  );
  const maxScore = signals.length > 0 ? Math.max(...signals.map((s) => Math.abs(s.alpha_score || 0))) : 1;

  return (
    <div className="glass-card alpha-table-panel fade-in">
      <div className="alpha-table-header">
        <div className="section-title" style={{ marginBottom: 0 }}>Alpha Signals</div>
        <div className="alpha-table-stats">
          <div className="alpha-stat">
            <span className="alpha-stat-label">Active</span>
            <span className="alpha-stat-value">{data.active_count ?? '—'}</span>
          </div>
          <div className="alpha-stat">
            <span className="alpha-stat-label">Excluded</span>
            <span className="alpha-stat-value" style={{ color: 'var(--red)' }}>
              {data.excluded_count ?? '—'}
            </span>
          </div>
          {data.regime_label && (
            <span className={`regime-badge ${getRegimeClass(data.regime_label)}`}>
              {data.regime_label}
            </span>
          )}
        </div>
      </div>

      <div className="alpha-table-wrapper">
        <table className="data-table">
          <thead>
            <tr>
              <th>#</th>
              <th>Subsector</th>
              <th>Alpha Score</th>
              <th>Momentum</th>
              <th>Mean Rev</th>
              <th>Volatility</th>
              <th>Macro</th>
              <th>Status</th>
            </tr>
          </thead>
          <tbody>
            {signals.map((sig, idx) => (
              <tr key={sig.subsector || idx}>
                <td>
                  <span className="alpha-rank">{idx + 1}</span>
                </td>
                <td className="subsector-cell">{sig.subsector || '—'}</td>
                <td>
                  <div className="alpha-score-cell">
                    <span>{formatScore(sig.alpha_score)}</span>
                    <div className="alpha-bar">
                      <div
                        className="alpha-bar-fill"
                        style={{ width: `${getScoreBarWidth(sig.alpha_score, maxScore)}%` }}
                      />
                    </div>
                  </div>
                </td>
                <td>{formatScore(sig.momentum)}</td>
                <td>{formatScore(sig.mean_reversion)}</td>
                <td>{formatScore(sig.vol_breakout)}</td>
                <td>{formatScore(sig.macro_align)}</td>
                <td>
                  <span
                    className={`status-pill ${
                      sig.status === 'PASS' ? 'pass' : 'excluded'
                    }`}
                  >
                    {sig.status || '—'}
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {signals.length === 0 && (
        <div className="empty-state">
          <div className="icon">📊</div>
          <div className="text">No alpha signals available</div>
        </div>
      )}
    </div>
  );
}

function getRegimeClass(label) {
  if (!label) return 'neutral';
  const l = label.toUpperCase();
  if (l.includes('BULL')) return 'bull';
  if (l.includes('BEAR')) return 'bear';
  return 'neutral';
}
