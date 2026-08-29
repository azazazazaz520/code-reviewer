import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { act } from "react";
import { describe, expect, it, vi } from "vitest";
import { Modal } from "./modal";

describe("Modal", () => {
  it("将焦点移入弹层、限制 Tab 循环并在关闭后恢复焦点", async () => {
    const trigger = document.createElement("button");
    document.body.appendChild(trigger);
    trigger.focus();
    const onClose = vi.fn();
    const { rerender } = render(
      <Modal open onClose={onClose} titleId="modal-title">
        <h2 id="modal-title">测试弹层</h2>
        <button type="button">第一个操作</button>
        <button type="button">第二个操作</button>
      </Modal>,
    );

    await waitFor(() => expect(screen.getByRole("button", { name: "第一个操作" })).toHaveFocus());
    expect(document.getElementById("root")?.inert).toBe(true);

    screen.getByRole("button", { name: "第二个操作" }).focus();
    fireEvent.keyDown(document, { key: "Tab" });
    expect(screen.getByRole("button", { name: "第一个操作" })).toHaveFocus();
    screen.getByRole("button", { name: "第一个操作" }).focus();
    fireEvent.keyDown(document, { key: "Tab", shiftKey: true });
    expect(screen.getByRole("button", { name: "第二个操作" })).toHaveFocus();
    fireEvent.keyDown(document, { key: "Escape" });
    expect(onClose).toHaveBeenCalledTimes(1);

    rerender(<Modal open={false} onClose={onClose} titleId="modal-title"><div /></Modal>);
    await waitFor(() => expect(trigger).toHaveFocus());
    trigger.remove();
  });

  it("关闭时保留弹层直到退出过渡完成", () => {
    vi.useFakeTimers();
    try {
      const onClose = vi.fn();
      const { rerender } = render(
        <Modal open onClose={onClose} titleId="modal-title">
          <h2 id="modal-title">测试弹层</h2>
        </Modal>,
      );

      rerender(
        <Modal open={false} onClose={onClose} titleId="modal-title">
          <h2 id="modal-title">测试弹层</h2>
        </Modal>,
      );

      expect(screen.getByRole("dialog")).toHaveAttribute("data-state", "closed");
      act(() => vi.advanceTimersByTime(249));
      expect(screen.getByRole("dialog")).toBeInTheDocument();
      act(() => vi.advanceTimersByTime(1));
      expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    } finally {
      vi.useRealTimers();
    }
  });
});
