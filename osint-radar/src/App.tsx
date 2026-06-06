import { BrowserRouter as Router, Routes, Route } from "react-router-dom";
import Home from "@/pages/Home";
import Dashboard from "@/pages/Dashboard";
import VideoAnalysis from "@/pages/VideoAnalysis";

export default function App() {
  return (
    <Router>
      <Routes>
        <Route path="/" element={<Home />} />
        <Route path="/dashboard/:queryId" element={<Dashboard />} />
        <Route path="/video/:videoId" element={<VideoAnalysis />} />
      </Routes>
    </Router>
  );
}
