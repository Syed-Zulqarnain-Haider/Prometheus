import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

// Mock the data hooks so the widget's gating logic is tested in isolation (no network/auth).
const useChatStatus = vi.fn();
const useSendChat = vi.fn(() => ({ isPending: false, mutateAsync: vi.fn() }));
vi.mock("@/lib/api-hooks", () => ({
  useChatStatus: () => useChatStatus(),
  useSendChat: () => useSendChat(),
}));

import { ChatWidget } from "@/components/chat/chat-widget";

describe("ChatWidget gating (RBAC/feature visibility)", () => {
  beforeEach(() => vi.clearAllMocks());

  it("renders nothing when the assistant is unavailable", () => {
    useChatStatus.mockReturnValue({ data: { available: false, providers: [] } });
    const { container } = render(<ChatWidget />);
    expect(container).toBeEmptyDOMElement();
    expect(screen.queryByRole("button")).toBeNull();
  });

  it("shows the launcher when the assistant is available", () => {
    useChatStatus.mockReturnValue({
      data: { available: true, providers: [{ id: "claude", label: "Claude" }] },
    });
    render(<ChatWidget />);
    expect(
      screen.getByLabelText(/open the ask-your-data assistant/i),
    ).toBeInTheDocument();
  });
});
