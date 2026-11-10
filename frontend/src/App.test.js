import {
  render,
  screen,
  waitFor,
} from "@testing-library/react";

import App from "./App";

beforeEach(() => {
  global.fetch = jest.fn(() =>
    Promise.resolve({
      ok: true,
      json: () =>
        Promise.resolve([]),
    })
  );
});

afterEach(() => {
  jest.restoreAllMocks();
});

test(
  "renders the BugPilot dashboard",
  async () => {
    render(<App />);

    await waitFor(() => {
      expect(
        screen.getByText(
          "BugPilot"
        )
      ).toBeInTheDocument();
    });
  }
);