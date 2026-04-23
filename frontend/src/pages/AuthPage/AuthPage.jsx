import { Authenticator, useAuthenticator, View } from '@aws-amplify/ui-react';
import { useNavigate } from 'react-router-dom';
import { useEffect } from 'react';
import styles from './AuthPage.module.css';

export default function AuthPage() {
  const navigate = useNavigate();
  const { authStatus } = useAuthenticator((context) => [context.authStatus]);

  useEffect(() => {
    if (authStatus === 'authenticated') {
      navigate('/dashboard');
    }
  }, [authStatus, navigate]);

  return (
    <main className={styles.container}>
      <div className={styles.wrapper}>
        <h1 className={styles.heading}>Log in to Chirp Alpha</h1>
        
        {/* We use the simple version to avoid triggering default Card styles */}
        <Authenticator socialProviders={['google']} hideSignUp={true} />

        <p className={styles.footer}>
          Don't have an account? <span className={styles.link}>Sign Up</span>
        </p>
      </div>
    </main>
  );
}