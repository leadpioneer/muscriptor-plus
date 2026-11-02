import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { I18nProvider } from "../i18n";
import { ModelSwitcher } from "./ModelSwitcher";

function json(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  });
}

describe("ModelSwitcher", () => {
  const fetchMock = vi.fn();

  beforeEach(() => {
    fetchMock.mockReset();
    vi.stubGlobal("fetch", fetchMock);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("shows the server's reason when a switch is refused", async () => {
    fetchMock
      .mockResolvedValueOnce(
        json(200, { model: "medium", status: "ready", error: null }),
      )
      .mockResolvedValueOnce(
        json(409, {
          detail: "a transcription is in progress; try again when it finishes",
        }),
      );
    render(
      <I18nProvider>
        <ModelSwitcher />
      </I18nProvider>,
    );

    const select = await screen.findByRole("combobox");
    await userEvent.selectOptions(select, "large");

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "a transcription is in progress",
    );
    await waitFor(() => expect(select).toHaveValue("medium"));
  });
});
