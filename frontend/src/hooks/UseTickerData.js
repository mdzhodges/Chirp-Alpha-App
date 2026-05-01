import { useState, useEffect } from 'react';

export function useTickerData(querySymbol, modelType = "balanced") {
  const [status, setStatus] = useState('idle');
  const [error, setError] = useState(null);
  const [ticker, setTicker] = useState(null);

  useEffect(() => {
    const controller = new AbortController();

    async function load() {
      const trimmed = querySymbol?.trim();
      if (!trimmed) return;

      setStatus('loading');
      setError(null);

      try {
        const response = await fetch(
          `/api/ticker?symbol=${encodeURIComponent(trimmed)}&modelType=${encodeURIComponent(modelType)}`,
          { signal: controller.signal }
        );

        if (!response.ok) {
          const text = await response.text().catch(() => '');
          throw new Error(text || `Request failed (${response.status})`);
        }

        const data = await response.json();
        
        // Format graph data for the chart component
        if (data.graphData) {
          data.graphData = data.graphData.map(pt => ({
            ...pt,
            time: new Date(pt.timestamp).toLocaleString(undefined, { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hour12: false })
          }));
        }

        setTicker(data);
        setStatus('success');

      } catch (err) {
        if (err?.name === 'AbortError') return;
        setTicker(null);
        setStatus('error');
        setError(err instanceof Error ? err.message : String(err));
      }
    }

    load();
    return () => controller.abort();
  }, [querySymbol, modelType]);

  return { status, error, ticker, history: ticker?.graphData ? { histogram: ticker.graphData } : null };
}
