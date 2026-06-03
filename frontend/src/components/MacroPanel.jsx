import './MacroPanel.css';
import useApi from '../hooks/useApi';

function getRegimeClass(label) {
  if (!label) return 'neutral';
  const l = label.toUpperCase();
  if (l.includes('BULL')) return 'bull';
  if (l.includes('BEAR')) return 'bear';
  return 'neutral';
}

function formatChange(val) {
  if (val == null) return { text: '—', cls: 'flat' };
  const n = Number(val);
  if (n > 0) return { text: `+${n.toFixed(2)}%`, cls: 'pos' };
  if (n < 0) return { text: `${n.toFixed(2)}%`, cls: 'neg' };
  return { text: '0.00%', cls: 'flat' };
}

function formatNum(val, decimals = 2) {
  if (val == null) return '—';
  return Number(val).toLocaleString('en-IN', {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  });
}

function getSubRegimePillClass(label) {
  if (!label) return '';
  const l = label.toUpperCase();
  if (l.includes('LOW') || l.includes('STABLE') || l.includes('BULL') || l.includes('POSITIVE'))
    return 'cyan';
  if (l.includes('HIGH') || l.includes('VOLATILE') || l.includes('BEAR') || l.includes('NEGATIVE'))
    return 'amber';
  return '';
}

function getSignalBarWidth(val) {
  if (val == null) return 0;
  return Math.min(Math.abs(Number(val)) * 5, 100);
}

export default function MacroPanel() {
  const { data, loading, error } = useApi('/api/macro', 30000);

  if (error) {
    return (
      <div className="glass-card macro-panel">
        <div className="section-title">Macro Regime</div>
        <div className="empty-state">
          <div className="icon">⚠</div>
          <div className="text">{error}</div>
        </div>
      </div>
    );
  }

  if (loading || !data) {
    return (
      <div className="glass-card macro-panel">
        <div className="section-title">Macro Regime</div>
        <div className="macro-regime-header">
          <div className="macro-regime-main">
            <div className="skeleton macro-skeleton-score" />
            <div className="skeleton macro-skeleton-badge" />
          </div>
        </div>
        <div className="macro-skeleton-row">
          {[1, 2, 3, 4].map((i) => (
            <div key={i} className="skeleton macro-skeleton-card" />
          ))}
        </div>
      </div>
    );
  }

  const regime = data.regime || {};
  const macroData = data.macro || {};
  const regimeClass = getRegimeClass(regime.overall_regime);

  const indicators = [
    {
      label: 'India VIX',
      value: formatNum(macroData.india_vix?.current),
      change: formatChange(macroData.india_vix?.change_pct),
      score: macroData.india_vix?.score,
    },
    {
      label: 'USD/INR',
      value: formatNum(macroData.usdinr?.current),
      change: formatChange(macroData.usdinr?.change_pct),
      score: macroData.usdinr?.change_pct,
    },
    {
      label: 'Brent Crude',
      value: macroData.brent_crude?.current != null
        ? `$${formatNum(macroData.brent_crude.current)}`
        : '—',
      change: formatChange(macroData.brent_crude?.change_pct),
      score: macroData.brent_crude?.change_pct,
    },
    {
      label: 'FII Flows',
      value: macroData.fii_flows?.estimated_crore != null
        ? `₹${formatNum(macroData.fii_flows.estimated_crore, 0)} Cr`
        : '—',
      change: { text: macroData.fii_flows?.signal || '—', cls: macroData.fii_flows?.signal === 'BUYING' ? 'pos' : macroData.fii_flows?.signal === 'SELLING' ? 'neg' : 'flat' },
      score: macroData.fii_flows?.estimated_crore,
    },
  ];

  return (
    <div className="glass-card macro-panel fade-in">
      <div className="section-title">Macro Regime</div>

      {/* Regime Header */}
      <div className="macro-regime-header">
        <div className="macro-regime-main">
          <div className={`macro-regime-score ${regimeClass}`}>
            {regime.regime_score != null ? Number(regime.regime_score).toFixed(1) : '—'}
          </div>
          <span className={`regime-badge macro-regime-badge ${regimeClass}`}>
            {regime.overall_regime || 'N/A'}
          </span>
        </div>

        {/* Sub-regime pills */}
        <div className="macro-sub-regimes">
          {regime.volatility_regime && (
            <div className="macro-sub-regime">
              <span className="macro-sub-label">VOL</span>
              <span className={`pill ${getSubRegimePillClass(regime.volatility_regime)}`}>
                {regime.volatility_regime}
              </span>
            </div>
          )}
          {regime.rate_regime && (
            <div className="macro-sub-regime">
              <span className="macro-sub-label">RATE</span>
              <span className={`pill ${getSubRegimePillClass(regime.rate_regime)}`}>
                {regime.rate_regime}
              </span>
            </div>
          )}
          {regime.global_regime && (
            <div className="macro-sub-regime">
              <span className="macro-sub-label">GLOBAL</span>
              <span className={`pill ${getSubRegimePillClass(regime.global_regime)}`}>
                {regime.global_regime}
              </span>
            </div>
          )}
        </div>
      </div>

      {/* Indicators Grid */}
      <div className="macro-indicators-grid">
        {indicators.map((ind) => {
          const barWidth = getSignalBarWidth(ind.score);
          const barClass = ind.change.cls === 'pos' ? 'pos' : ind.change.cls === 'neg' ? 'neg' : 'neutral';
          return (
            <div key={ind.label} className="macro-indicator">
              <div className="macro-indicator-header">
                <span className="macro-indicator-label">{ind.label}</span>
                <span className={`change macro-indicator-change ${ind.change.cls}`}>
                  {ind.change.text}
                </span>
              </div>
              <span className="macro-indicator-value">{ind.value}</span>
              <div className="signal-bar">
                <div
                  className={`signal-bar-fill ${barClass}`}
                  style={{ width: `${barWidth}%` }}
                />
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
