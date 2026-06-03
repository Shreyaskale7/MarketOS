import './BacktestPanel.css';
import useApi from '../hooks/useApi';

function pct(val, decimals = 2, showSign = false) {
  if (val == null) return '—';
  const n = Number(val);
  const prefix = showSign && n > 0 ? '+' : '';
  return `${prefix}${n.toFixed(decimals)}%`;
}

function MetricRow({ label, value, isPercent = true, colorize = false }) {
  const n = Number(value);
  let cls = '';
  if (colorize && !isNaN(n)) {
    cls = n > 0 ? 'pos' : n < 0 ? 'neg' : '';
  }
  return (
    <div className="bt-metric-row">
      <span className="bt-metric-label">{label}</span>
      <span className={`bt-metric-value ${cls}`}>
        {isPercent ? pct(value, 2, colorize) : (value != null ? Number(value).toFixed(3) : '—')}
      </span>
    </div>
  );
}

function BacktestColumn({ title, data, accent }) {
  if (!data) return null;
  return (
    <div className={`bt-column bt-column-${accent}`}>
      <div className="bt-column-header">{title}</div>
      <div className="bt-column-body">
        <MetricRow label="Annual Return" value={data.portfolio_annualised_return} colorize />
        <MetricRow label="Benchmark Return" value={data.benchmark_annualised_return} colorize />
        <MetricRow label="Net Alpha" value={data.net_alpha} colorize />
        <MetricRow label="Max Drawdown" value={data.max_drawdown} colorize />
        <MetricRow label="Sharpe Ratio" value={data.sharpe_ratio} isPercent={false} />
        <MetricRow label="Win Rate" value={data.win_rate} />
      </div>
    </div>
  );
}

export default function BacktestPanel() {
  const { data, loading, error } = useApi('/api/performance', 60000);

  if (loading) {
    return (
      <div className="glass-card fade-in">
        <div className="section-title">Backtest Performance</div>
        <div className="bt-grid">
          {[1, 2].map(i => (
            <div key={i} className="bt-column">
              <div className="skeleton" style={{ height: 20, width: '60%', marginBottom: 16 }} />
              {[1,2,3,4,5].map(j => (
                <div key={j} className="skeleton" style={{ height: 16, width: '100%', marginBottom: 10 }} />
              ))}
            </div>
          ))}
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="glass-card fade-in">
        <div className="section-title">Backtest Performance</div>
        <div className="empty-state">
          <div className="icon">⚠️</div>
          <div className="text">{error}</div>
        </div>
      </div>
    );
  }

  const bt3 = data?.backtest_3yr;
  const bt5 = data?.backtest_5yr;
  const bench = data?.nifty_benchmark;

  return (
    <div className="glass-card fade-in">
      <div className="section-title">Backtest Performance</div>

      <div className="bt-grid">
        <BacktestColumn title="3-Year Backtest" data={bt3} accent="cyan" />
        <BacktestColumn title="5-Year Backtest" data={bt5} accent="purple" />
      </div>

      {bench && (
        <div className="bt-benchmark">
          <div className="bt-bench-title">NIFTY 50 Benchmark (Reference)</div>
          <div className="bt-bench-metrics">
            <div className="bt-bench-item">
              <span className="bt-metric-label">Annual Return</span>
              <span className={`bt-metric-value ${Number(bench.annualised_return) >= 0 ? 'pos' : 'neg'}`}>
                {pct(bench.annualised_return, 2, true)}
              </span>
            </div>
            <div className="bt-bench-item">
              <span className="bt-metric-label">Sharpe</span>
              <span className="bt-metric-value">{bench.sharpe_ratio != null ? Number(bench.sharpe_ratio).toFixed(3) : '—'}</span>
            </div>
            <div className="bt-bench-item">
              <span className="bt-metric-label">Max Drawdown</span>
              <span className="bt-metric-value neg">{pct(bench.max_drawdown, 2)}</span>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
