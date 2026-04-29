import { useAuthenticator } from '@aws-amplify/ui-react';
import { Navigate, useLocation } from 'react-router-dom';
import styles from './ProtectedRoute.module.css'

export default function ProtectedRoute({ children }) {
  const { authStatus } = useAuthenticator((context) => [context.authStatus]);
  const location = useLocation();

  // Show a blank/loading screen while Amplify checks local storage
  if (authStatus === 'configuring') {
    return (
      <div style={styles.loadingContainer} />
    );
  }

  // Redirect to login if they aren't authenticated
  if (authStatus !== 'authenticated') {
    return <Navigate to="/login" state={{ from: location }} replace />;
  }

  // Render the protected component (Dashboard) if they are logged in
  return children;
}