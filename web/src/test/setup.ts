import "@testing-library/jest-dom/vitest";

Object.defineProperty(globalThis, "crypto", {
  value: {
    randomUUID: () => "test-request-id",
    subtle: {
      digest: async () => new Uint8Array([1, 2, 3]).buffer,
    },
  },
  configurable: true,
});

if (!File.prototype.arrayBuffer) {
  File.prototype.arrayBuffer = async () => new TextEncoder().encode("test-file").buffer;
}

class ResizeObserverMock {
  observe() {}
  unobserve() {}
  disconnect() {}
}

globalThis.ResizeObserver = ResizeObserverMock;
