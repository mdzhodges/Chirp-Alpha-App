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
          <div className={styles.statLabel}>52W Range</div>
          <div className={styles.statValue}>
            {ticker.yearLow == null || ticker.yearHigh == null
              ? '—'
              : `${currencyFormat.format(Number(ticker.yearLow))} – ${currencyFormat.format(Number(ticker.yearHigh))}`}
          </div>
        </div>
        <div className={styles.statItem}>
          <div className={styles.statLabel}>Volume</div>
          <div className={styles.statValue}>
            {ticker.volume == null ? '—' : compactFormat.format(Number(ticker.volume))}
          </div>
        </div>
        <div className={styles.statItem}>
          <div className={styles.statLabel}>Avg Volume</div>
          <div className={styles.statValue}>
            {ticker.avgVolume == null ? '—' : compactFormat.format(Number(ticker.avgVolume))}
          </div>
        </div>
        <div className={styles.statItem}>
          <div className={styles.statLabel}>Market Cap</div>
          <div className={styles.statValue}>
            {ticker.marketCap == null ? '—' : compactFormat.format(Number(ticker.marketCap))}
          </div>
        </div>
        <div className={styles.statItem}>
          <div className={styles.statLabel}>Enterprise Value</div>
          <div className={styles.statValue}>
            {ticker.enterpriseValue == null ? '—' : compactFormat.format(Number(ticker.enterpriseValue))}
          </div>
        </div>
        <div className={styles.statItem}>
          <div className={styles.statLabel}>Trailing P/E</div>
          <div className={styles.statValue}>
            {ticker.pe == null ? '—' : numberFormat.format(Number(ticker.pe))}
          </div>
        </div>
        <div className={styles.statItem}>
          <div className={styles.statLabel}>Forward P/E</div>
          <div className={styles.statValue}>
            {ticker.forwardPE == null ? '—' : numberFormat.format(Number(ticker.forwardPE))}
          </div>
        </div>
        <div className={styles.statItem}>
          <div className={styles.statLabel}>EPS (TTM)</div>
          <div className={styles.statValue}>
            {ticker.eps == null ? '—' : numberFormat.format(Number(ticker.eps))}
          </div>
        </div>
        <div className={styles.statItem}>
          <div className={styles.statLabel}>Dividend Yield</div>
          <div className={styles.statValue}>
            {ticker.dividendYield == null ? '—' : percentFormat.format(Number(ticker.dividendYield))}
          </div>
        </div>
        <div className={styles.statItem}>
          <div className={styles.statLabel}>Beta (5Y)</div>
          <div className={styles.statValue}>
            {ticker.beta == null ? '—' : numberFormat.format(Number(ticker.beta))}
          </div>
        </div>
        <div className={styles.statItem}>
          <div className={styles.statLabel}>Price/Book</div>
          <div className={styles.statValue}>
            {ticker.priceToBook == null ? '—' : numberFormat.format(Number(ticker.priceToBook))}
          </div>
        </div>
        <div className={styles.statItem}>
          <div className={styles.statLabel}>Profit Margin</div>
          <div className={styles.statValue}>
            {ticker.profitMargins == null ? '—' : percentFormat.format(Number(ticker.profitMargins))}
          </div>
        </div>
        <div className={styles.statItem}>
          <div className={styles.statLabel}>Chirp Momentum</div>
          <div className={`${styles.statValue} ${Number(ticker.momentum) >= 0 ? styles.tickerChangePositive : styles.tickerChangeNegative}`}>
            {ticker.momentum == null ? '—' : numberFormat.format(Number(ticker.momentum))}
          </div>
        </div>
        <div className={styles.statItem}>
          <div className={styles.statLabel}>Shares Out.</div>
          <div className={styles.statValue}>
            {ticker.sharesOutstanding == null ? '—' : compactFormat.format(Number(ticker.sharesOutstanding))}
          </div>
        </div>
      </div>
    </div>
  );
}
