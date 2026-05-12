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
import AlphaVisionChart from "../../components/AlphaVisionChart/AlphaVisionChart";

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
  const [chartMode, setChartMode] = useState("candlestick"); // 'candlestick', 'validation', or 'crystalBall'

  const { status, momentumStatus, error, ticker, history } = useTickerData(querySymbol, modelType);

  const descriptionParagraphs = useMemo(() => {
    if (!ticker?.description) return [];

    // 1. Normalize: merge stray single newlines into spaces, but keep double newlines (paragraphs)
    const normalized = ticker.description
      .replace(/\n\n+/g, "[[PARA_BREAK]]")
      .replace(/\n/g, " ")
      .replace(/\[\[PARA_BREAK\]\]/g, "\n\n")
      .trim();

    // 2. Split into initial paragraphs by double newlines
    const initialParas = normalized.split(/\n\n+/).filter(p => p.trim() !== "");
    
    // 3. Process each paragraph: if it's a huge block, break it up intelligently
    const finalParas = [];
    const ABBRS = ["Inc.", "Corp.", "Ltd.", "Co.", "U.S.", "Dr.", "Mr.", "Mrs.", "Ms.", "Jan.", "Feb.", "Mar.", "Apr.", "Jun.", "Jul.", "Aug.", "Sep.", "Oct.", "Nov.", "Dec.", "approx.", "est."];

    initialParas.forEach(para => {
      // If the paragraph is reasonably short, keep it as is
      if (para.length < 500) {
        finalParas.push(para);
        return;
      }

      // Otherwise, split into sentences without breaking on abbreviations
      const sentences = [];
      let currentSentence = "";
      const words = para.split(/\s+/);

      for (let i = 0; i < words.length; i++) {
        currentSentence += words[i] + " ";
        
        const word = words[i];
        const isLastWord = i === words.length - 1;
        const endsWithPunctuation = /[.!?]$/.test(word);
        
        // Check if it's a known abbreviation (case-insensitive for safety)
        const isAbbreviation = ABBRS.some(abbr => word.toLowerCase() === abbr.toLowerCase());
        
        // A sentence break usually requires an uppercase letter or number in the next word
        const nextWord = !isLastWord ? words[i + 1] : "";
        const nextWordStartsUpper = /^[A-Z0-9]/.test(nextWord);

        if (endsWithPunctuation && !isAbbreviation && (isLastWord || nextWordStartsUpper)) {
          sentences.push(currentSentence.trim());
          currentSentence = "";
        }
      }
      if (currentSentence.trim()) sentences.push(currentSentence.trim());

      // Group sentences into chunks of 3 for better readability
      for (let i = 0; i < sentences.length; i += 3) {
        finalParas.push(sentences.slice(i, i + 3).join(" ").trim());
      }
    });

    return finalParas;
  }, [ticker?.description]);

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
              {isUp ? "▲" : "▼"} {Math.abs(change).toFixed(2)} ({Math.abs(changePercent * 100).toFixed(2)}%)
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
          {momentumStatus === "loading" && (
            <div className={styles.signalsContainer}>
              <div className={styles.signalLoading}>
                <span className={styles.signalIcon}>⌛</span>
                Calculating Alpha Momentum & AI Signals...
              </div>
            </div>
          )}
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
              chartMode === "validation" || chartMode === "crystalBall" ? (
                <AlphaVisionChart 
                  key={`${chartMode}-${querySymbol}-${modelType}`}
                  history={history} 
                  ticker={ticker} 
                  mode={chartMode} 
                />
              ) : (
                <PriceChart 
                  key={`${chartMode}-${querySymbol}-${modelType}`} 
                  history={history} 
                  ticker={ticker} 
                  mode={chartMode}
                />
              )
            ) : (
              <div className={styles.loadingState}>
                {status === "loading" ? "Analyzing Market Cycles..." : "Search for a ticker to begin"}
              </div>
            )}

            <div className={styles.chartControls}>
              <div className={styles.modelGrid}>
                <button
                  className={`${styles.modelBtn} ${chartMode === "candlestick" ? styles.modelBtnActive : ""}`}
                  onClick={() => setChartMode("candlestick")}
                >
                  Candles
                </button>
                <button
                  className={`${styles.modelBtn} ${chartMode === "validation" ? styles.modelBtnActive : ""}`}
                  onClick={() => setChartMode("validation")}
                >
                  Validation View
                </button>
                <button
                  className={`${styles.modelBtn} ${chartMode === "crystalBall" ? styles.modelBtnActive : ""}`}
                  onClick={() => setChartMode("crystalBall")}
                >
                  Crystal Ball
                </button>
              </div>
            </div>
          </div>

          {descriptionParagraphs.length > 0 && (
            <div className={styles.descriptionCard}>
              <h3 className={styles.subTitle}>About {ticker?.symbol}</h3>
              <div className={styles.descriptionContent}>
                {descriptionParagraphs.map((para, idx) => (
                  <p key={idx} className={styles.descriptionText}>
                    {para}
                  </p>
                ))}
              </div>
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
              isLoading={momentumStatus === "loading"}
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
