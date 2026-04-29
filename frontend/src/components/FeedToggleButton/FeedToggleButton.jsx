import styles from './FeedToggleButton.module.css'

export default function FeedToggleButton({ isOpen, onToggle }) {
  return (
    <button 
      onClick={onToggle}
      className={`${styles.tab} ${isOpen ? styles.tabOpen : styles.tabClosed}`}
    >
      {isOpen ? 'Feed →' : '←Feed'}
    </button>
  );
}