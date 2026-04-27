// src/hooks/useTickerData.js
import { useState, useEffect } from 'react';

export function useTickerData(querySymbol) {
  const [status, setStatus] = useState('idle');
  const [error, setError] = useState(null);
  const [ticker, setTicker] = useState(null);
  const [history, setHistory] = useState(null);

  useEffect(() => {
    const controller = new AbortController();

    async function load() {
      const trimmed = querySymbol?.trim();
      if (!trimmed) return;

      setStatus('loading');
      setError(null);

      try {
        // --- TEMPORARY MOCK DATA TO BYPASS RATE LIMITS ---
        
        // Simulate a tiny network delay so you can still see loading states
        await new Promise(resolve => setTimeout(resolve, 600)); 

        // 1. Mock Ticker Data
        const mockTicker = {
          symbol: trimmed.toUpperCase(),
          name: "Mocked Company Inc.",
          exchange: "NASDAQ",
          currency: "USD",
          price: 271.06,
          change: -2.37,
          changePercent: -0.8668,
          open: 272.755,
          previousClose: 273.43,
          dayLow: 269.65,
          dayHigh: 273.06,
          volume: 38157110,
          fetchedAt: new Date().toISOString()
        };

        // 2. Mock History Data (so your Chart.js doesn't break)
        const mockHistory = {
          histogram: [
            { time: '04-20', close: 265.10 },
            { time: '04-21', close: 268.20 },
            { time: '04-22', close: 270.50 },
            { time: '04-23', close: 269.80 },
            { time: '04-24', close: 273.43 },
            { time: '04-27', close: 271.06 },
          ]
        };

        // If the component unmounted while "fetching", bail out
        if (controller.signal.aborted) return;

        setTicker(mockTicker);
        setHistory(mockHistory);
        setStatus('success');

        /* ================================================================
        TO REVERT BACK TO LIVE DATA LATER, DELETE THE MOCK CODE ABOVE 
        AND UNCOMMENT THE REAL FETCH CALLS BELOW:
        ================================================================
        
        const response = await fetch(
          `/api/ticker?symbol=${encodeURIComponent(trimmed)}`,
          { signal: controller.signal }
        );

        const responseHistory = await fetch(
          `/api/ticker/history?symbol=${encodeURIComponent(trimmed)}&range=1mo`,
          { signal: controller.signal }
        );

        if (!response.ok) {
          const text = await response.text().catch(() => '');
          throw new Error(text || `Request failed (${response.status})`);
        }

        const data = await response.json();
        setTicker(data);

        if (responseHistory.ok) {
          const dataHistory = await responseHistory.json();
          setHistory(dataHistory);
        }

        setStatus('success');
        */

      } catch (err) {
        if (err?.name === 'AbortError') return;
        setTicker(null);
        setStatus('error');
        setError(err instanceof Error ? err.message : String(err));
      }
    }

    load();
    return () => controller.abort();
  }, [querySymbol]);

  return { status, error, ticker, history };
}