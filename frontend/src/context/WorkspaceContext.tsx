import React, { createContext, useContext, useState, useEffect, useCallback } from "react";
import { Workspace, WorkspaceRole } from "../types";
import { api } from "../api/client";
import { useAuth } from "./AuthContext";

interface WorkspaceContextType {
  workspaces: Workspace[];
  currentWorkspace: Workspace | null;
  currentRole: WorkspaceRole | null;
  isLoading: boolean;
  isInitialized: boolean;
  error: string | null;
  switchWorkspace: (workspaceId: string) => void;
  refreshWorkspaces: () => Promise<void>;
  createWorkspace: (name: string, description?: string) => Promise<Workspace>;
  deleteWorkspace: (workspaceId: string) => Promise<void>;
  leaveWorkspace: (workspaceId: string) => Promise<void>;
  workspaceVersion: number;
  canEdit: boolean;
  canManageMembers: boolean;
  isOwner: boolean;
  isViewer: boolean;
}

const WorkspaceContext = createContext<WorkspaceContextType | undefined>(undefined);

export const WorkspaceProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const { isAuthenticated, token } = useAuth();
  const [workspaces, setWorkspaces] = useState<Workspace[]>([]);
  const [currentWorkspace, setCurrentWorkspace] = useState<Workspace | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [isInitialized, setIsInitialized] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [workspaceVersion, setWorkspaceVersion] = useState(0);

  const refreshWorkspaces = useCallback(async () => {
    if (!isAuthenticated) {
      setWorkspaces([]);
      setCurrentWorkspace(null);
      setIsInitialized(true);
      return;
    }

    try {
      setIsLoading(true);
      setError(null);
      const list = await api.workspaces.list();

      // Normalize role and is_personal for each workspace
      const normalizedList: Workspace[] = list.map((ws) => ({
        ...ws,
        role: (ws.role || ws.current_user_role || "viewer") as WorkspaceRole,
        is_personal: Boolean(ws.is_personal || ws.slug?.startsWith("personal-")),
      }));

      setWorkspaces(normalizedList);

      const savedWsId = localStorage.getItem("current_workspace_id");
      let selected = normalizedList.find((w) => w.id === savedWsId);

      // Stale or missing ID: fallback to Personal workspace or first available workspace
      if (!selected && normalizedList.length > 0) {
        selected = normalizedList.find((w) => w.is_personal) || normalizedList[0];
      }

      if (selected) {
        setCurrentWorkspace(selected);
        localStorage.setItem("current_workspace_id", selected.id);
      } else {
        setCurrentWorkspace(null);
        localStorage.removeItem("current_workspace_id");
      }
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Failed to load workspaces";
      setError(msg);
    } finally {
      setIsLoading(false);
      setIsInitialized(true);
    }
  }, [isAuthenticated]);

  useEffect(() => {
    refreshWorkspaces();
  }, [refreshWorkspaces, token]);

  const switchWorkspace = (workspaceId: string) => {
    const target = workspaces.find((w) => w.id === workspaceId);
    if (target && target.id !== currentWorkspace?.id) {
      setCurrentWorkspace(target);
      localStorage.setItem("current_workspace_id", target.id);
      // Bump version to notify listeners (DocumentsPage, ChatPage, etc.)
      setWorkspaceVersion((v) => v + 1);
    }
  };

  const createWorkspace = async (name: string, description?: string): Promise<Workspace> => {
    const created = await api.workspaces.create({ name, description });
    const normalizedCreated: Workspace = {
      ...created,
      role: (created.role || created.current_user_role || "owner") as WorkspaceRole,
      is_personal: Boolean(created.is_personal || created.slug?.startsWith("personal-")),
    };
    setCurrentWorkspace(normalizedCreated);
    localStorage.setItem("current_workspace_id", normalizedCreated.id);
    setWorkspaceVersion((v) => v + 1);
    await refreshWorkspaces();
    return normalizedCreated;
  };

  const deleteWorkspace = async (workspaceId: string): Promise<void> => {
    await api.workspaces.delete(workspaceId);
    await refreshWorkspaces();
  };

  const leaveWorkspace = async (workspaceId: string): Promise<void> => {
    await api.workspaces.leave(workspaceId);
    await refreshWorkspaces();
  };

  const currentRole: WorkspaceRole | null =
    currentWorkspace?.role || (currentWorkspace?.current_user_role as WorkspaceRole) || null;
  const canEdit = currentRole === "owner" || currentRole === "admin" || currentRole === "editor";
  const canManageMembers = currentRole === "owner" || currentRole === "admin";
  const isOwner = currentRole === "owner";
  const isViewer = currentRole === "viewer";

  return (
    <WorkspaceContext.Provider
      value={{
        workspaces,
        currentWorkspace,
        currentRole,
        isLoading,
        isInitialized,
        error,
        switchWorkspace,
        refreshWorkspaces,
        createWorkspace,
        deleteWorkspace,
        leaveWorkspace,
        workspaceVersion,
        canEdit,
        canManageMembers,
        isOwner,
        isViewer,
      }}
    >
      {children}
    </WorkspaceContext.Provider>
  );
};

export const useWorkspace = () => {
  const context = useContext(WorkspaceContext);
  if (!context) {
    throw new Error("useWorkspace must be used within a WorkspaceProvider");
  }
  return context;
};
