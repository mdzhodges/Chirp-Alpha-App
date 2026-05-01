import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import styles from './SearchForm.module.css';

export default function SearchForm() {
  const [localSymbol, setLocalSymbol] = useState('');
  const navigate = useNavigate();

  const handleSubmit = (e) => {
    e.preventDefault();
    const trimmed = localSymbol.trim();
    if (trimmed) {
      navigate(`/dashboard?s=${trimmed.toUpperCase()}`);
      setLocalSymbol('');
    }
  };

  return (
    <form onSubmit={handleSubmit} className={styles.form}>
      <div className={styles.inputGroup}>
        <div className={styles.searchIcon}>
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
            <circle cx="11" cy="11" r="8"></circle>
            <line x1="21" y1="21" x2="16.65" y2="16.65"></line>
          </svg>
        </div>
        <input
          className={styles.input}
          value={localSymbol}
          onChange={(e) => setLocalSymbol(e.target.value.toUpperCase())}
          placeholder="SEARCH TICKER..."
          autoCapitalize="characters"
          autoCorrect="off"
          spellCheck={false}
        />
        <div className={styles.shortcut}>
          <span>/</span>
        </div>
      </div>
    </form>
  );
}
