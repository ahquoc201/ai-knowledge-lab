import React, { createContext, useContext, useState, useEffect, useCallback } from "react";
import { Workspace, WorkspaceRole } from "../types";
import { api } from "../api/client";
import { useAuth } from "./AuthContext";

interface WorkspaceContextType {
  workspaces: Workspace[];
  currentWorkspace: Workspace | null;
  currentRole: WorkspaceRole | null;
  isLoading: boolean;
  switchWorkspace: (workspaceId: string) => void;
  refreshWorkspaces: () => Promise<void>;
  createWorkspace: (name: string, description?: string) => Promise<Workspace>;
  deleteWorkspace: (workspaceId: string) => Promise<void>;
  leaveWorkspace: (workspaceId: string) => Promise<void>;
  workspaceVersion: number; // Increment on switch so consumers can react
  canEdit: boolean;
  canManageMembers: boolean;
  isOwner: boolean;
  isViewer: boolean;
}

const WorkspaceContext = createContext<WorkspaceContextType | undefined>(undefined);

export const WorkspaceProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const { isAuthenticated } = useAuth();
  const [workspaces, setWorkspaces] = useState<Workspace[]>([]);
  const [currentWorkspace, setCurrentWorkspace] = useState<Workspace | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [workspaceVersion, setWorkspaceVersion] = useState(0);

  const refreshWorkspaces = useCallback(async () => {
    if (!isAuthenticated) {
      setWorkspaces([]);
      setCurrentWorkspace(null);
      return;
    }

    try {
      setIsLoading(true);
      const list = await api.workspaces.list();
      setWorkspaces(list);

      const savedWsId = localStorage.getItem("current_workspace_id");
      let selected = list.find((w) => w.id === savedWsId);

      // If saved workspace is not found, default to Personal workspace or first workspace
      if (!selected && list.length > 0) {
        selected = list.find((w) => w.is_personal) || list[0];
      }

      if (selected) {
        setCurrentWorkspace(selected);
        localStorage.setItem("current_workspace_id", selected.id);
      } else {
        setCurrentWorkspace(null);
        localStorage.removeItem("current_workspace_id");
      }
    } catch (err) {
      console.error("Failed to fetch workspaces:", err);
    } finally {
      setIsLoading(false);
    }
  }, [isAuthenticated]);

  useEffect(() => {
    refreshWorkspaces();
  }, [refreshWorkspaces]);

  const switchWorkspace = (workspaceId: string) => {
    const target = workspaces.find((w) => w.id === workspaceId);
    if (target && target.id !== currentWorkspace?.id) {
      setCurrentWorkspace(target);
      localStorage.setItem("current_workspace_id", target.id);
      // Bump version to notify all listeners (DocumentsPage, ChatPage, etc.)
      setWorkspaceVersion((v) => v + 1);
    }
  };

  const createWorkspace = async (name: string, description?: string): Promise<Workspace> => {
    const created = await api.workspaces.create({ name, description });
    await refreshWorkspaces();
    switchWorkspace(created.id);
    return created;
  };

  const deleteWorkspace = async (workspaceId: string): Promise<void> => {
    await api.workspaces.delete(workspaceId);
    await refreshWorkspaces();
  };

  const leaveWorkspace = async (workspaceId: string): Promise<void> => {
    await api.workspaces.leave(workspaceId);
    await refreshWorkspaces();
  };

  const currentRole: WorkspaceRole | null = currentWorkspace?.role || null;
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
