import React, { useMemo } from 'react';
import { Line } from 'react-chartjs-2';
import {
  Chart as ChartJS,
  Filler,
  LineElement,
  PointElement,
  LinearScale,
  CategoryScale,
  TimeSeriesScale,
  TimeScale,
  Tooltip,
  Legend
} from 'chart.js';
import 'chartjs-adapter-date-fns';
import styles from './AlphaVisionChart.module.css';

ChartJS.register(
  Filler,
  LineElement,
  PointElement,
  LinearScale,
  CategoryScale,
  TimeSeriesScale,
  TimeScale,
  Tooltip,
  Legend
);

export default function AlphaVisionChart({ history, ticker, mode }) {
  // 0. Preliminary data parsing for bounds
  const { minTs, maxTs, sortedHistory, sortedMomentum, futureDates } = useMemo(() => {
    const rawHistory = history?.histogram || (Array.isArray(history) ? history : null);
    if (!rawHistory || rawHistory.length === 0) {
      return { minTs: null, maxTs: null, sortedHistory: [], sortedMomentum: [], futureDates: [] };
    }

    const sh = [...rawHistory].sort((a, b) => new Date(a.timestamp) - new Date(b.timestamp));
    const sm = ticker?.momentumHistory 
      ? [...ticker.momentumHistory].sort((a, b) => new Date(a.timestamp) - new Date(b.timestamp))
      : [];

    const lastPoint = sh[sh.length - 1];
    const lastDate = new Date(lastPoint.timestamp);
    const fd = [];
    let d = new Date(lastDate);
    while (fd.length < 5) {
      d.setDate(d.getDate() + 1);
      if (d.getDay() !== 0 && d.getDay() !== 6) { // skip weekends
        fd.push(new Date(d).toISOString());
      }
    }

    const startTs = new Date(sh[0].timestamp).getTime();
    let endTs = new Date(sh[sh.length - 1].timestamp).getTime();

    if (mode === 'crystalBall') {
      let finalFutureDate = new Date(lastPoint.timestamp);
      let count = 0;
      while (count < 5) {
        finalFutureDate.setDate(finalFutureDate.getDate() + 1);
        if (finalFutureDate.getDay() !== 0 && finalFutureDate.getDay() !== 6) count++;
      }
      endTs = finalFutureDate.getTime();
    }

    return { minTs: startTs, maxTs: endTs, sortedHistory: sh, sortedMomentum: sm, futureDates: fd };
  }, [history, ticker?.momentumHistory, mode]);

  const chartData = useMemo(() => {
    if (!sortedHistory.length || !sortedMomentum.length) return { labels: [], datasets: [] };

    const lastPriceTs = new Date(sortedHistory[sortedHistory.length - 1].timestamp).getTime();

    // Data mapped to {x, y} for time-series scale
    const priceData = sortedHistory.map(h => ({ 
      x: new Date(h.timestamp).getTime(), 
      y: Number(h.close) 
    }));
    
    let momentumData = [];
    let futureMomentumData = [];
    let projectionData = [];

    // Helper to calculate ALL shifted momentum points
    const getAllShiftedMomentum = (momArray) => {
      return momArray.map(m => {
        const date = new Date(m.timestamp);
        date.setUTCHours(16, 0, 0, 0); // Align to market close
        
        // Expected Price = Price at prediction * (1 + momentum/100)
        // Use the explicit baseline price from the backend
        const priceAtPrediction = Number(m.baselinePrice);
        const expectedPrice = priceAtPrediction * (1 + (Number(m.value) / 100));

        let count = 0;
        while (count < 5) {
          date.setDate(date.getDate() + 1);
          if (date.getDay() !== 0 && date.getDay() !== 6) count++;
        }
        return { x: date.getTime(), y: expectedPrice };
      }).filter(pt => pt.x >= minTs); // Don't filter max here, we'll split it
    };

    const allShifted = getAllShiftedMomentum(sortedMomentum);

    if (mode === 'validation') {
      momentumData = allShifted.filter(pt => pt.x <= lastPriceTs);
    } else {
      // Crystal Ball mode
      momentumData = allShifted.filter(pt => pt.x <= lastPriceTs);
      
      // Future predictive momentum (dashed blue)
      // We start from the last historical point to keep the line connected
      const lastHist = momentumData[momentumData.length - 1];
      futureMomentumData = allShifted.filter(pt => pt.x >= lastPriceTs);

      // Latest prediction linear projection (purple dashed)
      // Use offset 1 (Previous Close) as the baseline to match the card and Alpaca
      const currentMomentum = sortedMomentum[sortedMomentum.length - 2] || sortedMomentum[sortedMomentum.length - 1];
      if (currentMomentum) {
        const lastHistoricalPt = sortedHistory[sortedHistory.length - 1];
        const lastHistoricalTs = new Date(lastHistoricalPt.timestamp).getTime();
        const lastPrice = Number(lastHistoricalPt.close);
        
        // Target Price = Baseline (Previous Close) * (1 + Momentum/100)
        const baselinePrice = Number(currentMomentum.baselinePrice);
        const targetPrice = baselinePrice * (1 + (Number(currentMomentum.value) / 100));
        
        projectionData.push({ x: lastHistoricalTs, y: lastPrice });
        const totalFutureDays = futureDates.length;
        futureDates.forEach((fd, idx) => {
          const date = new Date(fd);
          date.setUTCHours(16, 0, 0, 0);
          const ts = date.getTime();
          // We still project from the current live price to the target
          const stepPrice = lastPrice + (targetPrice - lastPrice) * ((idx + 1) / totalFutureDays);
          projectionData.push({ x: ts, y: stepPrice });
        });
      }
    }

    return {
      datasets: [
        {
          label: 'Actual Price',
          data: priceData,
          borderColor: 'rgba(255, 255, 255, 0.8)',
          backgroundColor: 'transparent',
          yAxisID: 'y',
          tension: 0.1,
          pointRadius: 0,
          order: 2,
        },
        {
          label: mode === 'validation' ? 'Shifted T+5 Expected Price' : 'Historical T+5 Targets',
          data: momentumData,
          borderColor: mode === 'validation' ? '#10b981' : '#3b82f6',
          backgroundColor: 'transparent',
          yAxisID: 'y',
          tension: 0.3,
          fill: false,
          pointRadius: 2,
          spanGaps: true,
          order: 3,
        },
        ...(mode === 'crystalBall' ? [
          {
            label: 'Upcoming T+5 Targets',
            data: futureMomentumData,
            borderColor: '#3b82f6',
            borderDash: [5, 5],
            backgroundColor: 'transparent',
            yAxisID: 'y',
            tension: 0.3,
            fill: false,
            pointRadius: 2,
            spanGaps: true,
            order: 4,
          },
          {
            label: '5-Day Price Target Projection',
            data: projectionData,
            borderColor: '#8b5cf6',
            borderDash: [5, 5],
            backgroundColor: 'transparent',
            fill: false,
            yAxisID: 'y', 
            tension: 0,
            pointRadius: 3,
            pointBackgroundColor: '#8b5cf6',
            spanGaps: true,
            order: 1,
          }
        ] : [])
      ]
    };
  }, [sortedHistory, sortedMomentum, futureDates, minTs, maxTs, mode]);

  const options = {
    responsive: true,
    maintainAspectRatio: false,
    interaction: { mode: 'index', intersect: false },
    scales: {
      x: {
        type: 'time',
        time: {
          unit: 'day',
          displayFormats: { day: 'MMM d' },
          tooltipFormat: 'MMM d, h:mm a'
        },
        min: minTs,
        max: maxTs,
        grid: { display: false },
        ticks: {
          source: 'auto',
          color: 'rgba(255, 255, 255, 0.5)',
          maxTicksLimit: 12,
          autoSkip: true,
          maxRotation: 0,
          stepSize: 1
        }
      },
      y: { 
        type: 'linear', 
        display: true, 
        position: 'left', 
        grid: { color: 'rgba(255,255,255,0.05)' },
        title: { display: true, text: 'Price ($)', color: 'rgba(255, 255, 255, 0.6)', font: { size: 11, weight: 'bold' } },
        ticks: {
          color: 'rgba(255, 255, 255, 0.7)'
        }
      }
    },
    plugins: { 
      legend: { labels: { color: '#fff' } },
      tooltip: {
        backgroundColor: 'rgba(18, 18, 18, 0.95)',
        titleColor: '#fff',
        bodyColor: '#fff',
        borderColor: 'rgba(255, 255, 255, 0.1)',
        borderWidth: 1
      }
    }
  };

  return (
    <div className={styles.chartCard}>
      <div className={styles.chartHeader}>
        {mode === 'validation' ? "Alpha Vision: Predictive Validation" : "Alpha Vision: 5-Day Target Projection"}
      </div>
      <div className={styles.chartContainer}>
        <Line data={chartData} options={options} />
      </div>
    </div>
  );
}
