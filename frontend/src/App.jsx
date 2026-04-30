import { Routes, Route } from 'react-router-dom';
import { Authenticator } from '@aws-amplify/ui-react';
import LandingPage from "./pages/LandingPage/LandingPage";
import Dashboard from './pages/Dashboard/Dashboard';
import Resources from './pages/Resources/Resources';
import About from './pages/AboutPage/About';
import NavBar from './components/NavBar/NavBar';
import SignupPage from './pages/SignupPage/SignupPage';
import AuthPage from './pages/AuthPage/AuthPage';
import ProtectedRoute from './components/ProtectedRoute/ProtectedRoute';

export default function App() {
    return(
        <Authenticator.Provider>
            <NavBar/>
            <Routes>
                {/* Public Routes */}
                <Route path="/" element={<LandingPage />} />
                <Route path="/resources" element={<Resources />} />
                <Route path="/about" element={<About />} />
                <Route path="/signup" element={<SignupPage />} />
                <Route path="/login" element={<AuthPage />} />
                <Route path="/dashboard" element={<Dashboard />} />
                {/* Protected Routes */}
            </Routes>
        </Authenticator.Provider>
    );
}