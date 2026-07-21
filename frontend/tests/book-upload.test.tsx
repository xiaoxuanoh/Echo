import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { BookUpload } from "@/components/upload/book-upload";

describe("page photo workflow", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn());
    Object.defineProperty(URL, "createObjectURL", {
      configurable: true,
      value: vi.fn((file: File) => `blob:${file.name}`),
    });
    Object.defineProperty(URL, "revokeObjectURL", {
      configurable: true,
      value: vi.fn(),
    });
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it("submits the confirmed order and rotation", async () => {
    const fetchMock = vi.mocked(fetch);
    fetchMock.mockResolvedValue(
      new Response(
        JSON.stringify({
          book_id: "temporary-book-id",
          source_type: "images",
          total_pages: 2,
          ordered_image_filenames: ["page-two.png", "page-one.png"],
          pages: [],
          processing_status: "uploaded",
        }),
        { status: 200, headers: { "Content-Type": "application/json" } },
      ),
    );
    render(<BookUpload />);
    fireEvent.click(
      screen.getByRole("button", { name: /^Upload Page Photos/ }),
    );

    const pageOne = new File(["one"], "page-one.png", { type: "image/png" });
    const pageTwo = new File(["two"], "page-two.png", { type: "image/png" });
    fireEvent.change(screen.getByLabelText("Choose page photos"), {
      target: { files: [pageOne, pageTwo] },
    });

    fireEvent.click(screen.getAllByRole("button", { name: "Rotate right" })[0]);
    fireEvent.click(screen.getAllByRole("button", { name: "Later" })[0]);
    fireEvent.click(screen.getByRole("button", { name: "Prepare your book" }));

    await waitFor(() => expect(fetchMock).toHaveBeenCalledOnce());
    const request = fetchMock.mock.calls[0][1];
    const body = request?.body as FormData;
    const filenames = body.getAll("files").map((entry) => (entry as File).name);

    expect(filenames).toEqual(["page-two.png", "page-one.png"]);
    expect(body.get("rotations")).toBe("[0,90]");
    expect(await screen.findByText("Your book pages are prepared")).toBeVisible();
  });
});
