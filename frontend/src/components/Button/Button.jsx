import { useNavigate } from 'react-router-dom';
import styles from './Button.module.css';

export default function Button({ text, to, onClick }) {
  const navigate = useNavigate();

  const handlePress = () => {
    if (to) {
      navigate(to);
    } else if (onClick) {
      onClick();
    }
  };

  return (
    <button className={styles.btn} onClick={handlePress}>
      {text}
    </button>
  );
}