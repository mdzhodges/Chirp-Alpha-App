import { useMemo } from 'react';
import styles from './TickerCards.module.css';

export default function TickerCard({ ticker }) {
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

  if (!ticker) return null;

  return (
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
  );
}