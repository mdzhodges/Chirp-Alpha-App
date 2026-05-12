import {
  Chart as ChartJS,
  LinearScale,
  PointElement,
  LineElement,
  LineController,
  Title,
  Tooltip,
  Legend,
  TimeScale,
  TimeSeriesScale,
  CategoryScale
} from 'chart.js';
import { Chart } from 'react-chartjs-2';
import { CandlestickController, CandlestickElement } from 'chartjs-chart-financial';
import 'chartjs-adapter-date-fns';
import styles from './PriceChart.module.css';

ChartJS.register(
  LinearScale,
  CategoryScale,
  PointElement,
  LineElement,
  LineController,
  CandlestickController,
  CandlestickElement,
  TimeScale,
  TimeSeriesScale,
  Title,
  Tooltip,
  Legend
);

export default function PriceChart({ history, ticker, mode = "candlestick" }) {
  if (!history || !history.histogram || history.histogram.length === 0) return null;

  const rawData = history.histogram;

  // 1. Generate future projection slots (5 days ahead)
  const lastPoint = rawData[rawData.length - 1];
  const lastTimestamp = new Date(lastPoint.timestamp).getTime();
  
  const futurePoints = [];
  for (let i = 1; i <= (5 * 24); i++) {
    futurePoints.push({
      timestamp: new Date(lastTimestamp + (i * 60 * 60 * 1000)).toISOString(),
      isFuture: true
    });
  }

  const allPoints = [...rawData, ...futurePoints];

  // 2. Prepare Candlestick data
  const candlestickData = rawData.map(p => ({
    x: new Date(p.timestamp).getTime(),
    o: Number(p.open),
    h: Number(p.high),
    l: Number(p.low),
    c: Number(p.close)
  }));

  const isCandle = mode === "candlestick";

  return (
    <div className={styles.chartCard}>
      <div className={styles.chartHeader}>
        {isCandle ? "Market Technicals (1H Candles)" : "Price Action"}
      </div>
      <div className={styles.chartContainer}>
        <Chart
          type={isCandle ? "candlestick" : "line"}
          data={{
            datasets: isCandle ? [
              {
                label: 'Price',
                data: candlestickData,
                yAxisID: 'y',
                // Using explicit standard colors
                color: {
                  up: '#22c55e',
                  down: '#ef4444',
                  unchanged: '#9ca3af'
                },
                borderColor: {
                  up: '#22c55e',
                  down: '#ef4444',
                  unchanged: '#9ca3af'
                },
                borderWidth: 1.5,
                barPercentage: 0.8,
              }
            ] : [
              {
                type: 'line',
                label: 'Price',
                data: rawData.map(p => ({ x: new Date(p.timestamp).getTime(), y: Number(p.close) })),
                borderColor: 'rgba(34, 197, 94, 0.8)',
                backgroundColor: 'transparent',
                tension: 0.1,
                borderWidth: 1.5,
                pointRadius: 0,
                yAxisID: 'y',
              }
            ],
          }}
          options={{
            responsive: true,
            maintainAspectRatio: false,
            // Target the specific element controller as advised
            elements: {
              candlestick: {
                color: {
                  up: '#22c55e',    // Emerald Green
                  down: '#ef4444',  // Bright Red
                  unchanged: '#9ca3af',
                },
                borderColor: {
                  up: '#22c55e',
                  down: '#ef4444',
                  unchanged: '#9ca3af',
                }
              }
            },
            plugins: {
              legend: {
                display: true,
                position: 'top',
                labels: { color: 'rgba(255, 255, 255, 0.7)', font: { weight: '600', size: 10 } }
              },
              tooltip: {
                mode: 'index',
                intersect: false,
                backgroundColor: 'rgba(18, 18, 18, 0.95)',
              },
            },
            scales: {
              x: {
                type: 'timeseries',
                offset: true,
                grid: { display: false },
                time: {
                  unit: 'day',
                  displayFormats: { day: 'MMM d' }
                },
                ticks: {
                  source: 'data',
                  color: 'rgba(255, 255, 255, 0.5)',
                  autoSkip: true,
                  maxTicksLimit: 8
                }
              },
              y: {
                type: 'linear',
                display: true,
                position: 'left',
                grid: { color: 'rgba(255, 255, 255, 0.05)' },
                ticks: { color: 'rgba(255, 255, 255, 0.7)' },
                title: { display: true, text: 'Price ($)', color: 'rgba(255, 255, 255, 0.4)', font: { size: 10 } }
              },
            },
          }}
        />
      </div>
    </div>
  );
}
