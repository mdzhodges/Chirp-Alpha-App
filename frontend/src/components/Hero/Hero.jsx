import styles from './Hero.module.css';
import Button from '../Button/Button.jsx';

export default function Hero() {
  return (
    <section className={styles.section}>
      <h1 className={styles.title}>Catch the Momentum.</h1>
      <p className={styles.subtitle}>
        Institutional-grade stock momentum tracking for the modern trader.
      </p>
      <Button text="Start Tracking" to="/dashboard" /> 
    </section>
  );
}