import './TopBar.css';
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

export default function TopBar() {
  const { data: status, loading: statusLoading } = useApi('/api/status', 15000);
  const { data: macro, loading: macroLoading } = useApi('/api/macro', 30000);

  const loading = statusLoading || macroLoading;

  const nifty = status?.nifty || {};
  const vix = macro?.macro?.india_vix || {};
  const usdinr = macro?.macro?.usdinr || {};
  const fii = macro?.macro?.fii_flows || {};

  const niftyChange = formatChange(nifty.return_pct);
  const vixChange = formatChange(vix.change_pct);
  const usdinrChange = formatChange(usdinr.change_pct);

  return (
    <div className="top-bar">
      {/* Left: Logo */}
      <div className="top-bar-left">
        <div className="logo">
          <div className="logo-icon">M</div>
          <div>
            <div className="logo-text">MarketOS</div>
            <div className="logo-sub">Quantitative Intelligence</div>
          </div>
        </div>
      </div>

      {/* Center: Live Metrics */}
      <div className="top-bar-center">
        {loading ? (
          <>
            {[1, 2, 3, 4].map((i) => (
              <div key={i} className="top-bar-metric">
                <div className="skeleton skeleton-metric" />
                <div className="skeleton skeleton-metric" style={{ width: 40, marginTop: 3 }} />
              </div>
            ))}
          </>
        ) : (
          <>
            <div className="top-bar-metric">
              <span className="label">NIFTY 50</span>
              <div className="top-bar-metric-group">
                <span className="value">{formatNum(nifty.level, 0)}</span>
                <span className={`change ${niftyChange.cls}`}>{niftyChange.text}</span>
              </div>
            </div>

            <div className="top-bar-divider" />

            <div className="top-bar-metric">
              <span className="label">India VIX</span>
              <div className="top-bar-metric-group">
                <span className="value">{formatNum(vix.current)}</span>
                <span className={`change ${vixChange.cls}`}>{vixChange.text}</span>
              </div>
            </div>

            <div className="top-bar-divider" />

            <div className="top-bar-metric">
              <span className="label">USD/INR</span>
              <div className="top-bar-metric-group">
                <span className="value">{formatNum(usdinr.current)}</span>
                <span className={`change ${usdinrChange.cls}`}>{usdinrChange.text}</span>
              </div>
            </div>

            <div className="top-bar-divider" />

            <div className="top-bar-metric">
              <span className="label">FII Flows</span>
              <div className="top-bar-metric-group">
                <span className="value">
                  {fii.estimated_crore != null
                    ? `₹${formatNum(fii.estimated_crore, 0)}Cr`
                    : '—'}
                </span>
                {fii.signal && (
                  <span
                    className={`change ${
                      fii.signal === 'BUYING' ? 'pos' : fii.signal === 'SELLING' ? 'neg' : 'flat'
                    }`}
                  >
                    {fii.signal}
                  </span>
                )}
              </div>
            </div>
          </>
        )}
      </div>

      {/* Right: Regime + Status */}
      <div className="top-bar-right">
        {!loading && (
          <>
            <span className={`regime-badge ${getRegimeClass(status?.regime_label)}`}>
              {status?.regime_label || 'N/A'}
            </span>
            <div className="top-bar-status">
              <div className="live-dot" />
              <span className="pipeline-date">{status?.pipeline_date || '—'}</span>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
