import './SentimentPanel.css';
import useApi from '../hooks/useApi';

function getScoreClass(score) {
  if (score == null) return 'flat';
  const n = Number(score);
  if (n > 0.05) return 'positive';
  if (n < -0.05) return 'negative';
  return 'flat';
}

export default function SentimentPanel() {
  const { data, loading, error } = useApi('/api/sentiment', 60000);

  if (error) {
    return (
      <div className="glass-card sentiment-panel">
        <div className="section-title">LLM Sentiment</div>
        <div className="empty-state">
          <div className="icon">⚠</div>
          <div className="text">{error}</div>
        </div>
      </div>
    );
  }

  if (loading || !data) {
    return (
      <div className="glass-card sentiment-panel">
        <div className="section-title">LLM Sentiment</div>
        {[1, 2, 3, 4].map((i) => (
          <div key={i} className="skeleton sentiment-skeleton-card" />
        ))}
      </div>
    );
  }

  const sentiment = data.sentiment || {};
  const sectors = Object.entries(sentiment);

  if (sectors.length === 0) {
    return (
      <div className="glass-card sentiment-panel fade-in">
        <div className="section-title">LLM Sentiment</div>
        <div className="empty-state">
          <div className="icon">💬</div>
          <div className="text">No sentiment data available</div>
        </div>
      </div>
    );
  }

  return (
    <div className="glass-card sentiment-panel fade-in">
      <div className="section-title">LLM Sentiment</div>
      <div className="sentiment-grid">
        {sectors.map(([sector, info]) => {
          const score = info?.score;
          const narrative = info?.narrative || '—';
          const scoreClass = getScoreClass(score);

          return (
            <div key={sector} className="sentiment-card">
              <div className={`sentiment-score ${scoreClass}`}>
                {score != null ? (Number(score) > 0 ? '+' : '') + Number(score).toFixed(2) : '—'}
              </div>
              <div className="sentiment-meta">
                <div className="sentiment-sector-name">{sector}</div>
                <div className="sentiment-narrative">{narrative}</div>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
