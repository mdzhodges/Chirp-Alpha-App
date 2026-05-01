import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  LineController,
  Title,
  Tooltip,
  Legend,
} from 'chart.js';
import { Line } from 'react-chartjs-2';
import styles from './PriceChart.module.css';

ChartJS.register(
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  LineController,
  Title,
  Tooltip,
  Legend
);

export default function PriceChart({ history, ticker }) {
  if (!history || !history.histogram) return null;

  const momentumData = ticker?.momentumHistory || [];
  const baseHistogram = history.histogram;
  if (baseHistogram.length === 0) return null;

  // 1. Generate future projection slots (5 days ahead)
  const lastPoint = baseHistogram[baseHistogram.length - 1];
  const lastTimestamp = new Date(lastPoint.timestamp);
  
  const futurePoints = [];
  for (let i = 1; i <= 5; i++) {
    const d = new Date(lastTimestamp);
    d.setHours(d.getHours() + (24 * i));
    futurePoints.push({
      timestamp: d.toISOString(),
      time: d.toLocaleString(undefined, { month: '2-digit', day: '2-digit' }) + ' (Proj)',
      isFuture: true
    });
  }

  const allPoints = [...baseHistogram, ...futurePoints];

  // 2. Align momentum points with a 5-day forward shift
  // A prediction made on date D represents the momentum at date D + 5 days.
  // So for a label at date L, we look for the prediction made on L - 5 days.
  const momentumDataset = allPoints.map(point => {
    if (!point.timestamp) return null;
    
    const targetDate = new Date(point.timestamp);
    const predictionDate = new Date(targetDate);
    predictionDate.setDate(predictionDate.getDate() - 5);
    const predDateStr = predictionDate.toISOString().split('T')[0];
    
    const momPoint = momentumData.find(m => {
      if (!m.timestamp) return false;
      try {
        return new Date(m.timestamp).toISOString().split('T')[0] === predDateStr;
      } catch (e) {
        return false;
      }
    });
    
    return momPoint ? momPoint.value : null;
  });

  return (
    <div className={styles.chartCard}>
      <div className={styles.chartHeader}>Price & Momentum Projection</div>
      <div className={styles.chartContainer}>
        <Line
          data={{
            labels: allPoints.map(p => p.time),
            datasets: [
              {
                label: 'Price',
                data: allPoints.map(p => p.isFuture ? null : p.close),
                borderColor: 'rgb(75, 192, 192)',
                backgroundColor: 'rgba(75, 192, 192, 0.5)',
                tension: 0.1,
                yAxisID: 'y',
              },
              {
                label: 'Predicted Momentum',
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
                  maxTicksLimit: 12,
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