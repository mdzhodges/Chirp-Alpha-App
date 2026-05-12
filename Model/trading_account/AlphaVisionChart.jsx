import React, { useMemo } from 'react';
import { Line } from 'react-chartjs-2';
import {
  Chart as ChartJS,
  Filler
} from 'chart.js';

ChartJS.register(Filler);

export default function AlphaVisionChart({ history, ticker, mode }) {
  const chartData = useMemo(() => {
    if (!history || !ticker?.momentumHistory) return { labels: [], datasets: [] };

    // 1. Sort history chronologically
    const sortedHistory = [...history].sort((a, b) => new Date(a.date) - new Date(b.date));
    const sortedMomentum = [...ticker.momentumHistory].sort((a, b) => new Date(a.date) - new Date(b.date));

    // 2. Generate future dates for the T+5 cone
    const lastDate = new Date(sortedHistory[sortedHistory.length - 1].date);
    const futureDates = [];
    let d = new Date(lastDate);
    while (futureDates.length < 5) {
      d.setDate(d.getDate() + 1);
      if (d.getDay() !== 0 && d.getDay() !== 6) { // skip weekends
        futureDates.push(new Date(d).toISOString());
      }
    }

    const allLabelsRaw = [
      ...sortedHistory.map(h => h.date),
      ...futureDates
    ];
    
    const labels = allLabelsRaw.map(d => new Date(d).toLocaleDateString(undefined, { month: 'short', day: 'numeric' }));

    const priceData = [
      ...sortedHistory.map(h => h.close),
      ...Array(5).fill(null)
    ];

    let momentumData = [];
    let projectionData = [];

    if (mode === 'validation') {
      // Shift momentum 5 trading days into the future to align with what it was predicting
      momentumData = Array(labels.length).fill(null);
      sortedMomentum.forEach((m) => {
        // Find the index of this prediction in the history
        const historyIdx = sortedHistory.findIndex(h => new Date(h.date).toDateString() === new Date(m.date).toDateString());
        if (historyIdx !== -1 && historyIdx + 5 < labels.length) {
          momentumData[historyIdx + 5] = m.momentum;
        }
      });
    } else {
      // Crystal Ball mode
      momentumData = Array(labels.length).fill(null);
      projectionData = Array(labels.length).fill(null);

      sortedMomentum.forEach((m) => {
        const historyIdx = sortedHistory.findIndex(h => new Date(h.date).toDateString() === new Date(m.date).toDateString());
        if (historyIdx !== -1) {
          momentumData[historyIdx] = m.momentum;
        }
      });

      // The final momentum value extends out into the future cone
      const lastMomentum = sortedMomentum[sortedMomentum.length - 1];
      if (lastMomentum) {
        const historyIdx = sortedHistory.length - 1;
        for (let i = historyIdx; i < labels.length; i++) {
          projectionData[i] = lastMomentum.momentum;
        }
      }
    }

    return {
      labels,
      datasets: [
        {
          label: 'Price',
          data: priceData,
          borderColor: 'rgba(255, 255, 255, 0.8)',
          backgroundColor: 'transparent',
          yAxisID: 'y',
          tension: 0.1,
          pointRadius: 0,
          order: 2,
        },
        {
          label: mode === 'validation' ? 'Shifted T+5 Momentum' : 'Live Momentum',
          data: momentumData,
          borderColor: mode === 'validation' ? '#10b981' : '#3b82f6',
          backgroundColor: mode === 'validation' ? 'rgba(16, 185, 129, 0.2)' : 'rgba(59, 130, 246, 0.2)',
          yAxisID: 'y1',
          tension: 0.3,
          fill: 'origin',
          pointRadius: 2,
          order: 3,
        },
        ...(mode === 'crystalBall' ? [{
          label: '5-Day Target Projection',
          data: projectionData,
          borderColor: '#8b5cf6',
          borderDash: [5, 5],
          backgroundColor: 'rgba(139, 92, 246, 0.2)',
          fill: 'origin',
          yAxisID: 'y1',
          tension: 0,
          pointRadius: 3,
          pointBackgroundColor: '#8b5cf6',
          order: 1,
        }] : [])
      ]
    };
  }, [history, ticker, mode]);

  const options = {
    responsive: true,
    maintainAspectRatio: false,
    interaction: { mode: 'index', intersect: false },
    scales: {
      y: { type: 'linear', display: true, position: 'left', grid: { color: 'rgba(255,255,255,0.05)' } },
      y1: { type: 'linear', display: true, position: 'right', grid: { drawOnChartArea: false } }
    },
    plugins: { legend: { labels: { color: '#fff' } } }
  };

  return (
    <div style={{ height: '100%', minHeight: '400px', width: '100%', padding: '10px' }}>
      <Line data={chartData} options={options} />
    </div>
  );
}