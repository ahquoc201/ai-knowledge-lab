import React from "react";
import { Card, CardHeader, CardTitle, CardDescription } from "../components/ui/Card";
import { useAuth } from "../context/AuthContext";
import { Shield, Database, Lock, CheckCircle } from "lucide-react";

export const SettingsPage: React.FC = () => {
  const { userEmail } = useAuth();

  return (
    <div className="space-y-6 max-w-4xl mx-auto">
      <div>
        <h2 className="text-xl font-bold text-foreground">Cấu hình & Giám sát hệ thống</h2>
        <p className="text-xs text-foreground-muted mt-0.5">
          Thông tin môi trường, cấu hình bảo mật và trạng thái kết nối hạ tầng.
        </p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <Card>
          <CardHeader>
            <div className="flex items-center gap-2">
              <Lock className="h-4 w-4 text-primary" />
              <CardTitle>Tài khoản hiện tại</CardTitle>
            </div>
            <CardDescription>Thông tin định danh phiên làm việc</CardDescription>
          </CardHeader>
          <div className="space-y-2.5 text-xs">
            <div className="flex justify-between py-1 border-b border-border">
              <span className="text-foreground-muted">Email</span>
              <span className="font-semibold text-foreground">{userEmail || "N/A"}</span>
            </div>
            <div className="flex justify-between py-1 border-b border-border">
              <span className="text-foreground-muted">Vai trò</span>
              <span className="font-semibold text-foreground">Workspace Owner</span>
            </div>
            <div className="flex justify-between py-1">
              <span className="text-foreground-muted">Cơ chế xác thực</span>
              <span className="font-semibold text-foreground">JWT Bearer Token</span>
            </div>
          </div>
        </Card>

        <Card>
          <CardHeader>
            <div className="flex items-center gap-2">
              <Database className="h-4 w-4 text-status-ready-text" />
              <CardTitle>Hạ tầng cơ sở dữ liệu</CardTitle>
            </div>
            <CardDescription>Cấu hình vector store và quan hệ</CardDescription>
          </CardHeader>
          <div className="space-y-2.5 text-xs">
            <div className="flex justify-between py-1 border-b border-border">
              <span className="text-foreground-muted">Cơ sở dữ liệu</span>
              <span className="font-semibold text-foreground">PostgreSQL 16</span>
            </div>
            <div className="flex justify-between py-1 border-b border-border">
              <span className="text-foreground-muted">Vector Extension</span>
              <span className="font-semibold text-foreground">pgvector (cosine distance)</span>
            </div>
            <div className="flex justify-between py-1">
              <span className="text-foreground-muted">Kích thước vector</span>
              <span className="font-semibold text-foreground">1536 chiều</span>
            </div>
          </div>
        </Card>

        <Card className="md:col-span-2">
          <CardHeader>
            <div className="flex items-center gap-2">
              <Shield className="h-4 w-4 text-amber-600" />
              <CardTitle>Chính sách phòng vệ dữ liệu (Data Defense Policies)</CardTitle>
            </div>
            <CardDescription>Các quy tắc an toàn thông tin áp dụng trên toàn workspace</CardDescription>
          </CardHeader>
          <div className="space-y-3 text-xs">
            <div className="flex items-start gap-2.5">
              <CheckCircle className="h-4 w-4 text-status-ready-text mt-0.5" />
              <div>
                <span className="font-semibold text-foreground">Tenant Isolation: </span>
                <span className="text-foreground-muted">
                  Tất cả truy vấn tìm kiếm vector và tài liệu đều được cô lập tuyệt đối theo `user_id`.
                </span>
              </div>
            </div>
            <div className="flex items-start gap-2.5">
              <CheckCircle className="h-4 w-4 text-status-ready-text mt-0.5" />
              <div>
                <span className="font-semibold text-foreground">Prompt Injection Sanitization: </span>
                <span className="text-foreground-muted">
                  Ngữ cảnh nạp vào mô hình được bao bọc trong data delimiters, chỉ coi context là dữ liệu tham khảo, không thực thi chỉ thị chứa trong tài liệu.
                </span>
              </div>
            </div>
            <div className="flex items-start gap-2.5">
              <CheckCircle className="h-4 w-4 text-status-ready-text mt-0.5" />
              <div>
                <span className="font-semibold text-foreground">Zero Fail-Open Policy: </span>
                <span className="text-foreground-muted">
                  Nếu câu trả lời sinh ra có trích dẫn không khớp hoặc không hợp lệ, hệ thống sẽ chặn không hiển thị ra người dùng.
                </span>
              </div>
            </div>
          </div>
        </Card>
      </div>
    </div>
  );
};
