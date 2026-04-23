import { Routes, Route } from 'react-router-dom';
import LandingPage from "./pages/LandingPage";
import Dashboard from './pages/Dashboard';
import Resources from './pages/Resources';
import About from './pages/AboutPage/About';
import NavBar from './components/NavBar/NavBar';
import SignupPage from './pages/SignupPage/SignupPage';
import AuthPage from './pages/AuthPage/AuthPage';

export default function App() {
    return(
        <>
            <NavBar />
            <Routes>
                <Route path="/" element={<LandingPage />} />
                <Route path="/dashboard" element={<Dashboard />} />
                <Route path="/resources" element={<Resources />} />
                <Route path="/about" element={<About />} />
                <Route path="/signupPage" element={<SignupPage />} />
                <Route path="/AuthPage" element={<AuthPage />} />
            </Routes>
        </>
    );
}