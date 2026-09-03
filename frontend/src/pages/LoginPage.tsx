import { useState } from "react";
import { Activity, LockKeyhole, UserRound } from "lucide-react";
import { useAuth } from "../AuthContext";

export function LoginPage() {
  const { login, signedOutReason } = useAuth();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState(signedOutReason || "");
  const [loading, setLoading] = useState(false);
  return <main className="login-page"><section className="login-brand"><span className="brand-mark large">TT</span><p className="eyebrow">BEA ENTERTAIMENT</p><h1>BeaTok Tok Tok</h1><br /><h3>Phòng Víp mãi đỉnh</h3><p>Phòng Víp Víp Víp Bea Tok Tok Tok</p><div className="login-feature"><Activity size={18} /><span>Dữ liệu đồng bộ trực tiếp sau mỗi job</span></div></section><section className="login-card"><div><p className="eyebrow">ĐĂNG NHẬP</p><h2>Chào mừng trở lại</h2><p>Mỗi tài khoản chỉ hoạt động trên một thiết bị.</p></div><form className="form-stack" onSubmit={async (e) => { e.preventDefault(); setLoading(true); setError(""); try { await login(username, password); } catch (err) { setError((err as Error).message); } finally { setLoading(false); } }}><label>Tên đăng nhập<div className="input-icon"><UserRound size={17} /><input value={username} onChange={(e) => setUsername(e.target.value)} autoComplete="username" required autoFocus /></div></label><label>Mật khẩu<div className="input-icon"><LockKeyhole size={17} /><input type="password" value={password} onChange={(e) => setPassword(e.target.value)} autoComplete="current-password" required /></div></label>{error && <div className="form-error">{error}</div>}<button className="button primary login-button" disabled={loading}>{loading ? "Đang đăng nhập…" : "Đăng nhập"}</button></form><small className="login-note">Hệ thống nội bộ · Không chia sẻ tài khoản và mật khẩu</small></section></main>;
}
