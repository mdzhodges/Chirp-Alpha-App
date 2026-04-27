import { useState, useEffect } from 'react';

export default function StockTwitsFeed({ symbol }) {
  const [messages, setMessages] = useState([]);
  const [status, setStatus] = useState('idle');
  const [error, setError] = useState(null);

  useEffect(() => {
    if (!symbol) return;
    
    const controller = new AbortController();
    
    async function fetchFeed() {
      setStatus('loading');
      setError(null);
      
      try {
        // Hitting the Spring Boot controller you set up earlier
        const response = await fetch(`/api/momentum/feed/${encodeURIComponent(symbol)}`, {
          signal: controller.signal
        });
        
        if (!response.ok) throw new Error(`Feed request failed (${response.status})`);
        
        const data = await response.json();
        // The StockTwits payload stores the posts in the 'messages' array
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
  }, [symbol]);

  // Temporary inline styles to get it working before we refactor CSS modules
  return (
    <div className="flex flex-col gap-4">
      <h2 style={{ fontSize: '1.25rem', fontWeight: 'bold', marginBottom: '1rem' }}>
        Live Momentum Feed for {symbol}
      </h2>

      {status === 'loading' && <div style={{ color: '#6b7280' }}>Loading feed...</div>}
      {status === 'error' && <div style={{ color: '#ef4444' }}>Error: {error}</div>}
      
      {status === 'success' && messages.length === 0 && (
        <div style={{ color: '#6b7280', fontStyle: 'italic' }}>No recent momentum found.</div>
      )}

      {status === 'success' && messages.map((msg) => (
        <div 
          key={msg.id} 
          style={{
            backgroundColor: '#1a1a1a', 
            padding: '1rem', 
            borderRadius: '0.75rem', 
            border: '1px solid #1f2937',
            marginBottom: '1rem'
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', marginBottom: '0.75rem' }}>
            <img 
              src={msg.user.avatar_url} 
              alt={msg.user.username} 
              style={{ width: '2.5rem', height: '2.5rem', borderRadius: '9999px', backgroundColor: '#374151' }}
            />
            <span style={{ fontWeight: '600', color: '#e5e7eb' }}>{msg.user.username}</span>
          </div>
          <p style={{ color: '#9ca3af', fontSize: '0.875rem', lineHeight: '1.5' }}>
            {msg.body}
          </p>
        </div>
      ))}
    </div>
  );
}