import { BrowserRouter, Routes, Route } from "react-router-dom";
import Layout from "./components/Layout";
import Dashboard from "./pages/Dashboard";
import RepoList from "./pages/RepoList";
import RepoDetail from "./pages/RepoDetail";
import ReviewDetail from "./pages/ReviewDetail";
import PromptWorkbench from "./pages/PromptWorkbench";

function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route element={<Layout />}>
          <Route path="/" element={<Dashboard />} />
          <Route path="/repos" element={<RepoList />} />
          <Route path="/repos/:id" element={<RepoDetail />} />
          <Route path="/reviews/:id" element={<ReviewDetail />} />
          <Route path="/prompts" element={<PromptWorkbench />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}

export default App;
