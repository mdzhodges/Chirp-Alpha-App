import { Link } from 'react-router-dom';
import styles from './Hero.module.css';
import Button from '../Button/Button';

export default function Hero() {
  return (
    <section className={styles.section}>
      <h1 className={styles.title}>Catch the Momentum.</h1>
      <p className={styles.subtitle}>
        Institutional-grade stock momentum tracking for the modern trader.
      </p>
      <Link to="/dashboard">
        <Button text="Start Tracking" /> 
      </Link>
    </section>
  );
}