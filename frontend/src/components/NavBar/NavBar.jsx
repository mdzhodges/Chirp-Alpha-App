import { useState, useRef, useEffect } from 'react';
import { Link, NavLink } from 'react-router-dom';
import styles from './NavBar.module.css';
import logo from '../../assets/chirp_logo_no_bg.png';
import SearchForm from '../SearchForm/SearchForm';

export default function Navbar() {
  const [isDropdownOpen, setIsDropdownOpen] = useState(false);
  const dropdownRef = useRef(null);

  useEffect(() => {
    function handleClickOutside(event) {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target)) {
        setIsDropdownOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  return (
    <nav className={styles.nav}>
      <div className={styles.left}>
        <div className={styles.logoContainer} ref={dropdownRef}>
          <div 
            className={styles.logoWrapper} 
            onClick={() => setIsDropdownOpen(!isDropdownOpen)}
          >
            <img src={logo} alt="Chirp Logo" className={styles.icon} />
            <span className={styles.logoText}>Chirp Alpha</span>
            <svg 
              className={`${styles.chevron} ${isDropdownOpen ? styles.chevronOpen : ''}`} 
              width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round"
            >
              <polyline points="6 9 12 15 18 9"></polyline>
            </svg>
          </div>
          
          {isDropdownOpen && (
            <div className={styles.dropdown}>
              <Link to="/login" className={styles.dropdownItem} onClick={() => setIsDropdownOpen(false)}>Log in</Link>
              <Link to="/signup" className={styles.dropdownItem} onClick={() => setIsDropdownOpen(false)}>Sign up</Link>
            </div>
          )}
        </div>
      </div>

      <div className={styles.center}>
        <div className={styles.links}>
          <NavLink to="/" className={({isActive}) => `${styles.navLink} ${isActive ? styles.navLinkActive : ''}`}>Home</NavLink>
          <NavLink to="/dashboard" className={({isActive}) => `${styles.navLink} ${isActive ? styles.navLinkActive : ''}`}>Dashboard</NavLink>
          <NavLink to="/resources" className={({isActive}) => `${styles.navLink} ${isActive ? styles.navLinkActive : ''}`}>Resources</NavLink>
          <NavLink to="/about" className={({isActive}) => `${styles.navLink} ${isActive ? styles.navLinkActive : ''}`}>About</NavLink>
        </div>
      </div>

      <div className={styles.right}>
        <div className={styles.searchWrapper}>
          <SearchForm />
        </div>
      </div>
    </nav>
  );
}
