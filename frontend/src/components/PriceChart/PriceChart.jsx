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

  const momentumData = ticker?.momentumHistory || [];
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

  // 3. Align momentum points (5-day lookahead) with Smooth Interpolation
  const momentumLineData = allPoints.map(point => {
    const ts = new Date(point.timestamp).getTime();
    const fiveDaysInMs = 5 * 24 * 60 * 60 * 1000;
    const expectedTime = ts - fiveDaysInMs;

    const sortedMom = [...momentumData].sort((a, b) => new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime());

    let p1 = null;
    let p2 = null;

    for (let i = 0; i < sortedMom.length; i++) {
      const momTs = new Date(sortedMom[i].timestamp).getTime();
      if (momTs <= expectedTime) {
        p1 = sortedMom[i];
      } else {
        p2 = sortedMom[i];
        break;
      }
    }

    if (p1 && p2) {
      const t1 = new Date(p1.timestamp).getTime();
      const t2 = new Date(p2.timestamp).getTime();
      const ratio = (expectedTime - t1) / (t2 - t1);
      const interpolatedValue = p1.value + (p2.value - p1.value) * ratio;
      return { x: ts, y: interpolatedValue };
    } else if (p1) {
      const t1 = new Date(p1.timestamp).getTime();
      if (Math.abs(expectedTime - t1) < 24 * 60 * 60 * 1000) {
        return { x: ts, y: p1.value };
      }
    }
    return null;
  }).filter(p => p !== null);

  const isCandle = mode === "candlestick";

  return (
    <div className={styles.chartCard}>
      <div className={styles.chartHeader}>
        {isCandle ? "Market Technicals (1H Candles)" : "AI Momentum vs. Price Action"}
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
              },
              {
                type: 'line',
                label: 'AI Momentum',
                data: momentumLineData,
                borderColor: '#fb7185',
                backgroundColor: 'transparent',
                fill: false,
                tension: 0.4,
                yAxisID: 'y1',
                pointRadius: 0,
                borderWidth: 2.5,
              }
            ],
          }}
          options={{
            responsive: true,
            maintainAspectRatio: false,
            animation: { duration: 0 },
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
              y1: isCandle ? { display: false } : {
                type: 'linear',
                display: true,
                position: 'right',
                grid: { drawOnChartArea: false },
                title: { display: true, text: 'Momentum', color: '#fb7185', font: { weight: 'bold', size: 10 } },
                ticks: { color: '#fb7185' },
                suggestedMin: -0.5,
                suggestedMax: 0.5
              },
            },
          }}
        />
      </div>
    </div>
  );
}
