import { BrowserRouter, Routes, Route } from "react-router-dom";

import Home from "./pages/Home";
import Loading from "./pages/Loading";
import Resultado from "./pages/Resultado";
import Log from "./pages/Log";
import Login from "./pages/Login";
import CriarConta from "./pages/CriarConta";
import TrocaSenha from "./pages/TrocaSenha";
import NovaSenha from "./pages/NovaSenha";
import Admin from "./pages/Admin";

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Home />} />
        <Route path="/loading" element={<Loading />} />
        <Route path="/resultado" element={<Resultado />} />
        <Route path="/log" element={<Log />} />
        <Route path="/login" element={<Login />} />
        <Route path="/criar-conta" element={<CriarConta />} />
        <Route path="/troca-senha" element={<TrocaSenha />} />
        <Route path="/nova-senha" element={<NovaSenha />} />
        <Route path="/admin" element={<Admin />} />
      </Routes>
    </BrowserRouter>
  );
}