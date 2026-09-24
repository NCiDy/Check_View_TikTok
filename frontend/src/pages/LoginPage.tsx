import { useState } from "react";
import { LockKeyhole, UserRound } from "lucide-react";
import { useAuth } from "../AuthContext";

const LOGIN_BACKGROUND_URL = "";

const BRAND_BACKGROUND_URL =
  "https://wpotbxpffxoaamwoqgrt.supabase.co/storage/v1/object/public/avatars/166ca8dd-e8bc-4ab7-aae1-40334905990d.png";

export function LoginPage() {
  const { login, signedOutReason } = useAuth();

  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState(signedOutReason || "");
  const [loading, setLoading] = useState(false);

  return (
    <main
      className={
        LOGIN_BACKGROUND_URL
          ? "login-page-with-background"
          : "login-page"
      }
      style={
        LOGIN_BACKGROUND_URL
          ? {
              backgroundImage: `url("${LOGIN_BACKGROUND_URL}")`,
            }
          : {
              backgroundImage: `url("${BRAND_BACKGROUND_URL}")`,
              backgroundSize: "cover",
              backgroundPosition: "center",
              backgroundRepeat: "no-repeat",
              width: "100vw",
              height: "100vh",
              minHeight: "100vh",
              maxWidth: "none",
              margin: 0,
              overflow: "hidden",
            }
      }
    >
      <section className="login-card">
        <div>
          <p className="eyebrow">ĐĂNG NHẬP</p>

          <h2>Chào mừng trở lại</h2>

          <p>Mỗi tài khoản chỉ hoạt động trên một thiết bị.</p>
        </div>

        <form
          className="form-stack"
          onSubmit={async (e) => {
            e.preventDefault();

            setLoading(true);
            setError("");

            try {
              await login(username, password);
            } catch (err) {
              setError((err as Error).message);
            } finally {
              setLoading(false);
            }
          }}
        >
          <label>
            Tên đăng nhập

            <div className="input-icon">
              <UserRound size={17} />

              <input
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                autoComplete="username"
                required
                autoFocus
              />
            </div>
          </label>

          <label>
            Mật khẩu

            <div className="input-icon">
              <LockKeyhole size={17} />

              <input
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                autoComplete="current-password"
                required
              />
            </div>
          </label>

          {error && (
            <div className="form-error">
              {error}
            </div>
          )}

          <button
            className="button primary login-button"
            disabled={loading}
          >
            {loading ? "Đang đăng nhập…" : "Đăng nhập"}
          </button>
        </form>

        <small className="login-note">
          Hệ thống nội bộ · Không chia sẻ tài khoản và mật khẩu
        </small>
      </section>
    </main>
  );
}