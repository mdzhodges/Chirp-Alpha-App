import { Authenticator, useAuthenticator } from '@aws-amplify/ui-react';
import { useNavigate } from 'react-router-dom';
import { useEffect } from 'react';
import styles from './SignupPage.module.css';

export default function SignupPage() {
  const navigate = useNavigate();
  const { authStatus } = useAuthenticator((context) => [context.authStatus]);

  useEffect(() => {
    if (authStatus === 'authenticated') {
      navigate('/dashboard');
    }
  }, [authStatus, navigate]);

  return (
    <div className={styles.container}>
      <div className={styles.wrapper}>
        <h1 className={styles.heading}>Sign Up for Chirp Alpha</h1>
        
        <Authenticator socialProviders={['google']} hideSignUp={true} />

        <p className={styles.footer}>
          Don't have an account? <span className={styles.link}>Sign Up</span>
        </p>
      </div>
    </div>
  );
}