import { useEffect, useMemo, useState } from 'react';
import { useTickerData } from '../../hooks/UseTickerData';
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
import StockTwitsFeed from '../../components/StockTwitsFeed/StockTwitsFeed'
import TickerCard from '../../components/TickerCard/TickerCard';

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
  const { status, error, ticker, history } = useTickerData(querySymbol);

  const momentumNumber = 1;
  const momentumDirection = momentumNumber > 0.1 ? 'up' : momentumNumber < -0.1 ? 'down' : 'neutral';

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

        {ticker && <TickerCard ticker={ticker} styles={styles} />}

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