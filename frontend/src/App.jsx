import { Routes, Route } from 'react-router-dom';
import LandingPage from "./pages/LandingPage";
import Dashboard from './pages/Dashboard';
import Resources from './pages/Resources';
import About from './pages/AboutPage/About';
import NavBar from './components/NavBar/NavBar';

export default function App() {
    return(
        <>
            <NavBar />
            <Routes>
                <Route path="/" element={<LandingPage />} />
                <Route path="/dashboard" element={<Dashboard />} />
                <Route path="/resources" element={<Resources />} />
                <Route path="/about" element={<About />} />
            </Routes>
        </>
    );
}