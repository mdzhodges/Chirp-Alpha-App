import { Link } from 'react-router-dom';
import styles from './Hero.module.css';
import Button from '../Button/Button';

export default function Hero() {
  return (
    <section className={styles.section}>
      {/* Full-bleed background arrow */}
      <div className={styles.arrowBackground} aria-hidden="true">
        <svg
          className={styles.stockArrow}
          viewBox="0 0 300 200"
          fill="none"
          preserveAspectRatio="xMidYMid slice"
          xmlns="http://www.w3.org/2000/svg"
        >
          <defs>
            <linearGradient id="arrowGradient" x1="0%" y1="100%" x2="100%" y2="0%">
              <stop offset="0%" stopColor="#047857" />
              <stop offset="100%" stopColor="#34d399" />
            </linearGradient>

            {/* Arrowhead marker — auto-attaches & auto-rotates to the line end */}
            <marker
              id="arrowhead"
              viewBox="0 0 10 10"
              refX="3"
              refY="5"
              markerWidth="4"
              markerHeight="4"
              orient="auto-start-reverse"
              markerUnits="strokeWidth"
            >
              <path className={styles.arrowMarker} d="M 0 0 L 10 5 L 0 10 Z" fill="#34d399" />
            </marker>
          </defs>

          <polyline
            className={styles.arrowLine}
            points="0,180 90,60 160,120 290,20"
            stroke="url(#arrowGradient)"
            strokeWidth="14"
            strokeLinecap="butt"
            strokeLinejoin="miter"
            fill="none"
            markerEnd="url(#arrowhead)"
          />
        </svg>
      </div>

      {/* Foreground content */}
      <div className={styles.content}>
        <h1 className={styles.title}>Catch the Momentum.</h1>
        <p className={styles.subtitle}>
          Institutional-grade stock momentum tracking for the modern trader.
        </p>
        <Link to="/dashboard">
          <Button text="Start Tracking" />
        </Link>
      </div>
    </section>
  );
}