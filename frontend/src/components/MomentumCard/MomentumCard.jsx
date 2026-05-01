import styles from './MomentumCard.module.css'

export default function MomentumCard({ momentumNumber, momentumDirection, modelStats }) {
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
    
      {modelStats && (
        <div className={styles.statsGrid}>
          <div className={styles.statItem}>
            <span className={styles.statLabel}>Up Acc:</span>
            <span className={styles.statValue}>{(Number(modelStats.upAccuracy || 0) * 100).toFixed(1)}%</span>
          </div>
          <div className={styles.statItem}>
            <span className={styles.statLabel}>Down Acc:</span>
            <span className={styles.statValue}>{(Number(modelStats.downAccuracy || 0) * 100).toFixed(1)}%</span>
          </div>
          <div className={styles.statItem}>
            <span className={styles.statLabel}>IC:</span>
            <span className={styles.statValue}>{Number(modelStats.ic || 0).toFixed(3)}</span>
          </div>
        </div>
      )}
</div>
  );
}