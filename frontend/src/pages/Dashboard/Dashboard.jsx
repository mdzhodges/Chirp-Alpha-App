import { useEffect, useMemo, useState } from 'react';
import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  Title,
  Tooltip,
  Legend,
} from 'chart.js';
import { Line } from 'react-chartjs-2';
import styles from './Dashboard.module.css';

ChartJS.register(
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  Title,
  Tooltip,
  Legend
);

export default function Dashboard() {
  const [symbol, setSymbol] = useState('AAPL');
  const [querySymbol, setQuerySymbol] = useState('AAPL');
  const [status, setStatus] = useState('idle');
  const [error, setError] = useState(null);
  const [ticker, setTicker] = useState(null);
  const [history, setHistory] = useState(null);

  const momentumNumber = 1;
  const momentumDirection = momentumNumber > 0.1 ? 'up' : momentumNumber < -0.1 ? 'down' : 'neutral';

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

        const responseHistory = await fetch(
          `/api/ticker/history?symbol=${encodeURIComponent(trimmed)}&range=1mo`,
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

        if (responseHistory.ok) {
          const dataHistory = await responseHistory.json();
          setHistory(dataHistory);
        }

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
    <div className={styles.page}>
      <div className={styles.container}>
        <div className={styles.header}>
          <div className={styles.badge}>Dashboard</div>
          <h1 className={styles.title}>Momentum Analysis</h1>
        </div>

        <div className={styles.momentumCard}>
          <div className={styles.momentumLabel}>Predicted Momentum Score</div>
          <div
            className={`${styles.momentumValue} ${
              momentumDirection === 'up'
                ? styles.momentumValueUp
                : momentumDirection === 'down'
                ? styles.momentumValueDown
                : styles.momentumValueNeutral
            }`}
          >
            {momentumNumber.toFixed(2)}
          </div>
          <span
            className={`${styles.momentumDirection} ${
              momentumDirection === 'up'
                ? styles.momentumDirectionUp
                : momentumDirection === 'down'
                ? styles.momentumDirectionDown
                : styles.momentumDirectionNeutral
            }`}
          >
            {momentumDirection === 'up' ? 'Bullish' : momentumDirection === 'down' ? 'Bearish' : 'Neutral'}
          </span>
        </div>

        <form
          onSubmit={(e) => {
            e.preventDefault();
            setQuerySymbol(symbol);
          }}
          className={styles.form}
        >
          <div className={styles.inputGroup}>
            <span className={styles.inputLabel}>Ticker Symbol</span>
            <input
              className={styles.input}
              value={symbol}
              onChange={(e) => setSymbol(e.target.value)}
              placeholder="AAPL"
              autoCapitalize="characters"
              autoCorrect="off"
              spellCheck={false}
            />
          </div>
          <button type="submit" className={styles.button} disabled={status === 'loading'}>
            {status === 'loading' ? 'Loading…' : 'Fetch'}
          </button>
        </form>

        {status === 'error' && (
          <div className={styles.error}>
            <strong>Failed to load ticker:</strong> {error}
          </div>
        )}

        {ticker && (
          <div className={styles.tickerCard}>
            <div className={styles.tickerHeader}>
              <div>
                <div className={styles.tickerSymbol}>{ticker.symbol}</div>
                <div className={styles.tickerName}>{ticker.name || ''}</div>
                <div className={styles.tickerMeta}>
                  {ticker.exchange ? `${ticker.exchange} · ` : ''}
                  {ticker.currency || 'USD'}
                  {ticker.fetchedAt ? ` · fetched ${new Date(ticker.fetchedAt).toLocaleString()}` : ''}
                </div>
              </div>
              <div>
                <div className={styles.tickerPrice}>
                  {ticker.price == null ? '—' : currencyFormat.format(Number(ticker.price))}
                </div>
                <div
                  className={`${styles.tickerChange} ${
                    Number(ticker.change) >= 0 ? styles.tickerChangePositive : styles.tickerChangeNegative
                  }`}
                >
                  {ticker.change == null ? '—' : numberFormat.format(Number(ticker.change))}
                  {ticker.changePercent == null
                    ? ''
                    : ` (${numberFormat.format(Number(ticker.changePercent))}%)`}
                </div>
              </div>
            </div>

            <div className={styles.statsGrid}>
              <div className={styles.statItem}>
                <div className={styles.statLabel}>Open</div>
                <div className={styles.statValue}>
                  {ticker.open == null ? '—' : currencyFormat.format(Number(ticker.open))}
                </div>
              </div>
              <div className={styles.statItem}>
                <div className={styles.statLabel}>Prev Close</div>
                <div className={styles.statValue}>
                  {ticker.previousClose == null ? '—' : currencyFormat.format(Number(ticker.previousClose))}
                </div>
              </div>
              <div className={styles.statItem}>
                <div className={styles.statLabel}>Day Range</div>
                <div className={styles.statValue}>
                  {ticker.dayLow == null || ticker.dayHigh == null
                    ? '—'
                    : `${currencyFormat.format(Number(ticker.dayLow))} – ${currencyFormat.format(Number(ticker.dayHigh))}`}
                </div>
              </div>
              <div className={styles.statItem}>
                <div className={styles.statLabel}>Volume</div>
                <div className={styles.statValue}>
                  {ticker.volume == null ? '—' : numberFormat.format(Number(ticker.volume))}
                </div>
              </div>
            </div>
          </div>
        )}

        {history && history.histogram && (
          <div className={styles.chartCard}>
            <div className={styles.chartHeader}>Price History (1 Month)</div>
            <div className={styles.chartContainer}>
              <Line
                data={{
                  labels: history.histogram.map(item => item.time),
                  datasets: [
                    {
                      label: 'Price',
                      data: history.histogram.map(item => item.close),
                      borderColor: 'rgb(75, 192, 192)',
                      backgroundColor: 'rgba(75, 192, 192, 0.5)',
                      tension: 0.1,
                    },
                  ],
                }}
                options={{
                  responsive: true,
                  maintainAspectRatio: false,
                  plugins: {
                    legend: {
                      display: false,
                    },
                  },
                  scales: {
                    x: {
                      ticks: {
                        maxTicksLimit: 10,
                      },
                    },
                  },
                }}
              />
            </div>
          </div>
        )}
      </div>
    </div>
  );
}