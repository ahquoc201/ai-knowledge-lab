import React, { createContext, useContext, useState, useEffect } from "react";
import { api } from "../api/client";

interface AuthContextType {
  token: string | null;
  userEmail: string | null;
  isAuthenticated: boolean;
  login: (email: string, password: string) => Promise<void>;
  register: (email: string, password: string) => Promise<void>;
  logout: () => void;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export const AuthProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [token, setToken] = useState<string | null>(() => localStorage.getItem("auth_token"));
  const [userEmail, setUserEmail] = useState<string | null>(() => localStorage.getItem("auth_user_email"));

  useEffect(() => {
    if (token) {
      localStorage.setItem("auth_token", token);
    } else {
      localStorage.removeItem("auth_token");
    }
  }, [token]);

  useEffect(() => {
    if (userEmail) {
      localStorage.setItem("auth_user_email", userEmail);
    } else {
      localStorage.removeItem("auth_user_email");
    }
  }, [userEmail]);

  const login = async (email: string, password: string) => {
    const res = await api.auth.login(email, password);
    setToken(res.access_token);
    setUserEmail(email);
  };

  const register = async (email: string, password: string) => {
    await api.auth.register(email, password);
    await login(email, password);
  };

  const logout = () => {
    setToken(null);
    setUserEmail(null);
    localStorage.removeItem("auth_token");
    localStorage.removeItem("auth_user_email");
  };

  return (
    <AuthContext.Provider
      value={{
        token,
        userEmail,
        isAuthenticated: !!token,
        login,
        register,
        logout,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
};

export const useAuth = () => {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error("useAuth must be used within an AuthProvider");
  }
  return context;
};
