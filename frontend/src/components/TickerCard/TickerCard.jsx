import { useMemo } from 'react';
import styles from './TickerCards.module.css';

/**
 * Renders a single stat row.
 * Pulled out so the markup stays readable when grouped into sections.
 */
function Stat({ label, value }) {
  return (
    <div className={styles.statItem}>
      <div className={styles.statLabel}>{label}</div>
      <div className={styles.statValue}>{value}</div>
    </div>
  );
}

export default function TickerCard({ ticker }) {
  const currencyCode = useMemo(() => {
    const value = ticker?.currency ?? '';
    return /^[A-Z]{3}$/.test(value) ? value : 'USD';
  }, [ticker?.currency]);

  const numberFormat = useMemo(
    () => new Intl.NumberFormat(undefined, { maximumFractionDigits: 4 }),
    []
  );

  const percentFormat = useMemo(
    () =>
      new Intl.NumberFormat(undefined, {
        style: 'percent',
        minimumFractionDigits: 2,
        maximumFractionDigits: 2,
      }),
    []
  );

  const currencyFormat = useMemo(
    () =>
      new Intl.NumberFormat(undefined, {
        style: 'currency',
        currency: currencyCode,
        maximumFractionDigits: 2,
      }),
    [currencyCode]
  );

  const compactFormat = useMemo(
    () =>
      new Intl.NumberFormat(undefined, {
        notation: 'compact',
        compactDisplay: 'short',
        maximumFractionDigits: 2,
      }),
    []
  );

  if (!ticker) return null;

  // Tiny helpers so JSX below stays clean
  const cur = (v) => (v == null ? '—' : currencyFormat.format(Number(v)));
  const num = (v) => (v == null ? '—' : numberFormat.format(Number(v)));
  const pct = (v) => (v == null ? '—' : percentFormat.format(Number(v)));
  const big = (v) => (v == null ? '—' : compactFormat.format(Number(v)));
  const range = (lo, hi) =>
    lo == null || hi == null ? '—' : `${cur(lo)} – ${cur(hi)}`;

  return (
    <div className={styles.tickerCard}>
      {/* TRADING */}
      <section className={styles.section}>
        <h3 className={styles.sectionTitle}>Trading</h3>
        <div className={styles.statsGrid}>
          <Stat label="Open" value={cur(ticker.open)} />
          <Stat label="Prev Close" value={cur(ticker.previousClose)} />
          <Stat label="Day Range" value={range(ticker.dayLow, ticker.dayHigh)} />
          <Stat label="52W Range" value={range(ticker.yearLow, ticker.yearHigh)} />
          <Stat label="Volume" value={big(ticker.volume)} />
          <Stat label="Avg Volume" value={big(ticker.avgVolume)} />
        </div>
      </section>

      {/* VALUATION */}
      <section className={styles.section}>
        <h3 className={styles.sectionTitle}>Valuation</h3>
        <div className={styles.statsGrid}>
          <Stat label="Market Cap" value={big(ticker.marketCap)} />
          <Stat label="Enterprise Value" value={big(ticker.enterpriseValue)} />
          <Stat label="Trailing P/E" value={num(ticker.pe)} />
          <Stat label="Forward P/E" value={num(ticker.forwardPE)} />
          <Stat label="Price/Book" value={num(ticker.priceToBook)} />
          <Stat label="Beta (5Y)" value={num(ticker.beta)} />
        </div>
      </section>

      {/* FUNDAMENTALS */}
      <section className={styles.section}>
        <h3 className={styles.sectionTitle}>Fundamentals</h3>
        <div className={styles.statsGrid}>
          <Stat label="EPS (TTM)" value={num(ticker.eps)} />
          <Stat label="Dividend Yield" value={pct(ticker.dividendYield)} />
          <Stat label="Profit Margin" value={pct(ticker.profitMargins)} />
          <Stat label="Shares Out." value={big(ticker.sharesOutstanding)} />
        </div>
      </section>
    </div>
  );
}