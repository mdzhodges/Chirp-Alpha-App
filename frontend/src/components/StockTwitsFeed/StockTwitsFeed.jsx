import { useState, useEffect } from 'react';
import styles from './StockTwitsFeed.module.css';

export default function StockTwitsFeed({ symbol, limit = 5 }) {
  const [messages, setMessages] = useState([]);
  const [status, setStatus] = useState('idle');
  const [error, setError] = useState(null);
  const [visibleCount, setVisibleCount] = useState(limit);

  useEffect(() => {
    if (!symbol) return;
    
    const controller = new AbortController();
    
    async function fetchFeed() {
      setStatus('loading');
      setError(null);
      setVisibleCount(limit);
      
      try {
        const response = await fetch(`/api/momentum/feed/${encodeURIComponent(symbol)}`, {
          signal: controller.signal
        });
        
        if (!response.ok) throw new Error(`Feed request failed (${response.status})`);
        
        const data = await response.json();
        setMessages(data.messages || []);
        setStatus('success');
      } catch (err) {
        if (err.name === 'AbortError') return;
        setStatus('error');
        setError(err.message);
      }
    }

    fetchFeed();
    return () => controller.abort();
  }, [symbol, limit]);

  // Helper function to format the raw API timestamp nicely
  const formatTime = (dateString) => {
    if (!dateString) return '';
    const date = new Date(dateString);
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
        Live Momentum Feed for {symbol}
      </h2>

      {status === 'loading' && <div className={styles.statusMessage}>Loading feed...</div>}
      {status === 'error' && <div className={styles.errorMessage}>Error: {error}</div>}
      
      {status === 'success' && messages.length === 0 && (
        <div className={styles.statusMessage}>No recent momentum found.</div>
      )}

      {status === 'success' && messages.slice(0, visibleCount).map((msg) => (
        <div key={msg.id} className={styles.messageCard}>
          <div className={styles.userInfo}>
            {/* Wrapper to group avatar and username together */}
            <div className={styles.userMeta}>
              <img 
                src={msg.user.avatar_url} 
                alt={msg.user.username} 
                className={styles.avatar}
              />
              <span className={styles.username}>{msg.user.username}</span>
            </div>
            {/* The newly formatted timestamp pushed to the right side */}
            <span className={styles.timestamp}>{formatTime(msg.created_at)}</span>
          </div>
          <p className={styles.messageBody}>
            {msg.body}
          </p>
        </div>
      ))}

      {status === 'success' && visibleCount < messages.length && (
        <button className={styles.loadMore} onClick={showMore}>
          Load More Pulse
        </button>
      )}
    </div>
  );
}