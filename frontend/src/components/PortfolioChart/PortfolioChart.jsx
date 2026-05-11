import React from 'react';
import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  Title,
  Tooltip,
  Legend,
  Filler
} from 'chart.js';
import { Line } from 'react-chartjs-2';
import styles from './PortfolioChart.module.css';

ChartJS.register(
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  Title,
  Tooltip,
  Legend,
  Filler
);

export default function PortfolioChart({ title, data }) {
  if (!data || !data.history) {
    return (
      <div className={styles.chartCard}>
        <div className={styles.title}>{title}</div>
        <div className={styles.equity}>N/A</div>
        <p style={{ color: 'var(--text-muted)', fontSize: '12px' }}>API Keys not configured or service unavailable.</p>
      </div>
    );
  }

  const { equity, buyingPower, history, positions } = data;
  
  // 1. Initial filter: every 6th point for 90-minute intervals (Alpaca 15min * 6 = 90min)
  let rawEquity = history?.equity || [];
  let rawTimestamps = history?.timestamp || [];
  
  const filteredEquity = rawEquity.filter((_, i) => i % 6 === 0);
  const filteredTimestamps = rawTimestamps.filter((_, i) => i % 6 === 0);

  // 2. Secondary filter: Remove leading zeros
  const firstNonZeroIdx = filteredEquity.findIndex(e => e > 0);
  const validEquity = firstNonZeroIdx !== -1 ? filteredEquity.slice(firstNonZeroIdx) : [];
  const validTimestamps = firstNonZeroIdx !== -1 ? filteredTimestamps.slice(firstNonZeroIdx) : [];

  // Calculate total return based on valid data
  const firstEquity = validEquity[0] || 0;
  const lastEquity = validEquity[validEquity.length - 1] || 0;
  const totalReturn = firstEquity > 0 ? lastEquity - firstEquity : 0;
  const totalReturnPct = firstEquity > 0 ? (totalReturn / firstEquity) * 100 : 0;

  const chartData = {
    labels: validTimestamps.map(ts => {
      const d = new Date(ts * 1000);
      return d.toLocaleString(undefined, { month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit' });
    }),
    datasets: [
      {
        label: 'Equity',
        data: validEquity,
        fill: false,
        borderColor: totalReturn >= 0 ? '#22c55e' : '#ef4444',
        backgroundColor: 'transparent',
        tension: 0.4,
        pointRadius: 0,
        borderWidth: 2,
      },
    ],
  };

  const options = {
    responsive: true,
    maintainAspectRatio: false,
    plugins: {
      legend: {
        display: false,
      },
      tooltip: {
        mode: 'index',
        intersect: false,
        backgroundColor: 'rgba(18, 18, 18, 0.9)',
        titleColor: '#fff',
        bodyColor: '#fff',
        borderColor: 'rgba(255, 255, 255, 0.1)',
        borderWidth: 1,
      },
    },
    scales: {
      x: {
        display: false,
      },
      y: {
        display: false,
        suggestedMin: validEquity.length > 0 ? Math.min(...validEquity) * 0.99 : 0,
        suggestedMax: validEquity.length > 0 ? Math.max(...validEquity) * 1.01 : 0,
      },
    },
  };

  return (
    <div className={styles.chartCard}>
      <div className={styles.mainLayout}>
        <div className={styles.chartSection}>
          <div className={styles.chartHeader}>
            <div className={styles.title}>{title}</div>
            <div className={`${styles.statValue} ${totalReturn >= 0 ? styles.positive : styles.negative}`}>
              {totalReturn >= 0 ? '+' : ''}{totalReturnPct.toFixed(2)}%
            </div>
          </div>
          
          <div className={styles.equity}>
            ${equity.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
          </div>

          <div className={styles.chartContainer}>
            <Line data={chartData} options={options} />
          </div>

          <div className={styles.statsGrid}>
            <div className={styles.statItem}>
              <div className={styles.statLabel}>Buying Power</div>
              <div className={styles.statValue}>${buyingPower.toLocaleString()}</div>
            </div>
            <div className={styles.statItem}>
              <div className={styles.statLabel}>1W Change</div>
              <div className={`${styles.statValue} ${totalReturn >= 0 ? styles.positive : styles.negative}`}>
                ${totalReturn.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
              </div>
            </div>
          </div>
        </div>

        {positions && positions.length > 0 && (
          <div className={styles.positionsSection}>
            <div className={styles.positionsHeader}>All Positions ({positions.length})</div>
            <div className={styles.positionList}>
              {positions.map(pos => {
                const marketValue = Number(pos.market_value || pos.marketValue || 0);
                const changeToday = Number(pos.change_today || pos.changeToday || 0);
                const qty = Number(pos.qty || 0);
                
                return (
                  <div key={pos.symbol} className={styles.positionItem}>
                    <div className={styles.posInfo}>
                      <span className={styles.posSymbol}>{pos.symbol}</span>
                      <span className={styles.posQty}>{qty.toFixed(2)} shares</span>
                    </div>
                    <div className={styles.posMarketPrice}>
                      ${marketValue.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                    </div>
                    <span className={`${styles.posChange} ${changeToday >= 0 ? styles.positive : styles.negative}`}>
                      {changeToday >= 0 ? '↑' : '↓'}{(Math.abs(changeToday) * 100).toFixed(1)}%
                    </span>
                  </div>
                );
              })}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
