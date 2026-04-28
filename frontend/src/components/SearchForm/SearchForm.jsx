import styles from './SearchForm.module.css'

export default function SearchForm({ symbol, setSymbol, setQuerySymbol, status }) {
  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        setQuerySymbol(symbol);
      }}
      className={styles.form}
    >
      <div className={styles.inputGroup}>
        <span className={styles.inputLabel}>Ticker Symbol</span>
        <input
          className={styles.input}
          value={symbol}
          onChange={(e) => setSymbol(e.target.value)}
          placeholder="AAPL"
          autoCapitalize="characters"
          autoCorrect="off"
          spellCheck={false}
        />
      </div>
      <button type="submit" className={styles.button} disabled={status === 'loading'}>
        {status === 'loading' ? 'Loading…' : 'Fetch'}
      </button>
    </form>
  );
}