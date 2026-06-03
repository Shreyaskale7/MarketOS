import './InsightsPanel.css';
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

export default function InsightsPanel() {
  const { data, loading, error } = useApi('/api/insights?limit=5', 60000);

  if (loading) {
    return (
      <div className="glass-card fade-in">
        <div className="section-title">AI Market Insights</div>
        <div className="ins-skeleton">
          <div className="skeleton" style={{ height: 120, width: '100%', marginBottom: 16 }} />
          {[1,2,3].map(i => (
            <div key={i} className="skeleton" style={{ height: 60, width: '100%', marginBottom: 10 }} />
          ))}
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="glass-card fade-in">
        <div className="section-title">AI Market Insights</div>
        <div className="empty-state">
          <div className="icon">⚠️</div>
          <div className="text">{error}</div>
        </div>
      </div>
    );
  }

  const insights = data?.insights || [];
  if (insights.length === 0) {
    return (
      <div className="glass-card fade-in">
        <div className="section-title">AI Market Insights</div>
        <div className="empty-state">
          <div className="icon">📊</div>
          <div className="text">No insights available yet. Run the pipeline to generate insights.</div>
        </div>
      </div>
    );
  }

  const [latest, ...previous] = insights;
  const latestChange = formatChange(latest.nifty_return);

  // Format insight text with line breaks
  const formatText = (text) => {
    if (!text) return '';
    return text.split('\n').filter(l => l.trim()).map((line, i) => (
      <p key={i} className="ins-line">{line}</p>
    ));
  };

  return (
    <div className="glass-card fade-in">
      <div className="section-title">AI Market Insights</div>

      {/* Latest Insight — Hero */}
      <div className="ins-hero">
        <div className="ins-hero-meta">
          <span className="ins-date">{latest.date}</span>
          <span className={`change ${latestChange.cls}`} style={{ fontSize: '0.8rem' }}>
            {latestChange.text}
          </span>
          <span className={`regime-badge ${getRegimeClass(latest.regime_label)}`}>
            {latest.regime_label || 'NEUTRAL'}
          </span>
          {latest.top_sector && (
            <span className="pill">Top: {latest.top_sector}</span>
          )}
        </div>
        <div className="ins-hero-body">
          {formatText(latest.full_insight || latest.what_text)}
        </div>
      </div>

      {/* Previous Insights */}
      {previous.length > 0 && (
        <div className="ins-history">
          <div className="ins-history-title">Previous Sessions</div>
          <div className="ins-history-grid">
            {previous.map((ins, i) => {
              const chg = formatChange(ins.nifty_return);
              return (
                <div key={i} className="ins-card">
                  <div className="ins-card-meta">
                    <span className="ins-date">{ins.date}</span>
                    <span className={`change ${chg.cls}`} style={{ fontSize: '0.7rem' }}>
                      {chg.text}
                    </span>
                    <span
                      className={`regime-badge ${getRegimeClass(ins.regime_label)}`}
                      style={{ fontSize: '0.55rem', padding: '2px 8px' }}
                    >
                      {ins.regime_label || 'NEUTRAL'}
                    </span>
                  </div>
                  <div className="ins-card-body">
                    {(ins.what_text || ins.full_insight || '').slice(0, 200)}
                    {(ins.what_text || ins.full_insight || '').length > 200 && '…'}
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}
