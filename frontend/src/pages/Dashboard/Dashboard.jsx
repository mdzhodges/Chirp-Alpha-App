import { useMemo, useState } from 'react';
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

import { useTickerData } from '../../hooks/UseTickerData';
import StockTwitsFeed from '../../components/StockTwitsFeed/StockTwitsFeed';
import TickerCard from '../../components/TickerCard/TickerCard';
import MomentumCard from '../../components/MomentumCard/MomentumCard';
import SearchForm from '../../components/SearchForm/SearchForm';
import PriceChart from '../../components/PriceChart/PriceChart';

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

const TABS = [
  { id: 'overview', label: 'Overview' },
  { id: 'chart', label: 'Chart' },
  { id: 'feed', label: 'Feed' },
];

export default function Dashboard() {
  const [symbol, setSymbol] = useState('AAPL');
  const [querySymbol, setQuerySymbol] = useState('AAPL');
  const [activeTab, setActiveTab] = useState('overview');

  const { status, error, ticker, history } = useTickerData(querySymbol);

  const momentumNumber = ticker?.momentum ?? 0;
  const momentumDirection = useMemo(() => {
    if (momentumNumber > 0.1) return 'up';
    if (momentumNumber < -0.1) return 'down';
    return 'neutral';
  }, [momentumNumber]);

  const change = Number(ticker?.change ?? 0);
  const changePercent = Number(ticker?.changePercent ?? 0);
  const isUp = change >= 0;

  const priceFormatted = useMemo(() => {
    if (ticker?.price == null) return '—';
    return new Intl.NumberFormat(undefined, {
      style: 'currency',
      currency: /^[A-Z]{3}$/.test(ticker.currency || '') ? ticker.currency : 'USD',
      maximumFractionDigits: 2,
    }).format(Number(ticker.price));
  }, [ticker?.price, ticker?.currency]);

  return (
    <div className={styles.page}>
      {/* HERO STRIP: symbol, price, change. The thing you look at first. */}
      <header className={styles.hero}>
        <div className={styles.heroLeft}>
          <div className={styles.heroSymbol}>{ticker?.symbol || querySymbol}</div>
          <div className={styles.heroName}>{ticker?.name || ''}</div>
          <div className={styles.heroMeta}>
            {ticker?.exchange ? `${ticker.exchange} · ` : ''}
            {ticker?.currency || 'USD'}
            {ticker?.fetchedAt && (
              <span className={styles.heroDot}>
                · updated {new Date(ticker.fetchedAt).toLocaleTimeString()}
              </span>
            )}
          </div>
        </div>

        <div className={styles.heroRight}>
          <div className={styles.heroPrice}>{priceFormatted}</div>
          <div
            className={`${styles.heroChange} ${
              isUp ? styles.heroChangeUp : styles.heroChangeDown
            }`}
          >
            <span className={styles.heroChangeArrow}>{isUp ? '▲' : '▼'}</span>
            {ticker?.change == null ? '—' : Math.abs(change).toFixed(2)}
            {ticker?.changePercent != null && (
              <span className={styles.heroChangePct}>
                ({Math.abs(changePercent).toFixed(2)}%)
              </span>
            )}
          </div>
        </div>
      </header>

      {/* SEARCH + TABS row */}
      <div className={styles.controls}>
        <SearchForm
          symbol={symbol}
          setSymbol={setSymbol}
          setQuerySymbol={setQuerySymbol}
          status={status}
        />

        <nav className={styles.tabBar} role="tablist">
          {TABS.map((tab) => (
            <button
              key={tab.id}
              role="tab"
              aria-selected={activeTab === tab.id}
              className={`${styles.tab} ${activeTab === tab.id ? styles.tabActive : ''}`}
              onClick={() => setActiveTab(tab.id)}
            >
              {tab.label}
            </button>
          ))}
        </nav>
      </div>

      {status === 'error' && (
        <div className={styles.error}>
          <strong>Failed to load ticker:</strong> {error}
        </div>
      )}

      {/* TAB PANELS */}
      <main className={styles.panel}>
        {activeTab === 'overview' && (
          <div className={styles.overviewGrid}>
            <section className={styles.overviewMain}>
              <MomentumCard
                momentumNumber={momentumNumber}
                momentumDirection={momentumDirection}
              />
              {history && (
                <div className={styles.chartWrap}>
                  <PriceChart history={history} ticker={ticker} />
                </div>
              )}
            </section>

            <aside className={styles.overviewSide}>
              {ticker && <TickerCard ticker={ticker} />}
            </aside>
          </div>
        )}

        {activeTab === 'chart' && (
          <div className={styles.chartFull}>
            {history ? (
              <PriceChart history={history} ticker={ticker} />
            ) : (
              <div className={styles.empty}>No price history available.</div>
            )}
          </div>
        )}

        {activeTab === 'feed' && (
          <div className={styles.feedFull}>
            <StockTwitsFeed symbol={querySymbol} />
          </div>
        )}
      </main>
    </div>
  );
}