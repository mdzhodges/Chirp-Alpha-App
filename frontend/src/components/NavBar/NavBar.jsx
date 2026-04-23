import { Link } from 'react-router-dom';
import styles from './Navbar.module.css';
import logo from '../../assets/chirp_logo_no_bg.png';

export default function Navbar() {
  return (
    <nav className={styles.nav}>
      {/* Changed div to Link here */}
      <Link to="/" className={styles.logo}>
        <img src={logo} alt="Chirp Logo" className={styles.icon} />
        <span>Chirp Alpha</span>
      </Link>
      
      <div className={styles.links}>
        <Link to="/dashboard">Product</Link>
        <Link to="/resources">Resources</Link>
        <Link to="/about">About</Link>
      </div>

      <div className={styles.actions}>
        <Link to="AuthPage" className={styles.login}>Log in</Link>
        <Link to="SignupPage" className={styles.signupBtn}>Sign up</Link>
      </div>
    </nav>
  );
}