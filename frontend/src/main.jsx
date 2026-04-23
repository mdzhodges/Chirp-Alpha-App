import React, { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import { BrowserRouter } from 'react-router-dom';
import { Amplify } from 'aws-amplify';
import { Authenticator } from '@aws-amplify/ui-react';
import App from './App.jsx';
import './index.css';
import '@aws-amplify/ui-react/styles.css';

Amplify.configure({
  Auth: {
    Cognito: {
      userPoolId: 'us-east-1_1fa6e13b58d446a584b411452621c1aa',
      userPoolClientId: '6aa27594be3c4059b7edefd5d2',
      userPoolEndpoint: 'http://localhost:5000' 
    }
  }
});

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <Authenticator.Provider>
      <BrowserRouter>
        <App />
      </BrowserRouter>
    </Authenticator.Provider>
  </StrictMode>
);