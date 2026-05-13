import { useState, useEffect } from 'react';
import styles from './NewsFeed.module.css';

export default function NewsFeed({ symbol, limit = 5 }) {
  const [news, setNews] = useState([]);
  const [status, setStatus] = useState('idle');
  const [error, setError] = useState(null);
  const [visibleCount, setVisibleCount] = useState(limit);

  useEffect(() => {
    if (!symbol) return;

    const controller = new AbortController();

    async function fetchNews() {
      setStatus('loading');
      setError(null);
      setVisibleCount(limit);

      try {
        const response = await fetch(`/api/momentum/feed/${encodeURIComponent(symbol)}`, {
          signal: controller.signal
        });

        if (!response.ok) throw new Error(`News request failed (${response.status})`);

        const data = await response.json();

        // Finnhub returns an array directly
        setNews(data || []);
        setStatus('success');
      } catch (err) {
        if (err.name === 'AbortError') return;
        setStatus('error');
        setError(err.message);
      }
    }

    fetchNews();
    return () => controller.abort();
  }, [symbol, limit]);

  // Helper function to format the unix timestamp
  const formatTime = (timestamp) => {
    if (!timestamp) return '';
    const date = new Date(timestamp * 1000);
    return date.toLocaleString(undefined, { 
      month: 'short', 
      day: 'numeric', 
      hour: 'numeric', 
      minute: '2-digit' 
    });
  };

  const showMore = () => {
    setVisibleCount(prev => prev + limit);
  };

  return (
    <div className={styles.feedContainer}>
      <h2 className={styles.header}>
        Latest News for {symbol}
      </h2>

      {status === 'loading' && <div className={styles.statusMessage}>Loading news...</div>}
      {status === 'error' && <div className={styles.errorMessage}>Error: {error}</div>}

      {status === 'success' && news.length === 0 && (
        <div className={styles.statusMessage}>No recent news found for {symbol}.</div>
      )}

      {status === 'success' && news.slice(0, visibleCount).map((item) => (
        <div key={item.id} className={styles.messageCard}>
          <div className={styles.userInfo}>
            <div className={styles.userMeta}>
              {item.image && (
                <img 
                  src={item.image} 
                  alt={item.source} 
                  className={styles.avatar}
                />
              )}
              <div className={styles.userDetails}>
                <span className={styles.username}>{item.source}</span>
              </div>
            </div>
            <span className={styles.timestamp}>{formatTime(item.datetime)}</span>
          </div>
          <div className={styles.newsContent}>
            <h3 className={styles.headline}>
              <a href={item.url} target="_blank" rel="noopener noreferrer">
                {item.headline}
              </a>
            </h3>
            <p className={styles.messageBody}>
              {item.summary}
            </p>
          </div>
        </div>
      ))}

      {status === 'success' && visibleCount < news.length && (
        <button className={styles.loadMore} onClick={showMore}>
          Load More News
        </button>
      )}
    </div>
  );
}
