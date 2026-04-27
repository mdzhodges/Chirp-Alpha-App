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

export default function PriceChart({ history, styles }) {
  if (!history || !history.histogram) return null;

  return (
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
  );
}