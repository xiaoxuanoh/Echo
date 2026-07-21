import { describe, expect, it } from "vitest";

import {
  MAX_IMAGE_SIZE_BYTES,
  MAX_PDF_SIZE_BYTES,
  validateNewImages,
  validatePdf,
} from "../src/lib/upload-validation";

function file(name: string, type: string, size = 10): File {
  return new File([new Uint8Array(size)], name, { type });
}

describe("PDF validation", () => {
  it("accepts a PDF within the limit", () => {
    expect(validatePdf(file("book.pdf", "application/pdf"))).toBeNull();
  });

  it("rejects the wrong type and oversized PDFs", () => {
    expect(validatePdf(file("notes.txt", "text/plain"))).toContain("PDF");
    expect(
      validatePdf(file("large.pdf", "application/pdf", MAX_PDF_SIZE_BYTES + 1)),
    ).toContain("50 MB");
  });
});

describe("image validation", () => {
  it("accepts JPG and PNG pages", () => {
    expect(
      validateNewImages(
        [file("one.jpg", "image/jpeg"), file("two.png", "image/png")],
        0,
      ),
    ).toBeNull();
  });

  it("rejects invalid, oversized, and excess images", () => {
    expect(validateNewImages([file("page.gif", "image/gif")], 0)).toContain(
      "not a JPG or PNG",
    );
    expect(
      validateNewImages(
        [file("page.png", "image/png", MAX_IMAGE_SIZE_BYTES + 1)],
        0,
      ),
    ).toContain("15 MB");
    expect(validateNewImages([file("page.png", "image/png")], 100)).toContain(
      "up to 100",
    );
  });
});
