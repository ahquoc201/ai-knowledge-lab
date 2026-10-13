import React, { useState } from "react";
import { useAuth } from "../context/AuthContext";
import { Button } from "../components/ui/Button";
import { Input } from "../components/ui/Input";
import { Alert } from "../components/ui/Alert";
import { Sparkles, ShieldCheck, Database, Layers } from "lucide-react";

export const AuthPage: React.FC = () => {
  const { login, register } = useAuth();
  const [isRegister, setIsRegister] = useState(false);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);

    if (!email || !password) {
      setError("Vui lòng điền đầy đủ email và mật khẩu.");
      return;
    }

    if (password.length < 8) {
      setError("Mật khẩu phải có ít nhất 8 ký tự.");
      return;
    }

    setIsLoading(true);
    try {
      if (isRegister) {
        await register(email, password);
      } else {
        await login(email, password);
      }
    } catch (err: unknown) {
      const message =
        err instanceof Error ? err.message : "Đăng nhập/Đăng ký không thành công.";
      setError(message);
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="flex min-h-screen w-screen bg-background">
      {/* Left hero / enterprise branding */}
      <div className="hidden lg:flex lg:w-1/2 flex-col justify-between bg-surface border-r border-border p-12">
        <div className="flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-primary text-white shadow-md">
            <Sparkles className="h-6 w-6" />
          </div>
          <div>
            <h1 className="text-xl font-bold tracking-tight text-foreground">AI Knowledge Lab</h1>
            <p className="text-xs uppercase tracking-wider text-foreground-subtle font-semibold">
              Evidence-Driven AI Workspace
            </p>
          </div>
        </div>

        <div className="space-y-8 my-auto max-w-lg">
          <div>
            <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-semibold bg-primary-subtle text-primary border border-blue-200 mb-4">
              Version 0.2.0 • Architecture Milestone T260021
            </span>
            <h2 className="text-3xl font-extrabold text-foreground tracking-tight leading-tight">
              Hệ thống quản trị tri thức doanh nghiệp & RAG an toàn, có dẫn nguồn.
            </h2>
            <p className="mt-4 text-sm text-foreground-muted leading-relaxed">
              Giải pháp AI Knowledge Lab bảo đảm mọi câu trả lời đều được định danh nguồn trích dẫn
              chính xác (strict citation validation), phòng chống hallucination và bảo vệ an toàn ngữ cảnh.
            </p>
          </div>

          <div className="grid grid-cols-1 gap-4 pt-4 border-t border-border">
            <div className="flex items-start gap-3">
              <div className="rounded-lg bg-emerald-50 p-2 text-status-ready-text">
                <ShieldCheck className="h-5 w-5" />
              </div>
              <div>
                <h4 className="text-xs font-bold text-foreground">Audit & Strict Citations</h4>
                <p className="text-xs text-foreground-muted">
                  Tự động kiểm tra tính hợp lệ của nguồn trích dẫn trước khi trả về câu trả lời cho người dùng.
                </p>
              </div>
            </div>

            <div className="flex items-start gap-3">
              <div className="rounded-lg bg-blue-50 p-2 text-primary">
                <Database className="h-5 w-5" />
              </div>
              <div>
                <h4 className="text-xs font-bold text-foreground">PostgreSQL & pgvector</h4>
                <p className="text-xs text-foreground-muted">
                  Lưu trữ vector embeddings đa chiều, kết hợp semantic search và hybrid filtering.
                </p>
              </div>
            </div>

            <div className="flex items-start gap-3">
              <div className="rounded-lg bg-amber-50 p-2 text-status-pending-text">
                <Layers className="h-5 w-5" />
              </div>
              <div>
                <h4 className="text-xs font-bold text-foreground">TDD & Zero-Regression</h4>
                <p className="text-xs text-foreground-muted">
                  350+ automated unit & integration tests bảo đảm hệ thống vận hành tin cậy và liên tục.
                </p>
              </div>
            </div>
          </div>
        </div>

        <div className="text-xs text-foreground-subtle">
          © 2026 AI Knowledge Lab. Tất cả quyền được bảo lưu.
        </div>
      </div>

      {/* Right authentication form */}
      <div className="flex flex-1 flex-col justify-center px-6 py-12 lg:px-16">
        <div className="mx-auto w-full max-w-md">
          {/* Mobile brand header */}
          <div className="mb-8 flex items-center gap-3 lg:hidden">
            <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-primary text-white">
              <Sparkles className="h-5 w-5" />
            </div>
            <h1 className="text-lg font-bold text-foreground">AI Knowledge Lab</h1>
          </div>

          <div className="rounded-2xl border border-border bg-surface p-8 shadow-sm">
            <div className="mb-6">
              <h2 className="text-2xl font-bold tracking-tight text-foreground">
                {isRegister ? "Tạo tài khoản mới" : "Đăng nhập hệ thống"}
              </h2>
              <p className="mt-1 text-xs text-foreground-muted">
                {isRegister
                  ? "Điền thông tin email và mật khẩu để khởi tạo tài khoản làm việc."
                  : "Truy cập không gian làm việc AI Knowledge Lab với tài khoản của bạn."}
              </p>
            </div>

            {error && (
              <Alert type="error" className="mb-6" onClose={() => setError(null)}>
                {error}
              </Alert>
            )}

            <form onSubmit={handleSubmit} className="space-y-4">
              <Input
                label="Email doanh nghiệp"
                type="email"
                placeholder="name@company.com"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                autoComplete="email"
                required
              />

              <Input
                label="Mật khẩu"
                type="password"
                placeholder="••••••••"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                helperText={isRegister ? "Mật khẩu tối thiểu 8 ký tự." : undefined}
                autoComplete={isRegister ? "new-password" : "current-password"}
                required
              />

              <Button
                type="submit"
                variant="primary"
                className="w-full mt-2"
                isLoading={isLoading}
              >
                {isRegister ? "Tạo tài khoản" : "Đăng nhập ngay"}
              </Button>
            </form>

            <div className="mt-6 border-t border-border pt-4 text-center">
              <button
                type="button"
                onClick={() => {
                  setIsRegister(!isRegister);
                  setError(null);
                }}
                className="text-xs font-semibold text-primary hover:underline"
              >
                {isRegister
                  ? "Đã có tài khoản? Nhấp vào đây để đăng nhập"
                  : "Chưa có tài khoản? Nhấp vào đây để đăng ký"}
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
