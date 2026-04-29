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
import MomentumCard from '../../components/MomentumCard/MomentumCard';
import SearchForm from '../../components/SearchForm/SearchForm';
import FeedToggleButton from '../../components/FeedToggleButton/FeedToggleButton';
import PriceChart from '../../components/PriceChart/PriceChart';

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
  const [isFeedOpen, setIsFeedOpen] = useState(true); // tweets show when true

  const { status, error, ticker, history } = useTickerData(querySymbol);

  const momentumNumber = ticker?.momentum ?? 0;
  const momentumDirection = momentumNumber > 0.1 ? 'up' : momentumNumber < -0.1 ? 'down' : 'neutral';

  return (
    <div className={styles.splitScreenContainer}>
      
      {/* --- LEFT COLUMN --- */}
      <div className={`${styles.leftColumn} ${isFeedOpen ? styles.leftColumnSplit : styles.leftColumnFull}`}>
        <div className={styles.container}>
          
          <div style={{ marginBottom: '2rem' }}>
            <div className={styles.header}>
              <div className={styles.badge}>Dashboard</div>
              <h1 className={styles.title} style={{ margin: 0 }}>Momentum Analysis</h1>
            </div>
          </div>

          <MomentumCard 
            momentumNumber={momentumNumber} 
            momentumDirection={momentumDirection} 
            styles={styles} 
          />

          <SearchForm 
            symbol={symbol}
            setSymbol={setSymbol}
            setQuerySymbol={setQuerySymbol}
            status={status}
            styles={styles}
          />

          {status === 'error' && (
            <div className={styles.error}>
              <strong>Failed to load ticker:</strong> {error}
            </div>
          )}

          {ticker && <TickerCard ticker={ticker} styles={styles} />}
          {history && <PriceChart history={history} ticker={ticker} styles={styles} />}

        </div>
      </div>
      {/* --- END LEFT COLUMN --- */}

      {/* --- RIGHT COLUMN --- */}
      <div className={`${styles.rightColumn} ${isFeedOpen ? styles.rightColumnOpen : styles.rightColumnClosed}`}>
        <div className={styles.feedInnerWrapper}>
          <StockTwitsFeed symbol={querySymbol} />
        </div>
      </div>

      {/* --- THE FLOATING TAB --- */}
      <FeedToggleButton 
        isOpen={isFeedOpen} 
        onToggle={() => setIsFeedOpen(!isFeedOpen)} 
      />

    </div>
  );
}