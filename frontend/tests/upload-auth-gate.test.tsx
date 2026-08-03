import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { UploadAuthGate } from "@/components/auth/upload-auth-gate";
import { getSupabaseBrowserClient } from "@/lib/supabase/browser";

vi.mock("@/components/upload/document-upload", () => ({
  DocumentUpload: () => <div>Upload form ready</div>,
}));

vi.mock("@/lib/supabase/browser", () => ({
  getSupabaseBrowserClient: vi.fn(),
}));

const getSupabaseBrowserClientMock = vi.mocked(getSupabaseBrowserClient);

describe("upload auth gate", () => {
  afterEach(() => {
    cleanup();
    vi.clearAllMocks();
  });

  it("shows the upload form when Supabase is not configured", async () => {
    getSupabaseBrowserClientMock.mockReturnValue(null);

    render(<UploadAuthGate />);

    expect(await screen.findByText("Upload form ready")).toBeInTheDocument();
    expect(screen.queryByText("Sign in to upload files")).not.toBeInTheDocument();
  });

  it("blocks uploads when the user is signed out", async () => {
    const unsubscribe = vi.fn();

    getSupabaseBrowserClientMock.mockReturnValue({
      auth: {
        getSession: vi.fn().mockResolvedValue({ data: { session: null } }),
        onAuthStateChange: vi.fn().mockReturnValue({
          data: { subscription: { unsubscribe } },
        }),
      },
    } as unknown as ReturnType<typeof getSupabaseBrowserClient>);

    render(<UploadAuthGate />);

    expect(await screen.findByText("Sign in to upload files")).toBeInTheDocument();
    expect(
      screen.getByRole("link", { name: "Sign in to start uploading" }),
    ).toHaveAttribute("href", "/profile");
    expect(screen.queryByText("Upload form ready")).not.toBeInTheDocument();
  });

  it("shows the upload form when the user is signed in", async () => {
    const unsubscribe = vi.fn();

    getSupabaseBrowserClientMock.mockReturnValue({
      auth: {
        getSession: vi.fn().mockResolvedValue({
          data: {
            session: {
              user: {
                email: "reader@example.com",
                id: "user-id",
              },
            },
          },
        }),
        onAuthStateChange: vi.fn().mockReturnValue({
          data: { subscription: { unsubscribe } },
        }),
      },
    } as unknown as ReturnType<typeof getSupabaseBrowserClient>);

    render(<UploadAuthGate />);

    expect(await screen.findByText("Upload form ready")).toBeInTheDocument();
    expect(screen.queryByText("Sign in to upload files")).not.toBeInTheDocument();
  });
});
