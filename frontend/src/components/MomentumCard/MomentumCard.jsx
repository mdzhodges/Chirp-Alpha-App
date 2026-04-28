export default function MomentumCard({ momentumNumber, momentumDirection, styles }) {
  return (
    <div className={styles.momentumCard}>
      <div className={styles.momentumLabel}>Predicted Momentum Score</div>
      <div
        className={`${styles.momentumValue} ${
          momentumDirection === 'up'
            ? styles.momentumValueUp
            : momentumDirection === 'down'
            ? styles.momentumValueDown
            : styles.momentumValueNeutral
        }`}
      >
        {momentumNumber.toFixed(2)}
      </div>
      <span
        className={`${styles.momentumDirection} ${
          momentumDirection === 'up'
            ? styles.momentumDirectionUp
            : momentumDirection === 'down'
            ? styles.momentumDirectionDown
            : styles.momentumDirectionNeutral
        }`}
      >
        {momentumDirection === 'up' ? 'Bullish' : momentumDirection === 'down' ? 'Bearish' : 'Neutral'}
      </span>
    </div>
  );
}