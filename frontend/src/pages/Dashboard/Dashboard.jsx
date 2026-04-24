import { useEffect, useMemo, useState } from 'react';

export default function Dashboard() {
  const [symbol, setSymbol] = useState('AAPL');
  const [querySymbol, setQuerySymbol] = useState('AAPL');
  const [status, setStatus] = useState('idle'); // idle | loading | success | error
  const [error, setError] = useState(null);
  const [ticker, setTicker] = useState(null);

  const currencyCode = useMemo(() => {
    const value = ticker?.currency ?? '';
    return /^[A-Z]{3}$/.test(value) ? value : 'USD';
  }, [ticker?.currency]);

  const numberFormat = useMemo(
    () =>
      new Intl.NumberFormat(undefined, {
        maximumFractionDigits: 4,
      }),
    []
  );

  const currencyFormat = useMemo(
    () =>
      new Intl.NumberFormat(undefined, {
        style: 'currency',
        currency: currencyCode,
        maximumFractionDigits: 4,
      }),
    [currencyCode]
  );

  useEffect(() => {
    const controller = new AbortController();

    async function load() {
      const trimmed = querySymbol.trim();
      if (!trimmed) return;

      setStatus('loading');
      setError(null);

      try {
        const response = await fetch(
          `/api/ticker?symbol=${encodeURIComponent(trimmed)}`,
          { signal: controller.signal }
        );

        if (!response.ok) {
          const contentType = response.headers.get('content-type') || '';
          if (contentType.includes('application/json')) {
            const data = await response.json().catch(() => null);
            const detail =
              data?.detail ||
              data?.message ||
              (data?.error && data?.status ? `${data.error} (${data.status})` : null) ||
              (typeof data === 'string' ? data : null);
            throw new Error(detail || `Request failed (${response.status})`);
          }

          const text = await response.text().catch(() => '');
          throw new Error(text || `Request failed (${response.status})`);
        }

        const data = await response.json();
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
  }, [querySymbol]);

  return (
    <div style={{ padding: '40px' }}>
      <h1>Dashboard</h1>
      <p>Real-time data will appear here.</p>

      <form
        onSubmit={(e) => {
          e.preventDefault();
          setQuerySymbol(symbol);
        }}
        style={{ display: 'flex', gap: '12px', alignItems: 'center', marginTop: '20px' }}
      >
        <label style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
          <span style={{ fontSize: '12px', opacity: 0.8 }}>Ticker symbol</span>
          <input
            value={symbol}
            onChange={(e) => setSymbol(e.target.value)}
            placeholder="AAPL"
            autoCapitalize="characters"
            autoCorrect="off"
            spellCheck={false}
            style={{ padding: '10px 12px', minWidth: '240px' }}
          />
        </label>
        <button type="submit" style={{ padding: '10px 12px' }} disabled={status === 'loading'}>
          {status === 'loading' ? 'Loading…' : 'Fetch'}
        </button>
      </form>

      {status === 'error' && (
        <div style={{ marginTop: '16px', color: '#b00020' }}>
          <strong>Failed to load ticker:</strong> {error}
        </div>
      )}

      {ticker && (
        <div
          style={{
            marginTop: '20px',
            border: '1px solid rgba(0,0,0,0.12)',
            borderRadius: '12px',
            padding: '16px',
            maxWidth: '720px',
          }}
        >
          <div style={{ display: 'flex', justifyContent: 'space-between', gap: '12px' }}>
            <div>
              <div style={{ fontSize: '18px', fontWeight: 700 }}>
                {ticker.symbol} {ticker.name ? `— ${ticker.name}` : ''}
              </div>
              <div style={{ fontSize: '12px', opacity: 0.75 }}>
                {ticker.exchange ? `${ticker.exchange} · ` : ''}
                {ticker.currency || 'USD'}
                {ticker.fetchedAt ? ` · fetched ${new Date(ticker.fetchedAt).toLocaleString()}` : ''}
              </div>
            </div>
            <div style={{ textAlign: 'right' }}>
              <div style={{ fontSize: '22px', fontWeight: 800 }}>
                {ticker.price == null ? '—' : currencyFormat.format(Number(ticker.price))}
              </div>
              <div style={{ fontSize: '12px', opacity: 0.85 }}>
                {ticker.change == null ? '—' : numberFormat.format(Number(ticker.change))}{' '}
                {ticker.changePercent == null
                  ? ''
                  : `(${numberFormat.format(Number(ticker.changePercent))}%)`}
              </div>
            </div>
          </div>

          <div
            style={{
              marginTop: '14px',
              display: 'grid',
              gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))',
              gap: '10px 16px',
              fontSize: '13px',
            }}
          >
            <div>
              <div style={{ opacity: 0.7 }}>Open</div>
              <div>{ticker.open == null ? '—' : currencyFormat.format(Number(ticker.open))}</div>
            </div>
            <div>
              <div style={{ opacity: 0.7 }}>Prev close</div>
              <div>
                {ticker.previousClose == null ? '—' : currencyFormat.format(Number(ticker.previousClose))}
              </div>
            </div>
            <div>
              <div style={{ opacity: 0.7 }}>Day range</div>
              <div>
                {ticker.dayLow == null || ticker.dayHigh == null
                  ? '—'
                  : `${currencyFormat.format(Number(ticker.dayLow))} – ${currencyFormat.format(
                      Number(ticker.dayHigh)
                    )}`}
              </div>
            </div>
            <div>
              <div style={{ opacity: 0.7 }}>Volume</div>
              <div>{ticker.volume == null ? '—' : numberFormat.format(Number(ticker.volume))}</div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
