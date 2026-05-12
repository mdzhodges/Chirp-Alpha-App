import styles from './MomentumCard.module.css'

export default function MomentumCard({ momentumNumber, momentumDirection, modelStats, isLoading }) {
  return (
    <div className={`${styles.momentumCard} ${isLoading ? styles.isLoading : ''}`}>
      <div className={styles.momentumLabel}>5-Day Predicted Momentum</div>
      <div
        className={`${styles.momentumValue} ${
          isLoading 
            ? styles.skeletonText
            : momentumDirection === 'up'
            ? styles.momentumValueUp
            : momentumDirection === 'down'
            ? styles.momentumValueDown
            : styles.momentumValueNeutral
        }`}
      >
        {isLoading ? '--.--' : momentumNumber.toFixed(2)}
      </div>
      <span
        className={`${styles.momentumDirection} ${
          isLoading
            ? styles.skeletonLabel
            : momentumDirection === 'up'
            ? styles.momentumDirectionUp
            : momentumDirection === 'down'
            ? styles.momentumDirectionDown
            : styles.momentumDirectionNeutral
        }`}
      >
        {isLoading ? 'Analyzing...' : (momentumDirection === 'up' ? 'Bullish' : momentumDirection === 'down' ? 'Bearish' : 'Neutral')}
      </span>
    
      {modelStats && (
        <div className={styles.statsGrid}>
          <div className={styles.statItemRow}>
            <div className={styles.statItem}>
              <span className={styles.statLabel}>Overall Acc:</span>
              <span className={styles.statValue}>{(Number(modelStats.overallAccuracy || 0) * 100).toFixed(2)}%</span>
            </div>
            <div className={styles.statItem}>
              <span className={styles.statLabel}>Up Acc:</span>
              <span className={styles.statValue}>{(Number(modelStats.upAccuracy || 0) * 100).toFixed(2)}%</span>
            </div>
            <div className={styles.statItem}>
              <span className={styles.statLabel}>Down Acc:</span>
              <span className={styles.statValue}>{(Number(modelStats.downAccuracy || 0) * 100).toFixed(2)}%</span>
            </div>
            <div className={styles.statItem}>
              <span className={styles.statLabel}>IC:</span>
              <span className={styles.statValue}>{Number(modelStats.ic || 0).toFixed(4)}</span>
            </div>
          </div>
        </div>
      )}
</div>
  );
}