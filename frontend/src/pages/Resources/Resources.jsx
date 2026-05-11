import React, { useEffect, useState } from 'react';
import PortfolioChart from '../../components/PortfolioChart/PortfolioChart';
import styles from './Resources.module.css';

export default function Resources() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function fetchData() {
      try {
        const response = await fetch('/api/alpaca/dashboard');
        if (response.ok) {
          const result = await response.json();
          setData(result);
        }
      } catch (error) {
        console.error('Error fetching Alpaca dashboard data:', error);
      } finally {
        setLoading(false);
      }
    }

    fetchData();
  }, []);

  if (loading) {
    return <div className={styles.loading}>Initializing Neural Links...</div>;
  }

  return (
    <div className={styles.container}>
      <header className={styles.header}>
        <h1 className={styles.title}>System Performance</h1>
        <p className={styles.subtitle}>Real-time performance metrics across active trading strategies.</p>
      </header>

      <div className={styles.portfolioGrid}>
        <PortfolioChart title="Bullish Strategy" data={data?.bullish} />
        <PortfolioChart title="Balanced Strategy" data={data?.balanced} />
        <PortfolioChart title="Bearish Strategy" data={data?.bearish} />
      </div>
    </div>
  );
}
