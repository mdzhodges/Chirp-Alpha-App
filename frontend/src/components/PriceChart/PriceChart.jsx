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

ChartJS.register(
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  Title,
  Tooltip,
  Legend
);

export default function PriceChart({ history, ticker, styles }) {
  if (!history || !history.histogram) return null;

  const momentumData = ticker?.momentumHistory || [];

  // Align momentum points with price chart labels
  // Note: history.histogram is likely hourly, momentumHistory is daily
  // We'll map momentum values to the closest timestamps in the labels
  const momentumDataset = history.histogram.map(point => {
    const ptDate = new Date(point.timestamp).toISOString().split('T')[0];
    const momPoint = momentumData.find(m => {
      try {
        return new Date(m.timestamp).toISOString().split('T')[0] === ptDate;
      } catch (e) {
        return false;
      }
    });
    return momPoint ? momPoint.value : null;
  });

  return (
    <div className={styles.chartCard}>
      <div className={styles.chartHeader}>Price & Momentum Trend</div>
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
                yAxisID: 'y',
              },
              {
                label: 'Chirp Momentum',
                data: momentumDataset,
                borderColor: 'rgb(255, 99, 132)',
                backgroundColor: 'rgba(255, 99, 132, 0.5)',
                tension: 0.3,
                yAxisID: 'y1',
                spanGaps: true,
                pointRadius: 4,
                borderWidth: 2,
              },
            ],
          }}
          options={{
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
              legend: {
                display: true,
                position: 'top',
              },
              tooltip: {
                mode: 'index',
                intersect: false,
              },
            },
            scales: {
              x: {
                ticks: {
                  maxTicksLimit: 10,
                },
              },
              y: {
                type: 'linear',
                display: true,
                position: 'left',
                title: {
                  display: true,
                  text: 'Price',
                },
              },
              y1: {
                type: 'linear',
                display: true,
                position: 'right',
                grid: {
                  drawOnChartArea: false,
                },
                title: {
                  display: true,
                  text: 'Momentum',
                },
              },
            },
          }}
        />
      </div>
    </div>
  );
}