import { useState, useEffect } from 'react';

export function useTickerData(querySymbol, modelType = "ensemble") {
  const [status, setStatus] = useState('idle');
  const [momentumStatus, setMomentumStatus] = useState('idle');
  const [error, setError] = useState(null);
  const [ticker, setTicker] = useState(null);

  useEffect(() => {
    const controller = new AbortController();

    async function load() {
      const trimmed = querySymbol?.trim();
      if (!trimmed) return;

      setStatus('loading');
      setMomentumStatus('loading');
      setError(null);

      try {
        // Phase 1: Fetch fast market data
        const response = await fetch(
          `/api/ticker?symbol=${encodeURIComponent(trimmed)}&modelType=${encodeURIComponent(modelType)}&skipMomentum=true`,
          { signal: controller.signal }
        );

        if (!response.ok) {
          const text = await response.text().catch(() => '');
          throw new Error(text || `Request failed (${response.status})`);
        }

        let data = await response.json();
        
        // Format graph data for the chart component
        if (data.graphData) {
          data.graphData = data.graphData.map(pt => ({
            ...pt,
            time: new Date(pt.timestamp).toLocaleString(undefined, { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hour12: false })
          }));
        }

        setTicker(data);
        setStatus('success');

        // Phase 2: Fetch slow gRPC momentum analysis
        try {
          const momResponse = await fetch(
            `/api/ticker/momentum?symbol=${encodeURIComponent(trimmed)}&modelType=${encodeURIComponent(modelType)}`,
            { signal: controller.signal }
          );

          if (momResponse.ok) {
            const momData = await momResponse.json();
            setTicker(prev => ({
              ...prev,
              momentum: momData.current,
              momentumHistory: momData.history,
              signals: momData.signals
            }));
            setMomentumStatus('success');
          } else {
            console.warn("Failed to fetch momentum data");
            setMomentumStatus('error');
          }
        } catch (momErr) {
          if (momErr.name !== 'AbortError') {
            console.error("Momentum fetch error:", momErr);
            setMomentumStatus('error');
          }
        }

      } catch (err) {
        if (err?.name === 'AbortError') return;
        setTicker(null);
        setStatus('error');
        setMomentumStatus('idle');
        setError(err instanceof Error ? err.message : String(err));
      }
    }

    load();
    return () => controller.abort();
  }, [querySymbol, modelType]);

  return { 
    status, 
    momentumStatus,
    error, 
    ticker, 
    history: ticker?.graphData ? { histogram: ticker.graphData } : null 
  };
}
