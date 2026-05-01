import { useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  Title,
  Tooltip,
  Legend,
} from "chart.js";

import { useTickerData } from "../../hooks/UseTickerData";
import StockTwitsFeed from "../../components/StockTwitsFeed/StockTwitsFeed";
import TickerCard from "../../components/TickerCard/TickerCard";
import MomentumCard from "../../components/MomentumCard/MomentumCard";
import PriceChart from "../../components/PriceChart/PriceChart";

import styles from "./Dashboard.module.css";

ChartJS.register(
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  Title,
  Tooltip,
  Legend
);

const MODEL_OPTIONS = [
  { id: "balanced", label: "Balanced" },
  { id: "bullish", label: "Bullish" },
  { id: "bearish", label: "Bearish" },
  { id: "ensemble", label: "Consensus" },
];

export default function Dashboard() {
  const [searchParams] = useSearchParams();
  const querySymbol = searchParams.get("s") || "AAPL";
  const [modelType, setModelType] = useState("balanced");

  const { status, error, ticker, history } = useTickerData(querySymbol, modelType);

  const momentumNumber = ticker?.momentum ?? 0;
  const momentumDirection = useMemo(() => {
    if (momentumNumber > 0.1) return "up";
    if (momentumNumber < -0.1) return "down";
    return "neutral";
  }, [momentumNumber]);

  const change = Number(ticker?.change ?? 0);
  const changePercent = Number(ticker?.changePercent ?? 0);
  const isUp = change >= 0;

  const priceFormatted = useMemo(() => {
    if (ticker?.price == null) return "—";
    return new Intl.NumberFormat(undefined, {
      style: "currency",
      currency: /^[A-Z]{3}$/.test(ticker.currency || "") ? ticker.currency : "USD",
      maximumFractionDigits: 2,
    }).format(Number(ticker.price));
  }, [ticker?.price, ticker?.currency]);

  return (
    <div className={styles.container}>
      {/* 1. Dashboard Top Bar: Info + Tools */}
      <header className={styles.topBar}>
        <div className={styles.tickerHeader}>
          
          <div className={styles.logoWrap}>
            {ticker?.logoUrl ? (
              <img 
                src={ticker.logoUrl} 
                alt={`${ticker.symbol} logo`} 
                className={styles.logo}
                onError={(e) => e.target.style.display = "none"}
              />
            ) : (
              <div className={styles.logoPlaceholder}>{ticker?.symbol?.charAt(0)}</div>
            )}
          </div>
          <div className={styles.tickerIdentify}>
            <h1 className={styles.symbol}>{ticker?.symbol || querySymbol}</h1>
            <span className={styles.name}>{ticker?.name || ""}</span>
          </div>
          <div className={styles.priceRow}>
            <div className={styles.price}>{priceFormatted}</div>
            <div className={`${styles.change} ${isUp ? styles.changeUp : styles.changeDown}`}>
              {isUp ? "▲" : "▼"} {Math.abs(change).toFixed(2)} ({Math.abs(changePercent).toFixed(2)}%)
            </div>
          </div>
        </div>

        <div className={styles.toolbar}>
          <div className={styles.modelSelector}>
            <span className={styles.selectorLabel}>AI Persona</span>
            <div className={styles.modelGrid}>
              {MODEL_OPTIONS.map((opt) => (
                <button
                  key={opt.id}
                  className={`${styles.modelBtn} ${modelType === opt.id ? styles.modelBtnActive : ""}`}
                  onClick={() => setModelType(opt.id)}
                >
                  {opt.label}
                </button>
              ))}
            </div>
          </div>
        </div>
      </header>

      {status === "error" && (
        <div className={styles.errorBanner}>
          <strong>Error:</strong> {error}
        </div>
      )}

      {/* 2. Main Content Grid */}
      <div className={styles.dashboardGrid}>
        {/* Left: Huge Chart */}
        <section className={styles.chartSection}>
          {ticker?.signals && ticker.signals.length > 0 && (
            <div className={styles.signalsContainer}>
              {ticker.signals.map((sig, idx) => (
                <div key={idx} className={styles.signalAlert}>
                  <span className={styles.signalIcon}>⚡</span>
                  {sig}
                </div>
              ))}
            </div>
          )}
          <div className={styles.card}>
            {history ? (
              <PriceChart history={history} ticker={ticker} />
            ) : (
              <div className={styles.loadingState}>
                {status === "loading" ? "Analyzing Market Cycles..." : "Search for a ticker to begin"}
              </div>
            )}
          </div>

          {ticker?.description && (
            <div className={styles.descriptionCard}>
              <h3 className={styles.subTitle}>About {ticker.symbol}</h3>
              <p className={styles.descriptionText}>{ticker.description}</p>
            </div>
          )}
          
          {/* Social Feed at the bottom of chart on desktop */}
          <div className={styles.feedSection}>
             <h3 className={styles.subTitle}>Social Sentiment & Pulse</h3>
             <StockTwitsFeed symbol={querySymbol} />
          </div>
        </section>

        {/* Right: AI Insights & Fundamentals */}
        <aside className={styles.sidebar}>
          <div className={styles.stickyCol}>
            <MomentumCard
              momentumNumber={momentumNumber}
              momentumDirection={momentumDirection}
              modelStats={ticker?.modelStats}
            />
            
            <div className={styles.statsCard}>
              <h3 className={styles.subTitle}>Market Data</h3>
              {ticker && <TickerCard ticker={ticker} />}
            </div>
          </div>
        </aside>
      </div>
    </div>
  );
}
